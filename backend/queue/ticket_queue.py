# backend/queue/ticket_queue.py
# Redis sorted-set priority queue.
# Score = priority_weight * 1e10 + unix_timestamp
# CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1
from __future__ import annotations
import json, time
from datetime import datetime, timezone
from typing import Optional
import redis.asyncio as aioredis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import HumanAgent, Ticket, TicketStatus

PRIORITY_WEIGHT = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
QUEUE_KEY = 'nexaagent:ticket_queue'


class TicketQueue:
    def __init__(self, redis: aioredis.Redis, db: AsyncSession) -> None:
        self._r  = redis
        self._db = db

    async def push(self, ticket_id: str, priority: str) -> None:
        weight  = PRIORITY_WEIGHT.get(priority.upper(), 1)
        score   = weight * 1e10 + time.time()
        payload = json.dumps({'ticket_id': ticket_id, 'priority': priority.upper()})
        await self._r.zadd(QUEUE_KEY, {payload: score})
        await self._r.publish(
            f'ticket:new:{priority.upper()}',
            json.dumps({'event': 'ticket:new', 'ticket_id': ticket_id, 'priority': priority}),
        )

    async def claim_next(self, agent_id: str) -> Optional[Ticket]:
        results = await self._r.zpopmax(QUEUE_KEY, count=1)
        if not results:
            return None
        raw, _score = results[0]
        ticket_id   = json.loads(raw)['ticket_id']
        now         = datetime.now(timezone.utc)
        await self._db.execute(
            update(Ticket).where(Ticket.ticket_id == ticket_id)
            .values(status=TicketStatus.CLAIMED, assigned_agent_id=agent_id, claimed_at=now)
        )
        await self._db.execute(
            update(HumanAgent).where(HumanAgent.agent_id == agent_id)
            .values(current_ticket_count=HumanAgent.current_ticket_count + 1)
        )
        await self._db.commit()
        r = await self._db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
        ticket = r.scalar_one_or_none()
        await self._r.publish(
            f'ticket:claimed:{agent_id}',
            json.dumps({'event': 'ticket:claimed', 'ticket_id': ticket_id, 'agent_id': agent_id}),
        )
        return ticket

    async def release(self, ticket_id: str, agent_id: str) -> None:
        r = await self._db.execute(select(Ticket).where(Ticket.ticket_id == ticket_id))
        ticket = r.scalar_one_or_none()
        if not ticket:
            return
        await self._db.execute(
            update(Ticket).where(Ticket.ticket_id == ticket_id)
            .values(status=TicketStatus.OPEN, assigned_agent_id=None, claimed_at=None)
        )
        await self._db.execute(
            update(HumanAgent).where(HumanAgent.agent_id == agent_id)
            .values(current_ticket_count=HumanAgent.current_ticket_count - 1)
        )
        await self._db.commit()
        await self.push(ticket_id, ticket.priority)

    async def get_queue_depth(self) -> dict:
        counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for raw in await self._r.zrange(QUEUE_KEY, 0, -1):
            try:
                p = json.loads(raw).get('priority', 'LOW').upper()
                counts[p] = counts.get(p, 0) + 1
            except Exception:
                pass
        return counts

    async def list_unclaimed(self, limit: int = 50) -> list:
        items = await self._r.zrevrange(QUEUE_KEY, 0, limit - 1, withscores=True)
        return [json.loads(raw) for raw, _ in items]
