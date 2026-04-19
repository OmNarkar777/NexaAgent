"""nexaagent/backend/services/queue_service.py â€” Queue business logic and SLA monitoring."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Ticket, TicketStatus
from ..config import settings


async def check_sla_breaches(db: AsyncSession) -> int:
    """Mark tickets that have exceeded SLA. Returns count of newly breached tickets."""
    now = datetime.now(timezone.utc)
    breached = 0
    r = await db.execute(
        select(Ticket).where(Ticket.status.in_([TicketStatus.OPEN, TicketStatus.CLAIMED]),
                             Ticket.sla_breach == False)
    )
    for ticket in r.scalars().all():
        sla_mins = settings.sla_minutes.get(ticket.priority, 1440)
        if (now - ticket.created_at).total_seconds() / 60 > sla_mins:
            ticket.sla_breach = True
            breached += 1
    if breached:
        await db.commit()
    return breached


async def get_queue_stats(db: AsyncSession) -> dict:
    from sqlalchemy import func
    r = await db.execute(
        select(Ticket.priority, Ticket.status, func.count(Ticket.id))
        .where(Ticket.status.in_([TicketStatus.OPEN, TicketStatus.CLAIMED]))
        .group_by(Ticket.priority, Ticket.status)
    )
    stats = {}
    for priority, status, count in r.all():
        stats.setdefault(priority, {})[status] = count
    return stats
