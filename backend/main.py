"""backend/main.py - FastAPI app Phase 2, all routers registered."""
from __future__ import annotations
from contextlib import asynccontextmanager
import json
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from .database import close_redis, create_tables, dispose_engine, init_redis, get_redis
from .routers import auth, chat, tickets, agents_ops, analytics, kb

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("nexaagent.starting")
    await init_redis()
    await create_tables()
    logger.info("nexaagent.ready")
    yield
    await close_redis()
    await dispose_engine()
    logger.info("nexaagent.stopped")

app = FastAPI(
    title="NexaAgent",
    description="Production-grade AI customer operations platform",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000","http://localhost:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(tickets.router)
app.include_router(agents_ops.router)
app.include_router(analytics.router)
app.include_router(kb.router)

@app.get("/chat/conversation/{conversation_id}/stream")
async def conversation_sse(conversation_id: str):
    async def stream():
        redis = await get_redis()
        ps = redis.pubsub()
        await ps.subscribe(f"conversation:{conversation_id}")
        yield f"data: {json.dumps({\"event\":\"connected\"})}\n\n"
        try:
            async for msg in ps.listen():
                if msg["type"] == "message":
                    yield f"data: {msg[\"data\"]}\n\n"
        finally:
            await ps.unsubscribe()
            await ps.aclose()
    return StreamingResponse(stream(), media_type="text/event-stream",
                              headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

@app.get("/health")
async def health():
    return {"status":"ok","service":"nexaagent","version":"2.0.0"}