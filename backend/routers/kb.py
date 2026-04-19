"""nexaagent/backend/routers/kb.py â€” Knowledge base CRUD."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..database import get_db
from ..models import HumanAgent, KBDocument
from ..schemas import KBDocumentCreate, KBDocumentOut
from ..auth.dependencies import get_current_agent
from ..rag.vectorstore import get_vectorstore

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


@router.get("", response_model=list[KBDocumentOut])
async def list_documents(
    category: str | None = None, limit: int = 50,
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    q = select(KBDocument).where(KBDocument.is_active == True).limit(limit)
    if category: q = q.where(KBDocument.category == category)
    r = await db.execute(q)
    return r.scalars().all()


@router.post("", response_model=KBDocumentOut, status_code=201)
async def create_document(
    body: KBDocumentCreate,
    db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    doc = KBDocument(title=body.title, content=body.content, category=body.category)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    vs = get_vectorstore()
    embedding_id = vs.add_document(doc.doc_id, doc.title, doc.content, doc.category)
    await db.execute(update(KBDocument).where(KBDocument.doc_id == doc.doc_id).values(embedding_id=embedding_id))
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str, db: AsyncSession = Depends(get_db),
    agent: HumanAgent = Depends(get_current_agent),
):
    r = await db.execute(select(KBDocument).where(KBDocument.doc_id == doc_id))
    doc = r.scalar_one_or_none()
    if not doc: raise HTTPException(404, "Document not found")
    vs = get_vectorstore()
    vs.delete_document(doc_id)
    await db.execute(update(KBDocument).where(KBDocument.doc_id == doc_id).values(is_active=False))
    await db.commit()
