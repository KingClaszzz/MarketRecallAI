import json
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from app.data.validation import HOUR_MS
from app.db import CreditEntry, Forecast, Pick, User, get_session
from app.users import auth, credits, picks, sessions

ADDR = "0x" + "ab" * 32


def balance(address=ADDR) -> int:
    with get_session() as s:
        return s.get(User, address).credits


def test_signup_grants_three_credits(temp_db):
    assert credits.get_user(ADDR).credits == 3


def test_weekly_refill_tops_up_to_three_but_keeps_winnings(temp_db):
    credits.get_user(ADDR)
    credits.spend(ADDR, 3, "session")
    with get_session() as s:
        u = s.get(User, ADDR)
        u.week = "2000-W01"
        s.add(u)
        s.commit()
    assert credits.get_user(ADDR).credits == 3  # refilled

    credits.grant(ADDR, 4, "call_right")  # 7 now
    with get_session() as s:
        u = s.get(User, ADDR)
        u.week = "2000-W02"
        s.add(u)
        s.commit()
    assert credits.get_user(ADDR).credits == 7  # above the floor: kept


def test_balance_is_capped(temp_db):
    credits.get_user(ADDR)
    credits.grant(ADDR, 50, "call_right")
    assert balance() == credits.CAP


def test_cannot_spend_more_than_balance(temp_db):
    credits.get_user(ADDR)
    with pytest.raises(credits.InsufficientCredits):
        credits.spend(ADDR, 4, "session")
    assert balance() == 3


def test_ledger_matches_balance(temp_db):
    credits.get_user(ADDR)
    credits.spend(ADDR, 1, "session")
    credits.grant(ADDR, 2, "call_right")
    with get_session() as s:
        entries = s.exec(select(CreditEntry).where(CreditEntry.address == ADDR)).all()
    assert sum(e.delta for e in entries) == balance() == 4


@pytest.fixture
def no_walrus(monkeypatch):
    written = []

    def fake_remember(namespace, kind, text, ref=None, essential=False):
        written.append((namespace, kind, text))
        return type("Ref", (), {"id": len(written)})()

    monkeypatch.setattr(picks.store, "remember", fake_remember)
    monkeypatch.setattr(sessions.store, "recall", lambda *a, **k: [])
    return written


@pytest.fixture
def reading(temp_db):
    """A live model reading for WAL and SUI at the latest decision time."""
    t = picks.last_closed_hour() + HOUR_MS
    with get_session() as s:
        for asset in ("WAL", "SUI"):
            s.add(Forecast(asset=asset, t=t, horizon_h=4, close_at_t=1.0, voices={"lr-v1": 0.6}, model_version="test",
                           regime={"vol": "high", "trend": "up", "chain": "normal", "session": "us-weekday"},
                           amnesiac_p=0.6, recall_p=0.56, recall_action="ADJUSTED",
                           trace={"decision": {"voice": "lr-v1", "reasons": ["overconfident"], "n_matched": 30,
                                               "credibility": {}}}))
        s.commit()
    return t


def _open(mode="model", direction=None, asset="WAL"):
    credits.get_user(ADDR)
    return sessions.open_session(ADDR, asset, mode, direction)


def _resolve(monkeypatch, slot, start, end):
    # Pretend the whole 4h window has closed.
    monkeypatch.setattr(picks, "last_closed_hour", lambda: slot + 3 * HOUR_MS)
    closes = {slot - HOUR_MS: start, slot + 3 * HOUR_MS: end}
    return picks.resolve_picks(lambda asset, open_time: closes.get(open_time))


def test_session_costs_one_credit_and_targets_the_next_window(reading, no_walrus):
    ps = _open()
    assert balance() == 2
    assert ps.slot_t == picks.next_slot() and ps.slot_t > picks.last_closed_hour() + HOUR_MS
    assert ps.pick_id is None and sessions.view(ps)["can_call"]


