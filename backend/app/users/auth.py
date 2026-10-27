"""Sign-in with a Sui signature (wallet or zkLogin), verified by Tatum's Sui gRPC SignatureVerificationService."""
from __future__ import annotations

import base64
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlmodel import delete

from app.config import get_settings
from app.db import AuthChallenge, AuthSession, get_session
from app.integrations.onchain import get_client
from app.integrations.tracking import tracked

CHALLENGE_TTL = timedelta(minutes=10)
SESSION_TTL = timedelta(days=7)
ADDRESS = re.compile(r"^0x[0-9a-f]{64}$")


class AuthError(Exception):
    pass


def normalize_address(address: str) -> str:
    address = address.strip().lower()
    if not ADDRESS.match(address):
        raise AuthError("invalid Sui address")
    return address


def _uleb128(n: int) -> bytes:
    out = bytearray()
    while True:
        byte, n = n & 0x7F, n >> 7
        out.append(byte | (0x80 if n else 0))
        if not n:
            return bytes(out)


def personal_message_bcs(message: bytes) -> bytes:
    """BCS of a Sui PersonalMessage: vector<u8> = uleb128 length + bytes."""
    return _uleb128(len(message)) + message


def create_challenge(address: str) -> dict:
    address = normalize_address(address)
    nonce = secrets.token_hex(16)
    issued = datetime.now(timezone.utc)
    message = (
        "Sign in to MarketRecall AI\n"
        f"Domain: {get_settings().app_domain}\n"
        f"Address: {address}\n"
        f"Nonce: {nonce}\n"
        f"Issued: {issued.strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        "This request does not cost gas and does not move funds."
    )
    with get_session() as session:
        session.exec(delete(AuthChallenge).where(AuthChallenge.expires_at < issued))
        session.add(AuthChallenge(nonce=nonce, address=address, message=message, expires_at=issued + CHALLENGE_TTL))
        session.commit()
    return {"nonce": nonce, "message": message}


def verify_signature(address: str, message: bytes, signature_b64: str) -> None:
    """Raises AuthError unless the serialized Sui signature signs `message` for `address`."""
    with tracked("tatum_grpc", "SignatureVerificationService.VerifySignature"):
        result = get_client().call("sui.rpc.v2.SignatureVerificationService", "VerifySignature", {
            "message": {"name": "PersonalMessage", "value": base64.b64encode(personal_message_bcs(message)).decode()},
            "signature": {"bcs": {"value": signature_b64}},
            "address": address,
        })
    if not result.get("is_valid"):
        raise AuthError(f"signature rejected: {result.get('reason', 'invalid')}")


def login(address: str, nonce: str, signature_b64: str) -> dict:
    address = normalize_address(address)
    with get_session() as session:
        challenge = session.get(AuthChallenge, nonce)
        if challenge is None or challenge.address != address or challenge.used:
            raise AuthError("unknown or used challenge")
        if challenge.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
            raise AuthError("challenge expired")
        challenge.used = True  # single use, even if verification fails
        session.add(challenge)
        session.commit()
        message = challenge.message
    verify_signature(address, message.encode(), signature_b64)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + SESSION_TTL
    with get_session() as session:
        session.add(AuthSession(token_hash=_hash(token), address=address, expires_at=expires))
        session.commit()
    return {"token": token, "address": address, "expires_at": expires.isoformat()}


def address_for_token(token: str) -> str:
    with get_session() as session:
        s = session.get(AuthSession, _hash(token))
    if s is None or s.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise AuthError("invalid or expired session")
    return s.address


def revoke(token: str) -> None:
    with get_session() as session:
        s = session.get(AuthSession, _hash(token))
        if s is not None:
            session.delete(s)
            session.commit()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
