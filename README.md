# NexaAgent

> Production-grade AI customer operations platform — multi-agent orchestration, human-in-the-loop escalation, and real-time ops analytics.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-FF6B35)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

---

## What It Does

NexaAgent is a full-stack AI support platform that handles customer conversations end-to-end. Every message flows through a LangGraph multi-agent pipeline — classified by intent and sentiment, answered by RAG against a ChromaDB knowledge base, and escalated to a human agent queue when the AI cannot resolve it confidently. Human agents claim tickets via a real-time React dashboard. Ops managers monitor volume, resolution rate, cache efficiency, and sentiment trends across 24h/7d/30d windows.

---

## Architecture

```
Customer → POST /chat → FastAPI
                            ↓
                    LangGraph Pipeline
                            ↓
              ┌─────────────────────────┐
              │     Intent Agent        │  Groq Llama 3.3 70B
              │  (intent + sentiment)   │  structured JSON output
              └────────────┬────────────┘
                           ↓
              ┌─────────────────────────┐
              │     Cache Check         │  Redis SHA-256 key
              └──┬──────────────────────┘
                 │ hit → serve (<100ms)
                 │ miss ↓
              ┌──▼──────────────────────┐
              │      RAG Agent          │  ChromaDB + SentenceTransformers
              │  (KB semantic search)   │  all-MiniLM-L6-v2 embeddings
              └──┬──────────────────────┘
                 │ confidence ≥ 0.5 ↓
              ┌──▼──────────────────────┐      confidence < 0.5
              │   Response Agent        │  ←─────────────────────┐
              │  (Groq Llama 3.3 70B)   │                         │
              └─────────────────────────┘              ┌──────────▼──────────┐
                                                       │  Escalation Agent   │
                                                       │  PostgreSQL ticket  │
                                                       │  Redis ZPOPMAX queue│
                                                       └──────────┬──────────┘
                                                                  ↓
                                                         Human Agent Dashboard
                                                         (SSE real-time stream)
```

---

## Escalation Decision Tree

The escalation agent applies deterministic rules before invoking the LLM:

| Condition | Trigger | Priority |
|-----------|---------|----------|
| Sentiment = `FRUSTRATED` | SENTIMENT | CRITICAL |
| User tier = `enterprise` | ENTERPRISE_TIER | CRITICAL |
| Intent = `escalation_request` | EXPLICIT_REQUEST | HIGH |
| Urgency = `HIGH` | SENTIMENT | HIGH |
| `kb_confidence < 0.50` | COMPLEXITY | MEDIUM |
| Conversation turns > 5 | REPEAT_CONTACT | MEDIUM |
| `kb_confidence ≥ 0.85` + informational | AUTO-RESOLVE | — |

---

## Key Technical Decisions

**Why LangGraph?** Stateful agent graph with checkpoint-based memory allows the pipeline to pause at escalation boundaries, enabling human-in-the-loop review without losing conversation context.

**Why Redis ZPOPMAX?** Priority queue with composite score `priority_weight × 1e10 + unix_timestamp` ensures CRITICAL tickets surface instantly while preserving FIFO ordering within each priority band.

**Why per-user session isolation?** `conversation_id` is scoped to `user_id` in PostgreSQL — agents cannot access cross-user history. JWTs carry `role` claims (`user` / `agent`) enforced on every route.

**Why ChromaDB + SentenceTransformers locally?** Zero egress cost for embeddings. `all-MiniLM-L6-v2` runs on CPU in the container — no GPU, no external API call per query.

---

## Stack

| Layer | Technology |
|-------|-----------|
| LLM Inference | Groq API · Llama 3.3 70B |
| Agent Orchestration | LangGraph 0.2 · MemorySaver checkpoints |
| API | FastAPI 0.115 · async/await throughout |
| Auth | JWT (python-jose) · HTTPBearer + query-param fallback for SSE |
| Database | PostgreSQL 15 + SQLAlchemy async + Alembic migrations |
| Cache / Queue | Redis 7 · sorted-set priority queue · response cache TTL 1h |
| Vector Store | ChromaDB 0.5 · cosine similarity · SentenceTransformers |
| Frontend | React 18 · Vite · TailwindCSS · Recharts · TanStack Query |
| Streaming | Server-Sent Events (SSE) · token-by-token response streaming |
| Infra | Docker Compose · 5-service stack · health checks |

---

## Project Structure

