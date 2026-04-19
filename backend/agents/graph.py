"""
nexaagent/backend/agents/graph.py
LangGraph orchestration: intent â†’ cache_check â†’ [cached|escalate|rag] â†’ response â†’ cache_store
interrupt_before=["escalation_agent"] enables human-in-the-loop review.
"""
from __future__ import annotations
import hashlib, time
import redis.asyncio as aioredis
import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from .state import AgentState
from .intent_agent import run_intent_agent
from .rag_agent import run_rag_agent
from .response_agent import run_response_agent
from .escalation_agent import run_escalation_agent
from ..queue.ticket_queue import TicketQueue
from ..queue.pubsub import TicketPubSub

logger = structlog.get_logger(__name__)


def _cache_key(state: AgentState) -> str:
    intent = state["intent_result"].intent if state.get("intent_result") else ""
    normalised = " ".join(state.get("message","").lower().split())
    return f"nexaagent:cache:{hashlib.sha256(f'{intent}::{normalised}'.encode()).hexdigest()}"


async def node_intent(state: AgentState) -> AgentState:
    state["_start_ms"] = int(time.time() * 1000)
    return await run_intent_agent(state)


async def node_check_cache(state: AgentState, redis: aioredis.Redis) -> AgentState:
    key = _cache_key(state)
    state.update({"cache_key": key, "cache_hit": False, "was_cached": False})
    try:
        cached = await redis.get(key)
        if cached:
            state.update({"cache_hit": True, "was_cached": True, "cached_response": cached})
    except Exception as exc:
        logger.error("cache.check_failed", error=str(exc))
    return state


async def node_serve_cached(state: AgentState) -> AgentState:
    state["final_response"] = state.get("cached_response", "")
    state["should_escalate"] = False
    return state


async def node_escalation(state: AgentState, db: AsyncSession, tq: TicketQueue, ps: TicketPubSub) -> AgentState:
    return await run_escalation_agent(state, db, tq, ps)


async def node_response(state: AgentState) -> AgentState:
    return await run_response_agent(state)


async def node_cache_response(state: AgentState, redis: aioredis.Redis) -> AgentState:
    ir = state.get("intent_result")
    if state.get("should_escalate"):
        return state
    if ir and ir.sentiment_label in ("NEGATIVE", "FRUSTRATED"):
        return state
    key = state.get("cache_key")
    resp = state.get("final_response", "")
    if key and resp:
        try:
            await redis.setex(key, settings.redis_cache_ttl, resp)
        except Exception as exc:
            logger.error("cache.store_failed", error=str(exc))
    state["response_time_ms"] = int(time.time() * 1000) - state.get("_start_ms", int(time.time() * 1000))
    return state


def route_after_cache(state: AgentState) -> str:
    if state.get("cache_hit"):
        return "serve_cached"
    ir = state.get("intent_result")
    if ir:
        if ir.sentiment_label == "FRUSTRATED": return "escalation_agent"
        if ir.intent == "escalation_request": return "escalation_agent"
        if ir.urgency == "HIGH" and state.get("user_tier") == "enterprise": return "escalation_agent"
    return "rag_agent"


def route_after_rag(state: AgentState) -> str:
    ir = state.get("intent_result")
    if ir and ir.escalation_recommended: return "escalation_agent"
    if state.get("kb_confidence", 0.0) < settings.kb_confidence_threshold: return "escalation_agent"
    return "response_agent"


def build_graph(redis: aioredis.Redis, db: AsyncSession, tq: TicketQueue, ps: TicketPubSub):
    g = StateGraph(AgentState)
    g.add_node("intent_agent", node_intent)
    g.add_node("check_cache",      lambda s: node_check_cache(s, redis))
    g.add_node("serve_cached",     node_serve_cached)
    g.add_node("rag_agent",        run_rag_agent)
    g.add_node("escalation_agent", lambda s: node_escalation(s, db, tq, ps))
    g.add_node("response_agent",   node_response)
    g.add_node("cache_response",   lambda s: node_cache_response(s, redis))

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

    return g.compile(checkpointer=MemorySaver(), interrupt_before=["escalation_agent"])


async def run_graph(
    state: AgentState, redis: aioredis.Redis, db: AsyncSession,
    tq: TicketQueue, ps: TicketPubSub, auto_approve: bool = True,
) -> AgentState:
    compiled = build_graph(redis, db, tq, ps)
    cfg = {"configurable": {"thread_id": state["conversation_id"]}}
    result = await compiled.ainvoke(state, config=cfg)
    if auto_approve:
        snapshot = compiled.get_state(cfg)
        if snapshot.next and "escalation_agent" in snapshot.next:
            result = await compiled.ainvoke(None, config=cfg)
    return result
