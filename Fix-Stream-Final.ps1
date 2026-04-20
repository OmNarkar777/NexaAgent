# Write final chat.py that properly handles LangGraph interrupt
$chat = @'
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
    return await process_chat(user=user, message=body.message,
                               conversation_id=body.conversation_id, db=db, redis=redis)

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
        from langgraph.checkpoint.memory import MemorySaver
        from langgraph.graph import END, START, StateGraph
        from ..agents.intent_agent import run_intent_agent
        from ..agents.rag_agent import run_rag_agent
        from ..agents.response_agent import run_response_agent
        from ..agents.escalation_agent import run_escalation_agent
        import hashlib

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
        start = time.monotonic()

        # Build graph WITHOUT interrupt so streaming works end-to-end
        from ..agents.graph import (
            node_intent, node_check_cache, node_serve_cached,
            node_escalation, node_response, node_cache_response,
            route_after_cache, route_after_rag
        )
        from ..config import settings

        g = StateGraph(AgentState)
        g.add_node("intent_agent",    node_intent)
        g.add_node("check_cache",     lambda s: node_check_cache(s, redis))
        g.add_node("serve_cached",    node_serve_cached)
        g.add_node("rag_agent",       run_rag_agent)
        g.add_node("escalation_agent", lambda s: node_escalation(s, db, tq, ps))
        g.add_node("response_agent",  node_response)
        g.add_node("cache_response",  lambda s: node_cache_response(s, redis))
        g.add_edge(START, "intent_agent")
        g.add_edge("intent_agent", "check_cache")
        g.add_conditional_edges("check_cache", route_after_cache,
            {"serve_cached":"serve_cached","escalation_agent":"escalation_agent","rag_agent":"rag_agent"})
        g.add_edge("serve_cached", END)
        g.add_conditional_edges("rag_agent", route_after_rag,
            {"escalation_agent":"escalation_agent","response_agent":"response_agent"})
        g.add_edge("escalation_agent", END)
        g.add_edge("response_agent", "cache_response")
        g.add_edge("cache_response", END)
        # NO interrupt_before - runs fully through
        compiled = g.compile(checkpointer=MemorySaver())
        cfg = {"configurable": {"thread_id": conv_id}}

        async for event in compiled.astream(state, config=cfg, stream_mode="updates"):
            node = list(event.keys())[0]
            ns = event[node]
            if node == "intent_agent" and ns.get("intent_result"):
                ir = ns["intent_result"]
                yield "data: " + json.dumps({"event":"intent_classified","intent":ir.intent,"sentiment":ir.sentiment_label,"urgency":ir.urgency}) + "\n\n"
            elif node == "rag_agent":
                yield "data: " + json.dumps({"event":"kb_retrieved","n_docs":len(ns.get("kb_results",[])),"confidence":ns.get("kb_confidence",0)}) + "\n\n"
            elif node == "escalation_agent" and ns.get("ticket_id"):
                yield "data: " + json.dumps({"event":"escalated","ticket_id":ns["ticket_id"],"priority":"HIGH"}) + "\n\n"

        final_state = compiled.get_state(cfg).values
        response_text = final_state.get("final_response", "")

        if not response_text:
            response_text = "I am here to help. Could you please describe your issue in more detail?"

        words = response_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield "data: " + json.dumps({"event":"token","text":chunk}) + "\n\n"
            await asyncio.sleep(0.02)

        elapsed = int((time.monotonic() - start) * 1000)
        yield "data: " + json.dumps({"event":"done","conversation_id":conv_id,"response_time_ms":elapsed}) + "\n\n"
        await memory.add_message(conv_id, "assistant", response_text,
            metadata={"response_time_ms": elapsed, "was_cached": final_state.get("was_cached", False)})

    return StreamingResponse(generate(), media_type="text/event-stream",
                              headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})
'@
Set-Content "backend\routers\chat.py" $chat -Encoding UTF8
Write-Host "chat.py written" -ForegroundColor Green

docker restart nexaagent_backend
Start-Sleep 20
docker logs nexaagent_backend --tail 5
Write-Host ""
Write-Host "Done! Open http://localhost:3000 and send a message" -ForegroundColor Cyan
