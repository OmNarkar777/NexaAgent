"""
nexaagent/backend/auth/dependencies.py
FastAPI JWT auth dependencies: get_current_user, get_current_agent.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import HumanAgent, User
from .jwt_handler import decode_token

bearer_scheme = HTTPBearer(auto_error=True)

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("role") != "user":
            raise _401
        user_id: str = payload["sub"]
    except (JWTError, KeyError):
        raise _401

    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _401
    return user


async def get_current_agent(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> HumanAgent:
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("role") != "agent":
            raise _401
        agent_id: str = payload["sub"]
    except (JWTError, KeyError):
        raise _401

    result = await db.execute(select(HumanAgent).where(HumanAgent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        raise _401
    return agent
