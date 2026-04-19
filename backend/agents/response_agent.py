"""nexaagent/backend/agents/response_agent.py â€” Final response generation with KB grounding."""
from __future__ import annotations
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import AsyncGroq
from ..config import settings
from .state import AgentState

logger = structlog.get_logger(__name__)

_SYSTEM = """You are a helpful, professional customer support assistant for NexaAgent.
- Answer concisely: 2-4 short paragraphs max
- Use KB context to ground your answer; if it doesn't apply, say so
- Never make up pricing, policies, or specs
- Warm, empathetic tone â€” especially for frustrated customers
- No filler phrases like "Great question!"
- Plain text only"""


def _kb_context(state: AgentState) -> str:
    docs = state.get("kb_results", [])
    if not docs:
        return "No knowledge base articles retrieved."
    return "\n\n".join(
        f"[KB {i} â€” {d.title} (score:{d.relevance_score:.2f})]\n{d.content[:800]}"
        for i, d in enumerate(docs[:3], 1)
    )


def _build_messages(state: AgentState) -> list[dict]:
    ir = state.get("intent_result")
    ctx = ""
    if ir:
        ctx = f"Intent: {ir.intent} | Sentiment: {ir.sentiment_label} ({ir.sentiment_score:.2f}) | Urgency: {ir.urgency}"
    system = f"{_SYSTEM}\n\n--- KB Context ---\n{_kb_context(state)}\n\n--- Customer Context ---\n{ctx}"
    msgs = [{"role": "system", "content": system}]
    if state.get("history_summary"):
        msgs.append({"role": "system", "content": f"[Earlier summary: {state['history_summary']}]"})
    for m in (state.get("history") or [])[-10:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": state["message"]})
    return msgs


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
async def _call_groq(messages: list[dict]) -> str:
    c = await AsyncGroq(api_key=settings.groq_api_key).chat.completions.create(
        model=settings.groq_model, temperature=settings.groq_temperature,
        max_tokens=settings.groq_max_tokens, messages=messages,
    )
    return c.choices[0].message.content.strip()


async def run_response_agent(state: AgentState) -> AgentState:
    try:
        state["final_response"] = await _call_groq(_build_messages(state))
        logger.info("response_agent.ok", len=len(state["final_response"]))
    except Exception as exc:
        logger.error("response_agent.failed", error=str(exc))
        state["final_response"] = (
            "I'm experiencing a temporary issue. Your query has been noted and our team "
            "will follow up. For urgent matters contact support@nexaagent.com."
        )
        state["error"] = f"Response failed: {exc}"
    return state
