"""nexaagent/backend/services/analytics_service.py â€” Metrics aggregation for ops dashboard."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Conversation, HumanAgent, Message, Ticket, TicketStatus
from ..schemas import (AgentPerformance, DashboardMetrics, IntentBreakdown, SentimentBreakdown)


async def get_dashboard_metrics(db: AsyncSession, days: int = 7) -> DashboardMetrics:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total conversations
    r = await db.execute(select(func.count(Conversation.id)).where(Conversation.started_at >= since))
    total_convs = r.scalar() or 0

    # Escalations
    r = await db.execute(select(func.count(Conversation.id))
                         .where(Conversation.started_at >= since, Conversation.status == "escalated"))
    total_esc = r.scalar() or 0

    # Avg resolution time
    r = await db.execute(select(func.avg(Conversation.resolution_time_seconds))
                         .where(Conversation.started_at >= since, Conversation.resolution_time_seconds.isnot(None)))
    avg_res = r.scalar() or 0.0

    # Cache hit rate
    r_total = await db.execute(select(func.count(Message.id)).where(Message.created_at >= since, Message.role == "assistant"))
    r_cached = await db.execute(select(func.count(Message.id)).where(Message.created_at >= since, Message.was_cached == True))
    msg_total = r_total.scalar() or 1
    cache_hit_rate = (r_cached.scalar() or 0) / msg_total

    # Open / claimed tickets
    r = await db.execute(select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.OPEN))
    open_tickets = r.scalar() or 0
    r = await db.execute(select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.CLAIMED))
    claimed_tickets = r.scalar() or 0

    # SLA breach rate
    r_all = await db.execute(select(func.count(Ticket.id)).where(Ticket.created_at >= since))
    r_breach = await db.execute(select(func.count(Ticket.id)).where(Ticket.created_at >= since, Ticket.sla_breach == True))
    t_total = r_all.scalar() or 1
    sla_breach_rate = (r_breach.scalar() or 0) / t_total

    # Avg sentiment
    r = await db.execute(select(func.avg(Message.sentiment_score))
                         .where(Message.created_at >= since, Message.sentiment_score.isnot(None)))
    avg_sentiment = r.scalar() or 0.0

    # Intent breakdown
    r = await db.execute(
        select(Message.intent_label, func.count(Message.id))
        .where(Message.created_at >= since, Message.intent_label.isnot(None))
        .group_by(Message.intent_label)
    )
    intent_breakdown = [
        IntentBreakdown(intent=row[0], count=row[1], escalation_rate=0.0)
        for row in r.all() if row[0]
    ]

    # Sentiment breakdown
    r = await db.execute(
        select(Message.sentiment_label, func.count(Message.id))
        .where(Message.created_at >= since, Message.sentiment_label.isnot(None))
        .group_by(Message.sentiment_label)
    )
    rows = r.all()
    sent_total = sum(row[1] for row in rows) or 1
    sentiment_breakdown = [
        SentimentBreakdown(sentiment_label=row[0], count=row[1], percentage=row[1]/sent_total*100)
        for row in rows if row[0]
    ]

    # Agent performance
    r = await db.execute(select(HumanAgent))
    agents = r.scalars().all()
    agent_perf = [
        AgentPerformance(
            agent_id=a.agent_id, name=a.name,
            total_resolved=a.total_resolved,
            avg_resolution_minutes=0.0,
            sla_breach_rate=0.0,
            current_ticket_count=a.current_ticket_count,
        )
        for a in agents
    ]

    return DashboardMetrics(
        period_days=days,
        total_conversations=total_convs,
        total_escalations=total_esc,
        escalation_rate=total_esc / max(total_convs, 1),
        avg_resolution_time_seconds=avg_res,
        cache_hit_rate=cache_hit_rate,
        sla_breach_rate=sla_breach_rate,
        open_tickets=open_tickets,
        claimed_tickets=claimed_tickets,
        avg_sentiment_score=avg_sentiment,
        intent_breakdown=intent_breakdown,
        sentiment_breakdown=sentiment_breakdown,
        agent_performance=agent_perf,
        daily_volume=[],
    )
