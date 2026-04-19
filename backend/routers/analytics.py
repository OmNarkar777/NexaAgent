# backend/routers/analytics.py
# Ops dashboard analytics - overview, intent, sentiment, agent perf, top KB.
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from ..auth.dependencies import get_current_agent
from ..database import get_db
from ..models import Conversation, HumanAgent, Message, Ticket, TicketStatus, KBDocument

router   = APIRouter(prefix='/analytics', tags=['analytics'])
_WINDOWS = {'24h': 1, '7d': 7, '30d': 30}

def _since(window: str) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=_WINDOWS.get(window, 1))


@router.get('/overview')
async def overview(
    window: str = Query('24h', pattern='^(24h|7d|30d)$'),
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    since = _since(window)
    r = await db.execute(select(func.count(Conversation.id)).where(Conversation.started_at >= since))
    total_convs = r.scalar() or 0
    r = await db.execute(select(func.count(Conversation.id))
                         .where(Conversation.started_at >= since, Conversation.status == 'escalated'))
    escalated = r.scalar() or 0
    r = await db.execute(select(func.count(Conversation.id))
                         .where(Conversation.started_at >= since, Conversation.status == 'resolved',
                                Conversation.escalated_at.is_(None)))
    ai_resolved = r.scalar() or 0
    r = await db.execute(select(func.avg(Message.response_time_ms))
                         .where(Message.created_at >= since, Message.role == 'assistant',
                                Message.response_time_ms.isnot(None)))
    avg_resp_ms = r.scalar() or 0.0
    r_total  = await db.execute(select(func.count(Message.id))
                                .where(Message.created_at >= since, Message.role == 'assistant'))
    r_cached = await db.execute(select(func.count(Message.id))
                                .where(Message.created_at >= since, Message.was_cached == True))
    cache_rate = (r_cached.scalar() or 0) / max(r_total.scalar() or 1, 1)
    r = await db.execute(select(func.count(Ticket.id))
                         .where(Ticket.created_at >= since, Ticket.sla_breach == True))
    sla_breaches = r.scalar() or 0
    r = await db.execute(select(func.avg(Conversation.resolution_time_seconds))
                         .where(Conversation.started_at >= since,
                                Conversation.resolution_time_seconds.isnot(None)))
    avg_res = r.scalar() or 0.0
    return {
        'window': window, 'total_conversations': total_convs,
        'ai_resolved': ai_resolved, 'escalated_to_human': escalated,
        'escalation_rate': round(escalated / max(total_convs, 1), 4),
        'avg_response_time_ms': round(avg_resp_ms, 2),
        'cache_hit_rate': round(cache_rate, 4),
        'sla_breach_count': sla_breaches,
        'avg_resolution_time_minutes': round(avg_res / 60, 2),
    }


@router.get('/intent_breakdown')
async def intent_breakdown(
    window: str = Query('24h', pattern='^(24h|7d|30d)$'),
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    since = _since(window)
    r = await db.execute(
        select(Message.intent_label, func.count(Message.id).label('cnt'))
        .where(Message.created_at >= since, Message.intent_label.isnot(None), Message.role == 'user')
        .group_by(Message.intent_label).order_by(func.count(Message.id).desc())
    )
    return [{'intent': row.intent_label, 'count': row.cnt} for row in r.all()]


@router.get('/sentiment_trend')
async def sentiment_trend(
    window: str = Query('24h', pattern='^(24h|7d|30d)$'),
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    since = _since(window)
    r = await db.execute(
        text('''
            SELECT date_trunc(\'hour\', m.created_at) AS hour,
                   AVG(m.sentiment_score)              AS avg_sentiment,
                   COUNT(DISTINCT m.conversation_id)   AS conversation_count
            FROM   messages m
            WHERE  m.created_at >= :since AND m.sentiment_score IS NOT NULL
            GROUP  BY date_trunc(\'hour\', m.created_at)
            ORDER  BY hour ASC
        '''),
        {'since': since},
    )
    return [{'hour': row.hour.isoformat(), 'avg_sentiment': round(float(row.avg_sentiment), 4),
             'conversation_count': row.conversation_count} for row in r.all()]


@router.get('/agent_performance')
async def agent_performance(
    window: str = Query('24h', pattern='^(24h|7d|30d)$'),
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    since = _since(window)
    r = await db.execute(
        text('''
            SELECT ha.agent_id, ha.name, ha.current_ticket_count,
                   COUNT(t.id) FILTER (WHERE t.status = \'RESOLVED\')  AS tickets_resolved,
                   AVG(EXTRACT(EPOCH FROM (t.resolved_at - t.created_at))/60)
                       FILTER (WHERE t.resolved_at IS NOT NULL)         AS avg_resolution_minutes,
                   COUNT(t.id) FILTER (WHERE t.sla_breach = true)       AS sla_breach_count
            FROM   human_agents ha
            LEFT JOIN tickets t ON t.assigned_agent_id = ha.agent_id AND t.created_at >= :since
            GROUP  BY ha.agent_id, ha.name, ha.current_ticket_count
            ORDER  BY tickets_resolved DESC NULLS LAST
        '''),
        {'since': since},
    )
    return [{'agent_id': row.agent_id, 'name': row.name,
             'current_ticket_count': row.current_ticket_count,
             'tickets_resolved': row.tickets_resolved or 0,
             'avg_resolution_minutes': round(float(row.avg_resolution_minutes or 0), 2),
             'sla_breach_count': row.sla_breach_count or 0} for row in r.all()]


@router.get('/top_kb_queries')
async def top_kb_queries(
    limit: int = 10, db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    r = await db.execute(
        select(KBDocument.doc_id, KBDocument.title, KBDocument.category, KBDocument.view_count)
        .where(KBDocument.is_active == True)
        .order_by(KBDocument.view_count.desc()).limit(limit)
    )
    return [{'doc_id': row.doc_id, 'title': row.title,
             'category': row.category, 'view_count': row.view_count} for row in r.all()]
