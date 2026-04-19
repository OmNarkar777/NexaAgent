"""nexaagent/backend/routers/tickets.py â€” Ticket CRUD + queue operations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from ..database import get_db, get_redis
from ..models import HumanAgent, Ticket
from ..schemas import TicketOut
from ..auth.dependencies import get_current_agent
from ..queue.ticket_queue import TicketQueue

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
async def list_tickets(
    status: str | None = None, priority: str | None = None,
    limit: int = 50, offset: int = 0,
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    q = select(Ticket).order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    if status:   q = q.where(Ticket.status == status.upper())
    if priority: q = q.where(Ticket.priority == priority.upper())
    r = await db.execute(q)
    return r.scalars().all()


@router.get("/queue")
async def get_queue(
    count: int = 20,
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
):
    tq = TicketQueue(redis)
    items = await tq.peek(count)
    depth = await tq.queue_depth()
    return {"queue_depth": depth, "tickets": items}


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db),
                     agent: HumanAgent = Depends(get_current_agent)):
    r = await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
    t = r.scalar_one_or_none()
    if not t: raise HTTPException(404, "Ticket not found")
    return t
