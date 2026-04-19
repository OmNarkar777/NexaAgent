"""
nexaagent/backend/models.py
SQLAlchemy async ORM models â€” User, HumanAgent, Conversation, Message, Ticket, KBDocument.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey,
                        Integer, String, Text)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class ConversationStatus(str, PyEnum):
    ACTIVE = "active"; RESOLVED = "resolved"; ESCALATED = "escalated"

class SentimentLabel(str, PyEnum):
    POSITIVE = "POSITIVE"; NEUTRAL = "NEUTRAL"; NEGATIVE = "NEGATIVE"; FRUSTRATED = "FRUSTRATED"

class MessageRole(str, PyEnum):
    USER = "user"; ASSISTANT = "assistant"; SYSTEM = "system"

class TicketStatus(str, PyEnum):
    OPEN = "OPEN"; CLAIMED = "CLAIMED"; RESOLVED = "RESOLVED"; TRANSFERRED = "TRANSFERRED"

class TicketPriority(str, PyEnum):
    CRITICAL = "CRITICAL"; HIGH = "HIGH"; MEDIUM = "MEDIUM"; LOW = "LOW"

class EscalationTrigger(str, PyEnum):
    SENTIMENT = "SENTIMENT"; COMPLEXITY = "COMPLEXITY"
    EXPLICIT_REQUEST = "EXPLICIT_REQUEST"; REPEAT_CONTACT = "REPEAT_CONTACT"
    ENTERPRISE_TIER = "ENTERPRISE_TIER"

class UserTier(str, PyEnum):
    FREE = "free"; PREMIUM = "premium"; ENTERPRISE = "enterprise"


def _uuid() -> str: return str(uuid.uuid4())
def _now() -> datetime: return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), default=UserTier.FREE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", lazy="select")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="user", lazy="select")


class HumanAgent(Base):
    __tablename__ = "human_agents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    current_ticket_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_resolved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    assigned_tickets: Mapped[list["Ticket"]] = relationship(back_populates="assigned_agent", lazy="select")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=ConversationStatus.ACTIVE, nullable=False)
    total_messages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_time_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    satisfaction_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.created_at", lazy="select")
    tickets: Mapped[list["Ticket"]] = relationship(back_populates="conversation", lazy="select")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    was_cached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Ticket(Base):
    __tablename__ = "tickets"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String(36), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_agent_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("human_agents.agent_id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default=TicketStatus.OPEN, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default=TicketPriority.MEDIUM, nullable=False, index=True)
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_trigger: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False, index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_breach: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    conversation: Mapped["Conversation"] = relationship(back_populates="tickets")
    user: Mapped["User"] = relationship(back_populates="tickets")
    assigned_agent: Mapped["HumanAgent | None"] = relationship(back_populates="assigned_tickets")


class KBDocument(Base):
    __tablename__ = "kb_documents"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[str] = mapped_column(String(36), default=_uuid, unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    embedding_id: Mapped[str | None] = mapped_column(String(36), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
