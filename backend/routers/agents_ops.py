# backend/routers/agents_ops.py
# Human-agent operations: login, queue, claim, message, resolve, transfer, SSE.
from __future__ import annotations
import asyncio, json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis
from ..auth.dependencies import get_current_agent
from ..auth.jwt_handler import create_agent_token, token_expires_in
from ..database import get_db, get_redis
from ..models import Conversation, HumanAgent, Message, Ticket, TicketStatus
from ..queue.ticket_queue import TicketQueue
from ..queue.pubsub import TicketPubSub
from ..schemas import AgentOut, AgentStatusUpdate, TicketOut, TokenResponse

router   = APIRouter(prefix='/agent', tags=['human-agent'])
pwd      = CryptContext(schemes=['bcrypt'], deprecated='auto')
_now     = lambda: datetime.now(timezone.utc)
SLA_SECS = 4 * 3600


class AgentLogin(BaseModel):
    email: str
    password: str

class AgentMessageBody(BaseModel):
    content: str = Field(min_length=1, max_length=4096)

class ResolveBody(BaseModel):
    resolution_notes: str       = Field(min_length=10, max_length=4096)
    satisfaction_prompted: bool = False

class TransferBody(BaseModel):
    target_agent_id: str
    reason: str | None = None


@router.post('/auth/login', response_model=TokenResponse)
async def agent_login(body: AgentLogin, db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(HumanAgent).where(HumanAgent.email == body.email))
    agent = r.scalar_one_or_none()
    if not agent or not pwd.verify(body.password, agent.hashed_password):
        raise HTTPException(401, 'Invalid credentials')
    token = create_agent_token(agent.agent_id)
    return TokenResponse(access_token=token, expires_in=token_expires_in(token))


@router.get('/queue')
async def get_queue(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
):
    tq    = TicketQueue(redis, db)
    depth = await tq.get_queue_depth()
    items = await tq.list_unclaimed(50)
    previews = []
    for item in items:
        r = await db.execute(select(Ticket).where(Ticket.ticket_id == item['ticket_id']))
        ticket = r.scalar_one_or_none()
        if not ticket:
            continue
        msgs_r = await db.execute(
            select(Message).where(Message.conversation_id == ticket.conversation_id)
            .order_by(Message.created_at.desc()).limit(3)
        )
        msgs = list(reversed(msgs_r.scalars().all()))
        previews.append({
            'ticket_id': ticket.ticket_id, 'priority': ticket.priority,
            'status': ticket.status, 'escalation_reason': ticket.escalation_reason,
            'created_at': ticket.created_at.isoformat(),
            'conversation_preview': [{'role': m.role, 'content': m.content[:200]} for m in msgs],
        })
    return {'depth': depth, 'tickets': previews}


