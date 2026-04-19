"""nexaagent/backend/rag/vectorstore.py â€” ChromaDB KB storage with SentenceTransformers."""
from __future__ import annotations
import structlog
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from ..config import settings

logger = structlog.get_logger(__name__)


class KBVectorStore:
    def __init__(self) -> None:
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._model = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
        self._col = self._client.get_or_create_collection(
            name=settings.chroma_collection_name, metadata={"hnsw:space": "cosine"}
        )
        logger.info("vectorstore.init", collection=settings.chroma_collection_name, docs=self._col.count())

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True).tolist()

    def add_document(self, doc_id: str, title: str, content: str, category: str) -> str:
        emb = self._embed([f"{title}\n\n{content}"])
        self._col.upsert(
            ids=[doc_id], embeddings=emb,
            documents=[f"{title}\n\n{content}"],
            metadatas=[{"title": title, "category": category, "doc_id": doc_id}],
        )
        return doc_id

    def delete_document(self, doc_id: str) -> None:
        self._col.delete(ids=[doc_id])

    def search(self, query: str, n_results: int = 5, category: str | None = None) -> list[dict]:
        where = {"category": category} if category else None
        r = self._col.query(
            query_embeddings=self._embed([query]),
            n_results=min(n_results, max(1, self._col.count())),
            include=["documents","metadatas","distances"],
            where=where,
        )
        docs = []
        for did, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0]):
            docs.append({
                "doc_id": meta.get("doc_id", did),
                "title": meta.get("title","Untitled"),
                "content": doc,
                "category": meta.get("category","general"),
                "relevance_score": max(0.0, min(1.0, 1.0 - dist / 2.0)),
            })
        return docs

    @property
    def document_count(self) -> int:
        return self._col.count()


_vs: KBVectorStore | None = None

def get_vectorstore() -> KBVectorStore:
    global _vs
    if _vs is None:
        _vs = KBVectorStore()
    return _vs
