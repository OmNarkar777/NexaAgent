"""
nexaagent/backend/routers/chat.py
POST /chat â€” full pipeline
GET  /chat/stream â€” SSE streaming with agent step events
"""
from __future__ import annotations
import asyncio, json, time, uuid
from typing import AsyncGenerator
from fastapi import APIRouter, Depends
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
    return await process_chat(user=user, message=body.message,
                               conversation_id=body.conversation_id, db=db, redis=redis)


@router.get("/stream")
async def chat_stream(
    message: str,
    conversation_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    user: User = Depends(get_current_user),
):
    """
    SSE endpoint. Emits events:
      data: {"event":"intent_classified","intent":"...","sentiment":"..."}
      data: {"event":"kb_retrieved","n_docs":N,"confidence":0.xx}
      data: {"event":"escalated","ticket_id":"..."}
      data: {"event":"token","text":"..."}
      data: {"event":"done","response_time_ms":N}
    """
    async def generate() -> AsyncGenerator[str, None]:
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

        tq = TicketQueue(redis)
        ps = TicketPubSub(redis)
        compiled = build_graph(redis, db, tq, ps)
        cfg = {"configurable": {"thread_id": conv_id}}
        start = time.monotonic()

        async for event in compiled.astream(state, config=cfg, stream_mode="updates"):
            node = list(event.keys())[0]
            node_state = event[node]

            if node == "intent_agent" and node_state.get("intent_result"):
                ir = node_state["intent_result"]
                yield f"data: {json.dumps({'event':'intent_classified','intent':ir.intent,'sentiment':ir.sentiment_label,'urgency':ir.urgency})}\n\n"

            elif node == "rag_agent":
                yield f"data: {json.dumps({'event':'kb_retrieved','n_docs':len(node_state.get('kb_results',[])),'confidence':node_state.get('kb_confidence',0)})}\n\n"

            elif node == "escalation_agent" and node_state.get("ticket_id"):
                yield f"data: {json.dumps({'event':'escalated','ticket_id':node_state['ticket_id']})}\n\n"

        # Stream final response token by token (simulated chunking)
        result = compiled.get_state(cfg).values
        response_text = result.get("final_response", "")
        words = response_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'event':'token','text':chunk})}\n\n"
            await asyncio.sleep(0.02)

        elapsed = int((time.monotonic() - start) * 1000)
        yield f"data: {json.dumps({'event':'done','response_time_ms':elapsed})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream",
                              headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
