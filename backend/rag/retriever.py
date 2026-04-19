"""nexaagent/backend/rag/retriever.py â€” Async wrapper around KBVectorStore."""
from __future__ import annotations
import asyncio
from functools import partial
from ..schemas import KBRetrievalResult
from .vectorstore import get_vectorstore


class KBRetriever:
    def __init__(self) -> None:
        self._vs = get_vectorstore()

    async def search(self, query: str, n_results: int = 4) -> list[KBRetrievalResult]:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, partial(self._vs.search, query, n_results))
        return [KBRetrievalResult(**r) for r in results]
