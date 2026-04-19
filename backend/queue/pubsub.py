# backend/queue/pubsub.py - Redis pub/sub for real-time notifications.
from __future__ import annotations
import json
import redis.asyncio as aioredis


class TicketPubSub:
    def __init__(self, redis: aioredis.Redis) -> None:
        self._r = redis

    async def publish_new_ticket(self, ticket_id: str, priority: str, conversation_id: str) -> None:
        await self._r.publish(
            f'ticket:new:{priority.upper()}',
            json.dumps({'event': 'ticket:new', 'ticket_id': ticket_id,
                        'priority': priority, 'conversation_id': conversation_id}),
        )

    async def publish_update(self, ticket_id: str, event: str, agent_id=None) -> None:
        await self._r.publish(
            'ticket:updates',
            json.dumps({'event': event, 'ticket_id': ticket_id, 'agent_id': agent_id}),
        )

    async def subscribe_agent(self, priorities=None):
        ps = self._r.pubsub()
        channels = ['ticket:updates']
        for p in (priorities or ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']):
            channels.append(f'ticket:new:{p.upper()}')
        await ps.subscribe(*channels)
        return ps
