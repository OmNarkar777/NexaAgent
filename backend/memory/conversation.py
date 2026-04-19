"""
nexaagent/backend/memory/conversation.py
PostgreSQL-backed conversation memory with LLM summarisation for older turns.
"""
from __future__ import annotations
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from groq import AsyncGroq
from ..config import settings
from ..models import Conversation, ConversationStatus, Message


class ConversationMemory:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create(self, conversation_id: str, user_id: str) -> Conversation:
        r = await self._db.execute(select(Conversation).where(Conversation.conversation_id == conversation_id))
        conv = r.scalar_one_or_none()
        if not conv:
            conv = Conversation(conversation_id=conversation_id, user_id=user_id)
            self._db.add(conv)
            await self._db.commit()
            await self._db.refresh(conv)
        return conv

    async def get_history(self, conversation_id: str, limit: int = 20) -> list[Message]:
        r = await self._db.execute(
            select(Message).where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc()).limit(limit)
        )
        return list(reversed(r.scalars().all()))

    async def add_message(self, conversation_id: str, role: str, content: str, metadata: dict | None = None) -> Message:
        meta = metadata or {}
        msg = Message(
            conversation_id=conversation_id, role=role, content=content,
            intent_label=meta.get("intent_label"),
            intent_confidence=meta.get("intent_confidence"),
            sentiment_score=meta.get("sentiment_score"),
            sentiment_label=meta.get("sentiment_label"),
            response_time_ms=meta.get("response_time_ms"),
            was_cached=meta.get("was_cached", False),
        )
        self._db.add(msg)
        await self._db.execute(
            update(Conversation)
            .where(Conversation.conversation_id == conversation_id)
            .values(total_messages=Conversation.total_messages + 1)
        )
        await self._db.commit()
        await self._db.refresh(msg)
        return msg

    async def get_summary(self, conversation_id: str) -> str | None:
        msgs = await self.get_history(conversation_id, limit=30)
        if len(msgs) <= 10:
            return None
        text = "\n".join(f"{m.role.upper()}: {m.content}" for m in msgs[:-10])
        client = AsyncGroq(api_key=settings.groq_api_key)
        r = await client.chat.completions.create(
            model=settings.groq_model, temperature=0.1, max_tokens=200,
            messages=[
                {"role": "system", "content": "Summarise this support conversation in 2-3 sentences: customer issue + any resolution."},
                {"role": "user", "content": text},
            ],
        )
        return r.choices[0].message.content.strip()

    async def get_context_for_llm(self, conversation_id: str) -> tuple[list[dict], str | None]:
        msgs = await self.get_history(conversation_id, limit=10)
        recent = [{"role": m.role, "content": m.content} for m in msgs]
        summary = await self.get_summary(conversation_id)
        return recent, summary
