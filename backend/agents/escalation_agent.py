"""
nexaagent/backend/agents/escalation_agent.py
Evaluates escalation criteria, creates PostgreSQL ticket,
pushes to Redis queue, publishes pub/sub notification.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Conversation, ConversationStatus, EscalationTrigger, Ticket, TicketPriority, TicketStatus
from ..queue.ticket_queue import TicketQueue
from ..queue.pubsub import TicketPubSub
from .state import AgentState

logger = structlog.get_logger(__name__)


class EscalationDecision:
    def __init__(self, state: AgentState) -> None:
        self.ir = state.get("intent_result")
        self.tier = state.get("user_tier", "free")
        self.turns = state.get("total_turns", 0)
        self.kb_conf = state.get("kb_confidence", 0.0)

    @property
    def should_escalate(self) -> tuple[bool, str, str]:
        ir = self.ir
        if ir and ir.sentiment_label == "FRUSTRATED":
            return True, "Customer sentiment FRUSTRATED", EscalationTrigger.SENTIMENT
        if ir and ir.urgency == "HIGH":
            return True, ir.escalation_reason or "High urgency", EscalationTrigger.SENTIMENT
        if ir and ir.intent == "escalation_request":
            return True, "Customer requested human agent", EscalationTrigger.EXPLICIT_REQUEST
        if self.turns > settings.escalation_max_turns:
            return True, f"Unresolved after {self.turns} turns", EscalationTrigger.REPEAT_CONTACT
        if self.tier == "enterprise":
            return True, "Enterprise tier priority routing", EscalationTrigger.ENTERPRISE_TIER
        informational = {"general_inquiry", "billing_inquiry"}
        if self.kb_conf > settings.kb_auto_resolve_threshold and ir and ir.intent in informational:
            return False, "", ""
        if ir and ir.escalation_recommended:
            return True, ir.escalation_reason or "AI recommended escalation", EscalationTrigger.COMPLEXITY
        return False, "", ""

    @property
    def priority(self) -> str:
        ir = self.ir
        if not ir:
            return TicketPriority.MEDIUM
        if self.tier == "enterprise" or ir.sentiment_label == "FRUSTRATED":
            return TicketPriority.CRITICAL
        if ir.urgency == "HIGH" or ir.intent in ("refund_request", "escalation_request"):
            return TicketPriority.HIGH
        if ir.urgency == "MEDIUM" or ir.intent == "complaint":
            return TicketPriority.MEDIUM
        return TicketPriority.LOW


async def run_escalation_agent(
    state: AgentState, db: AsyncSession,
    ticket_queue: TicketQueue, pubsub: TicketPubSub,
) -> AgentState:
    decision = EscalationDecision(state)
    escalate, reason, trigger = decision.should_escalate

    if not escalate:
        state["should_escalate"] = False
        return state

    priority = decision.priority
    ticket_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    ticket = Ticket(
        ticket_id=ticket_id,
        conversation_id=state["conversation_id"],
        user_id=state["user_id"],
        status=TicketStatus.OPEN,
        priority=priority,
        escalation_reason=reason,
        escalation_trigger=trigger,
        created_at=now,
        sla_breach=False,
    )
    db.add(ticket)

    from sqlalchemy import update
    await db.execute(
        update(Conversation)
        .where(Conversation.conversation_id == state["conversation_id"])
        .values(status=ConversationStatus.ESCALATED, escalated_at=now)
    )
    await db.commit()

    try:
        await ticket_queue.push(
            ticket_id=ticket_id, priority=priority,
            conversation_id=state["conversation_id"],
            user_id=state["user_id"], escalation_reason=reason,
            user_tier=state.get("user_tier", "free"),
        )
    except Exception as exc:
        logger.error("queue_push_failed", error=str(exc), ticket_id=ticket_id)

    try:
        await pubsub.publish_new_ticket(ticket_id, priority, state["conversation_id"])
    except Exception as exc:
        logger.error("pubsub_failed", error=str(exc))

    short = ticket_id.split("-")[0].upper()
    wait = {"CRITICAL":"within 15 min","HIGH":"within 1 hr","MEDIUM":"within 4 hrs","LOW":"within 24 hrs"}.get(priority,"soon")

    state["should_escalate"] = True
    state["ticket_id"] = ticket_id
    state["escalation_reason"] = reason
    state["escalation_trigger"] = trigger
    state["final_response"] = (
        f"I've connected you with our support team who can better assist you. "
        f"A specialist will reach out {wait}.\n\nTicket: **#{short}**\n\n"
        f"You'll receive email updates. Reference #{short} for urgent follow-up."
    )

    logger.info("escalation.ticket_created", ticket_id=ticket_id, priority=priority)
    return state