```
nexaagent/
├── backend/
│   ├── agents/
│   │   ├── graph.py          # LangGraph pipeline definition
│   │   ├── intent_agent.py   # Groq structured JSON classification
│   │   ├── rag_agent.py      # ChromaDB semantic retrieval
│   │   ├── response_agent.py # Groq KB-grounded response generation
│   │   └── escalation_agent.py # Decision tree + ticket creation
│   ├── auth/
│   │   ├── jwt_handler.py    # Token creation + validation
│   │   └── dependencies.py   # FastAPI deps: Bearer + ?token= SSE
│   ├── routers/
│   │   ├── chat.py           # POST /chat · GET /chat/stream (SSE)
│   │   ├── agents_ops.py     # Queue claim, resolve, transfer
│   │   ├── analytics.py      # Overview, intent, sentiment, agent KPIs
│   │   └── kb.py             # Knowledge base CRUD
│   ├── queue/
│   │   ├── ticket_queue.py   # Redis ZPOPMAX priority queue
│   │   └── pubsub.py         # Redis pub/sub for SSE fan-out
│   ├── memory/
│   │   └── conversation.py   # PostgreSQL memory + LLM summarisation
│   ├── rag/
│   │   ├── vectorstore.py    # ChromaDB wrapper
│   │   └── retriever.py      # Async retrieval
│   ├── services/
│   │   └── chat_service.py   # Full pipeline orchestration
│   ├── models.py             # SQLAlchemy ORM (6 tables)
│   ├── schemas.py            # Pydantic v2 request/response
│   ├── config.py             # Pydantic Settings from .env
│   └── database.py           # Async engine + Redis client
├── frontend/
│   └── src/pages/
│       ├── CustomerChat.jsx  # Chat UI with SSE token streaming
│       ├── AgentDashboard.jsx# Queue management + live ticket view
│       └── OpsDashboard.jsx  # Analytics charts (Recharts)
├── alembic/                  # Database migrations
├── tests/
│   ├── test_escalation.py    # EscalationDecision unit tests
│   └── test_intent_agent.py  # Override logic unit tests
└── docker-compose.yml        # 5-service stack
```

---

## Quick Start

```bash
# 1. Clone and configure
git clone https://github.com/OmNarkar777/NexaAgent.git
cd NexaAgent
cp .env.example .env
# Add your GROQ_API_KEY to .env

# 2. Start all services
docker-compose up -d

# 3. Open
# Customer chat:    http://localhost:3000
# Agent dashboard:  http://localhost:3000/agent
# Ops dashboard:    http://localhost:3000/ops
# API docs:         http://localhost:8000/docs
```

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/auth/register/user` | — | Register customer, returns JWT |
| POST | `/auth/login/user` | — | Customer login |
| POST | `/auth/register/agent` | — | Register human agent |
| POST | `/auth/login/agent` | — | Agent login |
| POST | `/chat` | User JWT | Full AI pipeline, returns response |
| GET | `/chat/stream` | User JWT / `?token=` | SSE token streaming |
| GET | `/agent/queue` | Agent JWT | Queue depth + ticket previews |
| POST | `/agent/queue/claim` | Agent JWT | Claim highest-priority ticket |
| POST | `/agent/tickets/{id}/message` | Agent JWT | Send message to customer |
| POST | `/agent/tickets/{id}/resolve` | Agent JWT | Resolve + SLA check |
| POST | `/agent/tickets/{id}/transfer` | Agent JWT | Transfer to another agent |
| GET | `/analytics/overview` | Agent JWT | KPIs: 24h / 7d / 30d |
| GET | `/analytics/sentiment_trend` | Agent JWT | Hourly sentiment chart |
| GET | `/analytics/intent_breakdown` | Agent JWT | Intent distribution |
| GET | `/analytics/agent_performance` | Agent JWT | Per-agent resolution stats |
| POST | `/kb` | Agent JWT | Add KB document + embed |
| GET | `/kb` | Agent JWT | List KB documents |
| DELETE | `/kb/{doc_id}` | Agent JWT | Remove document + embedding |

---

## SLA Tiers

| Priority | Response SLA | Score Weight |
|----------|-------------|-------------|
| CRITICAL | 15 minutes | 4 |
| HIGH | 1 hour | 3 |
| MEDIUM | 4 hours | 2 |
| LOW | 24 hours | 1 |

Queue score = `priority_weight × 1e10 + unix_timestamp` — guarantees priority ordering with FIFO tiebreaking.

---

## Tests

```bash
docker-compose exec backend pytest tests/ -v
```

Unit tests cover escalation decision logic and intent override rules — no database or Redis required.