@router.post('/queue/claim')
async def claim_next(
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
):
    from ..config import settings
    if agent.current_ticket_count >= settings.max_agent_tickets:
        raise HTTPException(429, 'At max ticket capacity')
    tq     = TicketQueue(redis, db)
    ticket = await tq.claim_next(agent.agent_id)
    if not ticket:
        raise HTTPException(404, 'No tickets in queue')
    msgs_r = await db.execute(
        select(Message).where(Message.conversation_id == ticket.conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = [
        {'role': m.role, 'content': m.content, 'created_at': m.created_at.isoformat(),
         'intent': m.intent_label, 'sentiment': m.sentiment_label}
        for m in msgs_r.scalars().all()
    ]
    return {'ticket': TicketOut.model_validate(ticket).model_dump(), 'conversation': messages}


@router.post('/tickets/{ticket_id}/message')
async def send_message(
    ticket_id: str, body: AgentMessageBody,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
):
    r = await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
    ticket = r.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, 'Ticket not found')
    if ticket.assigned_agent_id != agent.agent_id:
        raise HTTPException(403, 'Not your ticket')
    msg = Message(conversation_id=ticket.conversation_id, role='agent', content=body.content)
    db.add(msg)
    await db.execute(
        update(Conversation).where(Conversation.conversation_id == ticket.conversation_id)
        .values(total_messages=Conversation.total_messages + 1)
    )
    await db.commit()
    await db.refresh(msg)
    await redis.publish(
        f'conversation:{ticket.conversation_id}',
        json.dumps({'event': 'agent:message', 'content': body.content, 'agent': agent.name}),
    )
    return {'message_id': str(msg.id), 'content': msg.content, 'created_at': msg.created_at.isoformat()}


@router.post('/tickets/{ticket_id}/resolve', response_model=TicketOut)
async def resolve_ticket(
    ticket_id: str, body: ResolveBody,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
):
    r = await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
    ticket = r.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, 'Ticket not found')
    if ticket.assigned_agent_id != agent.agent_id:
        raise HTTPException(403, 'Not your ticket')
    if ticket.status == TicketStatus.RESOLVED:
        raise HTTPException(409, 'Already resolved')
    now                     = _now()
    res_secs                = int((now - ticket.created_at).total_seconds())
    ticket.status           = TicketStatus.RESOLVED
    ticket.resolved_at      = now
    ticket.resolution_notes = body.resolution_notes
    ticket.sla_breach       = res_secs > SLA_SECS
    await db.execute(
        update(Conversation).where(Conversation.conversation_id == ticket.conversation_id)
        .values(status='resolved', ended_at=now, resolution_time_seconds=res_secs)
    )
    await db.execute(
        update(HumanAgent).where(HumanAgent.agent_id == agent.agent_id)
        .values(current_ticket_count=HumanAgent.current_ticket_count - 1,
                total_resolved=HumanAgent.total_resolved + 1)
    )
    await db.commit()
    await db.refresh(ticket)
    await redis.publish(
        f'ticket:resolved:{ticket_id}',
        json.dumps({'event': 'ticket:resolved', 'ticket_id': ticket_id}),
    )
    return ticket


@router.post('/tickets/{ticket_id}/transfer', response_model=TicketOut)
async def transfer_ticket(
    ticket_id: str, body: TransferBody,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
):
    r = await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
    ticket = r.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, 'Ticket not found')
    if ticket.assigned_agent_id != agent.agent_id:
        raise HTTPException(403, 'Not your ticket')
    tr = await db.execute(select(HumanAgent).where(HumanAgent.agent_id == body.target_agent_id))
    target = tr.scalar_one_or_none()
    if not target:
        raise HTTPException(404, 'Target agent not found')
    if not target.is_available:
        raise HTTPException(409, 'Target agent not available')
    ticket.status            = TicketStatus.TRANSFERRED
    ticket.assigned_agent_id = body.target_agent_id
    await db.execute(update(HumanAgent).where(HumanAgent.agent_id == agent.agent_id)
                     .values(current_ticket_count=HumanAgent.current_ticket_count - 1))
    await db.execute(update(HumanAgent).where(HumanAgent.agent_id == body.target_agent_id)
                     .values(current_ticket_count=HumanAgent.current_ticket_count + 1))
    await db.commit()
    await db.refresh(ticket)
    await redis.publish(
        f'agent:{body.target_agent_id}:tickets',
        json.dumps({'event': 'ticket:transferred_to_you', 'ticket_id': ticket_id, 'from': agent.agent_id}),
    )
    return ticket


@router.get('/tickets/{ticket_id}/stream')
async def ticket_stream(
    ticket_id: str,
    redis: aioredis.Redis = Depends(get_redis),
    agent: HumanAgent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    r = await db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
    ticket = r.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, 'Ticket not found')

    async def stream():
        ps = redis.pubsub()
        await ps.subscribe(
            f'conversation:{ticket.conversation_id}',
            f'ticket:resolved:{ticket_id}',
        )
        yield f'data: {json.dumps({\