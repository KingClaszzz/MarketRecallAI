"""Input cleaning and output validation for LLM text."""
from __future__ import annotations

import json
import re
import unicodedata

MAX_STRING = 300
MAX_DEPTH = 5
MAX_ITEMS = 30

NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
INJECTION_MARKERS = re.compile(
    r"ignore (all |any )?(previous|prior|above)|system prompt|my instructions|as an ai|developer mode|"
    r"jailbreak|<\s*/?\s*(facts|system)|BEGIN_FACTS|END_FACTS|\binstructions?\b|\bprompt\b",
    re.IGNORECASE,
)
ADVICE = re.compile(
    r"\b(buy|sell|hold|go long|go short|longing|shorting|take profit|stop[- ]loss|position size|leverage|"
    r"guarantee[ds]?|risk[- ]free|sure thing|will (definitely|certainly) (rise|fall|go up|go down)|"
    r"financial advice|investment advice|you should invest|"
    r"beli|jual|borong|serok|pasti (naik|turun|untung)|dijamin|tanpa risiko|saran investasi|nasihat keuangan)\b",
    re.IGNORECASE,
)
# Matched before the LLM is called; these get a fixed reply.
ADVICE_REQUEST = re.compile(
    r"\b(should|shall|do|can|would you)\b.{0,40}\b(buy|sell|hold|long|short|invest|enter|exit|ape)\b|"
    r"price target|target price|how much (should|to) (buy|invest)|tell me (what|when) to (buy|sell)|"
    r"(harus|sebaiknya|mending|layak|boleh)\b.{0,40}\b(beli|jual|hold|masuk|keluar|invest)|target harga|"
    r"guarantee|pasti (naik|turun|untung)|dijamin",
    re.IGNORECASE,
)
INJECTION_REQUEST = re.compile(
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,30}\b(previous|prior|above|earlier|rules?|instructions?|guidelines?|"
    r"restrictions?|everything)|system prompt|system message|your (instructions|prompt|rules|guidelines|configuration)|"
    r"(repeat|print|show|output|translate|summari[sz]e)\b.{0,30}\b(above|everything before|your (rules|instructions|prompt))|"
    r"what (were|are) you (told|instructed)|new (instructions|rules|persona)|you are now|from now on|"
    r"developer mode|dan mode|jailbreak|pretend (to be|you are)|act as|role-?play|reveal|api[ _-]?key|private key|"
    r"seed phrase|recovery phrase|mnemonic|^\s*(system|assistant)\s*:|BEGIN_FACTS|END_FACTS|"
    r"abaikan\b|lupakan (semua|aturan|instruksi|perintah)|instruksi (baru|sebelumnya)|aturan (baru|sebelumnya)|"
    r"mulai sekarang|kamu sekarang( adalah)?|berpura-?pura|perintah sistem|tampilkan (prompt|instruksi|aturan)",
    re.IGNORECASE | re.MULTILINE,
)
SECRET_LIKE = re.compile(r"\bsk-[A-Za-z0-9]{8,}|\b0x[0-9a-fA-F]{20,}|\b[0-9a-fA-F]{40,}\b|suiprivkey")
URL = re.compile(
    r"https?://|www\.|\b[a-z0-9-]+\.(com|net|org|io|app|xyz|finance|fi|site|online|link|co|me|gg|ai|dev|"
    r"top|click|info|live|pro|cc|to|sh|ly|id|claims?|airdrop)\b",
    re.IGNORECASE,
)
WALLET_SCAM = re.compile(
    r"seed phrase|recovery phrase|mnemonic|private key|secret key|connect your wallet to|"
    r"(send|transfer|deposit)\b.{0,20}\b(sui|wal|cetus|usdc|tokens?|funds|coins?)\b|airdrop|claim (your|free|now)|"
    r"frasa (pemulihan|rahasia)|kunci privat|(kirim|transfer|setor)\b.{0,20}\b(sui|wal|cetus|token|dana|koin)\b",
    re.IGNORECASE,
)
FORMATTING = re.compile(r"```|^\s*#|^\s*[-*]\s", re.MULTILINE)


