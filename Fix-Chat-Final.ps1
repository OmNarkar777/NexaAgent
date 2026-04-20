# Write dependencies.py
$dep = @"
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import HumanAgent, User
from .jwt_handler import decode_token

bearer_scheme = HTTPBearer(auto_error=False)
_401 = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})

def _get_raw(credentials, token_query):
    if credentials and credentials.credentials:
        return credentials.credentials
    if token_query:
        return token_query
    raise _401

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    raw = _get_raw(credentials, token)
    try:
        payload = decode_token(raw)
        if payload.get("role") != "user": raise _401
        user_id = payload["sub"]
    except (JWTError, KeyError): raise _401
    result = await db.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active: raise _401
    return user

async def get_current_agent(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> HumanAgent:
    raw = _get_raw(credentials, token)
    try:
        payload = decode_token(raw)
        if payload.get("role") != "agent": raise _401
        agent_id = payload["sub"]
    except (JWTError, KeyError): raise _401
    result = await db.execute(select(HumanAgent).where(HumanAgent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if agent is None: raise _401
    return agent
"@
Set-Content "backend\auth\dependencies.py" $dep -Encoding UTF8

# Write chat.py
$chat = @"
from __future__ import annotations
import asyncio, json, time, uuid
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from ..database import get_db, get_redis
from ..models import User
from ..schemas import ChatRequest, ChatResponse
from ..auth.dependencies import get_current_user
from ..services.chat_service import process_chat

router = APIRouter(prefix="/chat", tags=["chat"])

@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    return await process_chat(user=user, message=body.message, conversation_id=body.conversation_id, db=db, redis=redis)

@router.get("/stream")
async def chat_stream(
    message: str = Query(...),
    conversation_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    async def generate():
        from ..agents.graph import build_graph
        from ..agents.state import AgentState
        from ..memory.conversation import ConversationMemory
        from ..queue.ticket_queue import TicketQueue
        from ..queue.pubsub import TicketPubSub

        memory = ConversationMemory(db)
        conv_id = conversation_id or str(uuid.uuid4())
        conv = await memory.get_or_create(conv_id, user.user_id)
        history, summary = await memory.get_context_for_llm(conv_id)
        await memory.add_message(conv_id, "user", message)

        state: AgentState = {
            "user_id": user.user_id, "conversation_id": conv_id,
            "message": message, "user_tier": user.tier,
            "history": history, "history_summary": summary,
            "total_turns": conv.total_messages, "kb_results": [],
            "kb_confidence": 0.0, "cache_hit": False, "was_cached": False,
            "should_escalate": False, "response_time_ms": 0,
        }

        tq = TicketQueue(redis, db)
        ps = TicketPubSub(redis)
        compiled = build_graph(redis, db, tq, ps)
        cfg = {"configurable": {"thread_id": conv_id}}
        start = time.monotonic()

        async for event in compiled.astream(state, config=cfg, stream_mode="updates"):
            node = list(event.keys())[0]
            ns = event[node]
            if node == "intent_agent" and ns.get("intent_result"):
                ir = ns["intent_result"]
                yield "data: " + json.dumps({"event": "intent_classified", "intent": ir.intent, "sentiment": ir.sentiment_label, "urgency": ir.urgency}) + "\n\n"
            elif node == "rag_agent":
                yield "data: " + json.dumps({"event": "kb_retrieved", "n_docs": len(ns.get("kb_results", [])), "confidence": ns.get("kb_confidence", 0)}) + "\n\n"
            elif node == "escalation_agent" and ns.get("ticket_id"):
                yield "data: " + json.dumps({"event": "escalated", "ticket_id": ns["ticket_id"], "priority": "HIGH"}) + "\n\n"

        final_state = compiled.get_state(cfg).values
        response_text = final_state.get("final_response", "")

        words = response_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield "data: " + json.dumps({"event": "token", "text": chunk}) + "\n\n"
            await asyncio.sleep(0.02)

        elapsed = int((time.monotonic() - start) * 1000)
        yield "data: " + json.dumps({"event": "done", "conversation_id": conv_id, "response_time_ms": elapsed}) + "\n\n"

        await memory.add_message(conv_id, "assistant", response_text, metadata={"response_time_ms": elapsed, "was_cached": final_state.get("was_cached", False)})

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
"@
Set-Content "backend\routers\chat.py" $chat -Encoding UTF8

Write-Host "Files written. Restarting backend..." -ForegroundColor Green
docker restart nexaagent_backend
Start-Sleep 20
docker logs nexaagent_backend --tail 10
Write-Host ""
Write-Host "Open http://localhost:3000 and type a message" -ForegroundColor Cyan