def test_own_mode_needs_a_call_and_locks_it_with_the_session(reading, no_walrus):
    with pytest.raises(sessions.SessionError):
        _open("own")
    assert balance() == 3  # nothing charged
    ps = _open("own", "DOWN")
    with get_session() as s:
        pick = s.get(Pick, ps.pick_id)
    assert pick.direction == "DOWN" and pick.mode == "own" and pick.agrees_with_model is False
    assert balance() == 2  # the call is included in the session


def test_model_mode_call_is_free_and_records_agreement(reading, no_walrus):
    ps = sessions.lock_call(ADDR, _open().id, "UP")
    with get_session() as s:
        pick = s.get(Pick, ps.pick_id)
    assert pick.mode == "model" and pick.model_p == 0.56 and pick.agrees_with_model is True
    assert balance() == 2
    with pytest.raises(sessions.SessionError):
        sessions.lock_call(ADDR, ps.id, "DOWN")  # one call per session


def test_one_call_per_asset_per_window(reading, no_walrus):
    _open("own", "UP")
    with pytest.raises(sessions.SessionError):
        _open("own", "UP")
    assert balance() == 2  # the rejected session was not charged
    _open("own", "UP", asset="SUI")  # a different asset is fine


def test_no_reading_means_no_charge(temp_db, no_walrus):
    with pytest.raises(LookupError):
        _open()
    assert balance() == 3


def test_stale_reading_is_not_charged(reading, no_walrus, monkeypatch):
    monkeypatch.setattr(picks, "last_closed_hour", lambda: reading + 3 * HOUR_MS)
    with pytest.raises(LookupError):
        _open()
    assert balance() == 3
    monkeypatch.setattr(picks, "last_closed_hour", lambda: reading)
    _open()
    assert balance() == 2


def test_right_call_pays_two_and_is_remembered_in_user_namespace(reading, no_walrus, monkeypatch):
    ps = _open("own", "UP")
    assert _resolve(monkeypatch, ps.slot_t, start=1.0, end=1.1) == 1
    assert balance() == 4  # 3 - 1 + 2
    namespace, kind, text = no_walrus[0]
    assert namespace == picks.user_namespace(ADDR) and ADDR not in namespace
    assert kind == "USER_EPISODE" and "result=WON" in text and "agreed=True" in text


def test_wrong_call_returns_nothing(reading, no_walrus, monkeypatch):
    ps = _open("own", "UP")
    _resolve(monkeypatch, ps.slot_t, start=1.0, end=1.0)  # flat counts as DOWN_OR_FLAT
    assert balance() == 2
    with get_session() as s:
        assert s.get(Pick, ps.pick_id).status == "LOST"


def test_unresolvable_call_is_refunded(reading, no_walrus, monkeypatch):
    ps = _open("own", "DOWN")
    monkeypatch.setattr(picks, "last_closed_hour", lambda: ps.slot_t + 40 * HOUR_MS)
    picks.resolve_picks(lambda asset, open_time: None)
    assert balance() == 3
    with get_session() as s:
        assert s.get(Pick, ps.pick_id).status == "REFUNDED"


def test_invalid_direction_and_mode_are_rejected(reading, no_walrus):
    with pytest.raises(sessions.SessionError):
        _open("own", "SIDEWAYS")
    with pytest.raises(sessions.SessionError):
        _open("both")
    assert balance() == 3  # never charged
    assert sessions.list_sessions(ADDR) == []  # and no session was left behind


def test_failed_open_leaves_no_free_session(reading, no_walrus, monkeypatch):
    def fail(*args, **kwargs):
        raise picks.PickError("window started")
    monkeypatch.setattr(picks, "place_pick", fail)
    with pytest.raises(picks.PickError):
        _open("own", "UP")
    assert balance() == 3  # refunded
    assert sessions.list_sessions(ADDR) == []  # the refunded session cannot be used


