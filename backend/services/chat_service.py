"""nexaagent/backend/services/chat_service.py â€” Full chat pipeline orchestration."""
from __future__ import annotations
import time, uuid
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from ..agents.graph import run_graph
from ..agents.state import AgentState
from ..memory.conversation import ConversationMemory
from ..models import User
from ..queue.ticket_queue import TicketQueue
from ..queue.pubsub import TicketPubSub
from ..schemas import ChatResponse

logger = structlog.get_logger(__name__)


async def process_chat(
    user: User, message: str, conversation_id: str | None,
    db: AsyncSession, redis: aioredis.Redis,
) -> ChatResponse:
    start = time.monotonic()
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

    result = await run_graph(state, redis, db, TicketQueue(redis), TicketPubSub(redis))
    elapsed = int((time.monotonic() - start) * 1000)
    ir = result.get("intent_result")

    await memory.add_message(conv_id, "assistant", result.get("final_response", ""), metadata={
        "intent_label": ir.intent if ir else None,
        "intent_confidence": ir.confidence if ir else None,
        "sentiment_score": ir.sentiment_score if ir else None,
        "sentiment_label": ir.sentiment_label if ir else None,
        "response_time_ms": elapsed,
        "was_cached": result.get("was_cached", False),
    })

    return ChatResponse(
        conversation_id=conv_id,
        message_id=str(uuid.uuid4()),
        response=result.get("final_response", ""),
        intent=ir.intent if ir else "unknown",
        sentiment_label=ir.sentiment_label if ir else "NEUTRAL",
        sentiment_score=ir.sentiment_score if ir else 0.0,
        urgency=ir.urgency if ir else "LOW",
        was_escalated=result.get("should_escalate", False),
        ticket_id=result.get("ticket_id"),
        was_cached=result.get("was_cached", False),
        response_time_ms=elapsed,
        kb_sources=result.get("kb_results", []),
    )
