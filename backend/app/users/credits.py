"""Weekly credits. They cannot be bought and have no monetary value."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from app.db import CreditEntry, User, get_session

WEEKLY_FLOOR = 3  # topped up every Monday 00:00 UTC
CAP = 10
SESSION_COST = 1
CALL_REWARD = 2


# Balance changes are read-modify-write; serialise them (single process).
_balance_lock = threading.RLock()


class InsufficientCredits(Exception):
    pass


def week_of(now: datetime | None = None) -> str:
    year, week, _ = (now or datetime.now(timezone.utc)).isocalendar()
    return f"{year}-W{week:02d}"


def _apply(session, user: User, delta: int, reason: str, ref: dict | None = None) -> int:
    new_balance = min(user.credits + delta, CAP)
    applied = new_balance - user.credits
    user.credits = new_balance
    session.add(user)
    session.add(CreditEntry(address=user.address, delta=applied, balance=new_balance, reason=reason, ref=ref or {}))
    return applied


def get_user(address: str) -> User:
    """Creates the user on first sight and applies the weekly refill."""
    with _balance_lock, get_session() as session:
        user = session.get(User, address)
        if user is None:
            user = User(address=address, week=week_of())
            _apply(session, user, WEEKLY_FLOOR, "signup")
        elif user.week != week_of():
            user.week = week_of()
            if user.credits < WEEKLY_FLOOR:
                _apply(session, user, WEEKLY_FLOOR - user.credits, "weekly_refill")
            session.add(user)
        session.commit()
        session.refresh(user)
        return user


def spend(address: str, amount: int, reason: str, ref: dict | None = None) -> int:
    get_user(address)
    with _balance_lock, get_session() as session:
        user = session.get(User, address)
        if user.credits < amount:
            raise InsufficientCredits(f"needs {amount} credit(s), has {user.credits}")
        _apply(session, user, -amount, reason, ref)
        session.commit()
        return user.credits


def grant(address: str, amount: int, reason: str, ref: dict | None = None) -> int:
    with _balance_lock, get_session() as session:
        user = session.get(User, address)
        _apply(session, user, amount, reason, ref)
        session.commit()
        return user.credits
