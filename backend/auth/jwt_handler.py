"""
nexaagent/backend/auth/jwt_handler.py
JWT creation and validation for users and agents.
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from jose import JWTError, jwt
from ..config import settings


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_user_token(user_id: str, tier: str) -> str:
    expire = _now_utc() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "role": "user", "tier": tier, "exp": expire, "iat": _now_utc()},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )


def create_agent_token(agent_id: str) -> str:
    expire = _now_utc() + timedelta(minutes=settings.jwt_agent_token_expire_minutes)
    return jwt.encode(
        {"sub": agent_id, "role": "agent", "exp": expire, "iat": _now_utc()},
        settings.jwt_secret_key, algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def token_expires_in(token: str) -> int:
    payload = decode_token(token)
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    return max(0, int((exp - _now_utc()).total_seconds()))
