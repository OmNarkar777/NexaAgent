"""nexaagent/backend/routers/auth.py â€” User and agent registration + login."""
from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import HumanAgent, User
from ..schemas import AgentRegister, LoginRequest, TokenResponse, UserRegister
from ..auth.jwt_handler import create_agent_token, create_user_token, token_expires_in

router = APIRouter(prefix="/auth", tags=["auth"])
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/register/user", response_model=TokenResponse, status_code=201)
async def register_user(body: UserRegister, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.email == body.email))
    if r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(email=body.email, hashed_password=pwd.hash(body.password), tier=body.tier)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_user_token(user.user_id, user.tier)
    return TokenResponse(access_token=token, expires_in=token_expires_in(token))


@router.post("/login/user", response_model=TokenResponse)
async def login_user(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(User).where(User.email == body.email))
    user = r.scalar_one_or_none()
    if not user or not pwd.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_user_token(user.user_id, user.tier)
    return TokenResponse(access_token=token, expires_in=token_expires_in(token))


@router.post("/register/agent", response_model=TokenResponse, status_code=201)
async def register_agent(body: AgentRegister, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(HumanAgent).where(HumanAgent.email == body.email))
    if r.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")
    agent = HumanAgent(email=body.email, name=body.name, hashed_password=pwd.hash(body.password))
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    token = create_agent_token(agent.agent_id)
    return TokenResponse(access_token=token, expires_in=token_expires_in(token))


@router.post("/login/agent", response_model=TokenResponse)
async def login_agent(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(HumanAgent).where(HumanAgent.email == body.email))
    agent = r.scalar_one_or_none()
    if not agent or not pwd.verify(body.password, agent.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_agent_token(agent.agent_id)
    return TokenResponse(access_token=token, expires_in=token_expires_in(token))
