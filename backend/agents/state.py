"""nexaagent/backend/agents/state.py â€” LangGraph AgentState TypedDict."""
from __future__ import annotations
from typing import Optional
from typing_extensions import TypedDict
from ..schemas import IntentResult, KBRetrievalResult


class AgentState(TypedDict, total=False):
    # Input
    user_id: str
    conversation_id: str
    message: str
    user_tier: str

    # Memory
    history: list[dict[str, str]]
    history_summary: Optional[str]
    total_turns: int

    # Intent agent
    intent_result: Optional[IntentResult]

    # Cache
    cache_key: Optional[str]
    cache_hit: bool
    cached_response: Optional[str]

    # RAG
    kb_results: list[KBRetrievalResult]
    kb_confidence: float

    # Response
    final_response: Optional[str]

    # Escalation
    should_escalate: bool
    escalation_reason: Optional[str]
    escalation_trigger: Optional[str]
    ticket_id: Optional[str]

    # Meta
    error: Optional[str]
    response_time_ms: int
    was_cached: bool
    _start_ms: int