def test_questions_are_limited_per_session(reading, no_walrus, monkeypatch):
    monkeypatch.setattr(sessions.agent, "session_answer", lambda q, facts, history: {"text": "ok", "by": "llm"})
    monkeypatch.setattr(sessions.engine, "market_context", lambda asset, t: {})
    ps = _open()
    for _ in range(sessions.MAX_MESSAGES):
        out = sessions.ask(ADDR, ps.id, "why?")
    assert out["questions_left"] == 0 and balance() == 2  # questions do not cost extra credits
    with pytest.raises(sessions.SessionError):
        sessions.ask(ADDR, ps.id, "one more?")
    assert len(sessions.messages_of(ps.id)) == 2 * sessions.MAX_MESSAGES


def test_sessions_are_private(reading, no_walrus):
    ps = _open()
    with pytest.raises(LookupError):
        sessions.get_owned("0x" + "cd" * 32, ps.id)


def test_session_facts_include_call_reading_and_history(reading, no_walrus, monkeypatch):
    monkeypatch.setattr(sessions.engine, "market_context", lambda asset, t: {"move_4h_pct": 1.2, "drivers": []})
    ps = _open("own", "UP")
    facts = sessions.build_facts(ps)
    assert facts["your_call"]["direction"] == "UP" and facts["your_call"]["agrees_with_model"] is True
    assert facts["model_reading"]["recall_p_up"] == 0.56 and facts["market"] == {"move_4h_pct": 1.2}
    assert "SUI" in facts["other_assets"] and "WAL" not in facts["other_assets"]
    assert facts["your_history"]["total"]["calls"] == 0


def test_personal_record_splits_agreeing_and_disagreeing_calls(monkeypatch):
    def episode(result, agreed):
        data = {"type": "user_episode", "asset": "WAL", "result": result, "mode": "model",
                "regime": {"vol": "high"}, "model": {"p": 0.6, "action": "ADJUSTED", "agreed": agreed}}
        return {"blob_id": "b", "text": "[USER_EPISODE] WAL\nDATA " + json.dumps(data)}

    rows = [episode("WON", True), episode("LOST", True), episode("WON", False)]
    monkeypatch.setattr(sessions.store, "recall", lambda *a, **k: rows)
    total = sessions.personal_record(ADDR)["total"]
    assert total == {"calls": 3, "right": 2, "agreed_calls": 2, "agreed_right": 1, "disagreed_calls": 1, "disagreed_right": 1}


def test_personal_message_bcs_prefixes_uleb128_length():
    assert auth.personal_message_bcs(b"hi") == b"\x02hi"
    assert auth.personal_message_bcs(b"x" * 200)[:2] == b"\xc8\x01"


def test_rejects_malformed_address():
    with pytest.raises(auth.AuthError):
        auth.normalize_address("0x123")


def test_challenge_is_single_use(temp_db, monkeypatch):
    monkeypatch.setattr(auth, "verify_signature", lambda *a: None)
    c = auth.create_challenge(ADDR)
    session = auth.login(ADDR, c["nonce"], "sig")
    assert auth.address_for_token(session["token"]) == ADDR
    with pytest.raises(auth.AuthError):
        auth.login(ADDR, c["nonce"], "sig")


def test_failed_signature_burns_the_challenge(temp_db, monkeypatch):
    def reject(*a):
        raise auth.AuthError("signature rejected")

    monkeypatch.setattr(auth, "verify_signature", reject)
    c = auth.create_challenge(ADDR)
    with pytest.raises(auth.AuthError):
        auth.login(ADDR, c["nonce"], "bad")
    monkeypatch.setattr(auth, "verify_signature", lambda *a: None)
    with pytest.raises(auth.AuthError):
        auth.login(ADDR, c["nonce"], "good")  # cannot retry the same nonce


def test_unknown_token_is_rejected(temp_db):
    with pytest.raises(auth.AuthError):
        auth.address_for_token("nope")


def test_week_of_uses_iso_weeks():
    assert credits.week_of(datetime(2026, 10, 26, tzinfo=timezone.utc)) == "2026-W44"
