"""
nexaagent/backend/schemas.py
Pydantic v2 request/response schemas.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# --- Auth ---
class UserRegister(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    tier: str = Field(default="free", pattern="^(free|premium|enterprise)$")

class AgentRegister(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# --- Chat ---
class ChatRequest(BaseModel):
    user_id: str
    conversation_id: Optional[str] = None
    message: str = Field(min_length=1, max_length=4096)

    @field_validator("message")
    @classmethod
    def strip_message(cls, v: str) -> str:
        return v.strip()


class IntentResult(BaseModel):
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    sentiment_label: str
    urgency: str
    is_repeat_contact: bool = False
    escalation_recommended: bool = False
    escalation_reason: Optional[str] = None

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        allowed = {"billing_inquiry","technical_support","refund_request",
                   "account_issue","general_inquiry","complaint","escalation_request"}
        return v if v in allowed else "general_inquiry"

    @field_validator("sentiment_label")
    @classmethod
    def validate_sentiment(cls, v: str) -> str:
        allowed = {"POSITIVE","NEUTRAL","NEGATIVE","FRUSTRATED"}
        return v.upper() if v.upper() in allowed else "NEUTRAL"

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        return v.upper() if v.upper() in {"HIGH","MEDIUM","LOW"} else "LOW"


class KBRetrievalResult(BaseModel):
    doc_id: str
    title: str
    content: str
    category: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    response: str
    intent: str
    sentiment_label: str
    sentiment_score: float
    urgency: str
    was_escalated: bool
    ticket_id: Optional[str] = None
    was_cached: bool
    response_time_ms: int
    kb_sources: list[KBRetrievalResult] = []


# --- Conversations ---
class MessageOut(BaseModel):
    model_config = {"from_attributes": True}
    conversation_id: str
    role: str
    content: str
    intent_label: Optional[str]
    intent_confidence: Optional[float]
    sentiment_score: Optional[float]
    sentiment_label: Optional[str]
    created_at: datetime
    response_time_ms: Optional[int]
    was_cached: bool


class ConversationOut(BaseModel):
    model_config = {"from_attributes": True}
    conversation_id: str
    user_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    status: str
    total_messages: int
    escalated_at: Optional[datetime]
    resolution_time_seconds: Optional[int]
    satisfaction_score: Optional[float]


# --- Tickets ---
class TicketOut(BaseModel):
    model_config = {"from_attributes": True}
    ticket_id: str
    conversation_id: str
    user_id: str
    assigned_agent_id: Optional[str]
    status: str
    priority: str
    escalation_reason: Optional[str]
    escalation_trigger: Optional[str]
    created_at: datetime
    claimed_at: Optional[datetime]
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    sla_breach: bool

class TicketClaimRequest(BaseModel):
    agent_id: str

class TicketResolveRequest(BaseModel):
    resolution_notes: str = Field(min_length=10, max_length=4096)

class TicketTransferRequest(BaseModel):
    target_agent_id: str
    reason: Optional[str] = None


# --- Human Agents ---
class AgentOut(BaseModel):
    model_config = {"from_attributes": True}
    agent_id: str
    email: str
    name: str
    is_available: bool
    current_ticket_count: int
    total_resolved: int
    created_at: datetime

class AgentStatusUpdate(BaseModel):
    is_available: bool


# --- KB Documents ---
class KBDocumentCreate(BaseModel):
    title: str = Field(min_length=3, max_length=512)
    content: str = Field(min_length=10)
    category: str = Field(min_length=1, max_length=100)

class KBDocumentOut(BaseModel):
    model_config = {"from_attributes": True}
    doc_id: str
    title: str
    content: str
    category: str
    created_at: datetime
    view_count: int
    is_active: bool


# --- Analytics ---
class IntentBreakdown(BaseModel):
    intent: str
    count: int
    escalation_rate: float

class SentimentBreakdown(BaseModel):
    sentiment_label: str
    count: int
    percentage: float

class AgentPerformance(BaseModel):
    agent_id: str
    name: str
    total_resolved: int
    avg_resolution_minutes: float
    sla_breach_rate: float
    current_ticket_count: int

class DashboardMetrics(BaseModel):
    period_days: int
    total_conversations: int
    total_escalations: int
    escalation_rate: float
    avg_resolution_time_seconds: float
    cache_hit_rate: float
    sla_breach_rate: float
    open_tickets: int
    claimed_tickets: int
    avg_sentiment_score: float
    intent_breakdown: list[IntentBreakdown]
    sentiment_breakdown: list[SentimentBreakdown]
    agent_performance: list[AgentPerformance]

