"""
nexaagent/backend/agents/intent_agent.py
Classifies intent, sentiment, urgency via Groq structured JSON + rule overrides.
"""
from __future__ import annotations
import json
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential
from groq import AsyncGroq
from ..config import settings
from ..schemas import IntentResult
from .state import AgentState

logger = structlog.get_logger(__name__)

_FRUSTRATION_MARKERS = frozenset([
    "ridiculous","unacceptable","useless","terrible","worst","disgusting",
    "awful","outrageous","scam","fraud","never again","lawsuit","legal action",
    "pathetic","incompetent",
])
_HIGH_URGENCY_MARKERS = frozenset([
    "urgent","immediately","asap","right now","emergency","broken","lost money",
    "cant access","cannot access","account locked","billing error","charge",
    "overcharged","data loss","security breach",
])

_SYSTEM = """You are an expert customer support intent classifier.
Return ONLY valid JSON, no markdown, no explanation.

Intent options: billing_inquiry, technical_support, refund_request,
account_issue, general_inquiry, complaint, escalation_request

Sentiment: score -1.0 to 1.0
  POSITIVE > 0.6 | NEUTRAL -0.6 to 0.6 | NEGATIVE -0.8 to -0.6 | FRUSTRATED < -0.8

Urgency:
  HIGH: urgent/immediately/broken/lost money/cant access/escalation_request
  MEDIUM: complaints, repeated issues
  LOW: informational

Return exactly:
{"intent":"...","confidence":0.0,"sentiment_score":0.0,"sentiment_label":"...","urgency":"...","is_repeat_contact":false,"escalation_recommended":false,"escalation_reason":null}"""


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10), reraise=True)
async def _call_groq(client: AsyncGroq, message: str, context: str) -> dict:
    c = await client.chat.completions.create(
        model=settings.groq_model, temperature=0.1, max_tokens=256,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Context:\n{context}\n\nMessage:\n{message}"},
        ],
    )
    return json.loads(c.choices[0].message.content)


def _apply_overrides(result: IntentResult, message: str) -> IntentResult:
    msg = message.lower()
    if any(m in msg for m in _FRUSTRATION_MARKERS):
        result = result.model_copy(update={
            "sentiment_label": "FRUSTRATED",
            "sentiment_score": min(result.sentiment_score, -0.85),
            "escalation_recommended": True,
            "escalation_reason": result.escalation_reason or "Frustration markers detected",
        })
    if any(m in msg for m in _HIGH_URGENCY_MARKERS):
        result = result.model_copy(update={
            "urgency": "HIGH",
            "escalation_recommended": True,
            "escalation_reason": result.escalation_reason or "High-urgency language detected",
        })
    if result.intent == "escalation_request":
        result = result.model_copy(update={
            "escalation_recommended": True, "urgency": "HIGH",
            "escalation_reason": "Customer explicitly requested human agent",
        })
    return result


async def run_intent_agent(state: AgentState) -> AgentState:
    history = state.get("history", [])
    context = "\n".join(f"{m['role'].upper()}: {m['content'][:200]}" for m in history[-6:]) or "No prior context."
    client = AsyncGroq(api_key=settings.groq_api_key)
    try:
        raw = await _call_groq(client, state["message"], context)
        raw["is_repeat_contact"] = state.get("total_turns", 0) > 3
        result = _apply_overrides(IntentResult(**raw), state["message"])
        logger.info("intent_agent.ok", intent=result.intent, sentiment=result.sentiment_label, urgency=result.urgency)
    except Exception as exc:
        logger.error("intent_agent.failed", error=str(exc))
        result = IntentResult(intent="general_inquiry", confidence=0.0, sentiment_score=0.0,
                              sentiment_label="NEUTRAL", urgency="LOW")
        state["error"] = f"Intent failed: {exc}"
    state["intent_result"] = result
    return state
