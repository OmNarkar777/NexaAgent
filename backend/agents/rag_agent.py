"""nexaagent/backend/agents/rag_agent.py â€” Semantic KB retrieval node."""
from __future__ import annotations
import structlog
from ..rag.retriever import KBRetriever
from .state import AgentState

logger = structlog.get_logger(__name__)
_retriever: KBRetriever | None = None

def _get_retriever() -> KBRetriever:
    global _retriever
    if _retriever is None:
        _retriever = KBRetriever()
    return _retriever

async def run_rag_agent(state: AgentState) -> AgentState:
    ir = state.get("intent_result")
    query = f"[{ir.intent}] {state['message']}" if ir else state["message"]
    try:
        results = await _get_retriever().search(query, n_results=4)
        state["kb_results"] = results
        state["kb_confidence"] = max((r.relevance_score for r in results), default=0.0)
        logger.info("rag_agent.ok", n=len(results), top=state["kb_confidence"])
    except Exception as exc:
        logger.error("rag_agent.failed", error=str(exc))
        state["kb_results"] = []
        state["kb_confidence"] = 0.0
    return state