def _clean_string(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if ch.isprintable() or ch == " ")
    s = s.replace("<", "(").replace(">", ")").replace("BEGIN_FACTS", "").replace("END_FACTS", "")
    return s[:MAX_STRING]


def sanitize(obj, depth: int = 0):
    if depth > MAX_DEPTH:
        return "[truncated]"
    if isinstance(obj, dict):
        return {_clean_string(str(k))[:60]: sanitize(v, depth + 1) for k, v in list(obj.items())[:MAX_ITEMS]}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v, depth + 1) for v in list(obj)[:MAX_ITEMS]]
    if isinstance(obj, str):
        return _clean_string(obj)
    if isinstance(obj, float):
        return round(obj, 4)
    return obj


def clean_question(text: str, limit: int = MAX_STRING) -> str:
    return _clean_string(" ".join(text[: limit * 2].split()))[:limit]


def facts_block(facts: dict) -> str:
    return "BEGIN_FACTS\n" + json.dumps(facts, default=float, ensure_ascii=False) + "\nEND_FACTS"


def _allowed_numbers(facts: dict, extra_text: str = "") -> set[str]:
    out = {"0", "1", "2", "3", "4", "10", "24", "50", "0.5", "0.25", "25"}  # used in the product knowledge
    for n in NUMBER.findall(json.dumps(facts, ensure_ascii=False) + " " + extra_text):
        out.add(n.lstrip("-"))  # e.g. the "00" of "14:00"
        x = abs(float(n))
        out |= {f"{x:g}", f"{x:.0f}", f"{x:.1f}", f"{x:.2f}", f"{x:.3f}", f"{x:.4f}"}
        out |= {f"{x * 100:.0f}", f"{x * 100:.1f}", f"{x * 100:.2f}"}  # as a percentage
    return out


WRITTEN_NUMBER = re.compile(r"(?<![\w.,])-?\d+(?:[.,]\d+)*")


def _readings(n: str) -> set[str]:
    out = {n, n.replace(",", "."), n.replace(",", ""), n.replace(".", ""), n.replace(".", "").replace(",", ".")}
    return {x for x in out if x.count(".") <= 1}


def validate(text: str, facts: dict, max_words: int, question: str = "") -> list[str]:
    """Reasons to reject `text` (empty if it is fine). Numbers must come from the facts or the question."""
    problems = []
    if not text.strip():
        return ["empty"]
    if len(text.split()) > max_words * 1.3:
        problems.append("too long")
    allowed = _allowed_numbers(facts, question)
    # Indonesian writes 0,51 for 0.51 and 1.530 for 1530.
    invented = [n for n in WRITTEN_NUMBER.findall(text)
                if not any(c in allowed or c.lstrip("-") in allowed for c in _readings(n))]
    if invented:
        problems.append(f"numbers not in facts: {invented[:5]}")
    for name, pattern in (("injection marker", INJECTION_MARKERS), ("advice or guarantee", ADVICE),
                          ("secret-like string", SECRET_LIKE), ("url", URL), ("wallet scam", WALLET_SCAM),
                          ("formatting", FORMATTING)):
        # "this is not financial advice" is fine
        checked = DISCLAIMER.sub(" ", text) if pattern is ADVICE else text
        if pattern.search(checked):
            problems.append(name)
    return problems


DISCLAIMER = re.compile(
    r"\b(not|never|no|don't|do not|doesn't|does not|cannot|can't|won't|isn't|is not)\b[^.]{0,40}?"
    r"\b((financial|investment|trading) advice|(buy|sell|buy or sell|buying or selling)\b[^.]{0,15}?\badvice|guarantee[ds]?)\b|"
    r"\b(bukan|tidak|tanpa|jangan)\b[^.]{0,30}?\b(saran (keuangan|investasi)|nasihat keuangan|saran (beli|jual)|dijamin)",
    re.IGNORECASE,
)
