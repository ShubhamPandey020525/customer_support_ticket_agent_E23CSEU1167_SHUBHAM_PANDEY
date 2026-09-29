from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from langchain_chroma import Chroma

from src.config import Settings
from src.rag.document_loader import load_support_documents, split_support_documents
from src.rag.embeddings import build_embeddings
from src.utils.errors import ComponentNotReadyError

# Relevance threshold: cosine similarity scores below this value indicate the
# retrieved chunk is not closely related to the query. When ALL chunks fall
# below this threshold the retriever signals "not in KB" via an empty result.
# Adjust via settings or env-var if the default proves too strict/lenient.
_RELEVANCE_THRESHOLD = 0.30


def _stable_chunk_id(source: str, content: str) -> str:
    """Derive a deterministic ID from source filename and chunk text.

    Using a stable ID allows Chroma to skip re-adding chunks that already
    exist, making initialization idempotent across API restarts.
    """
    payload = f"{source}::{content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


class KnowledgeRetriever:
    """Persistent Chroma retrieval scaffold with stable output contracts."""

    def __init__(self, settings: Settings, documents_dir: Path) -> None:
        self.settings = settings
        self.documents_dir = documents_dir
        self._store: Chroma | None = None

    async def initialize(self) -> None:
        """Build or reload the Chroma vector store from the knowledge base.

        Runs the blocking embedding/Chroma setup in a thread pool so the
        FastAPI event loop stays responsive during startup.
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_initialize)

    def _sync_initialize(self) -> None:
        """Blocking initialization — called from a thread pool."""
        documents = split_support_documents(load_support_documents(self.documents_dir))
        embeddings = build_embeddings(self.settings)

        # Create only the configured persistence directory, not arbitrary paths.
        db_path = Path(self.settings.vector_db_path)
        db_path.mkdir(parents=True, exist_ok=True)

        try:
            store = Chroma(
                collection_name=self.settings.rag_collection,
                embedding_function=embeddings,
                persist_directory=str(db_path),
                # Use cosine similarity so relevance scores stay in [0, 1].
                collection_metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to open Chroma collection '{self.settings.rag_collection}': {exc}"
            ) from exc

        # Determine which chunk IDs are already present so we do not duplicate.
        existing_ids: set[str] = set()
        try:
            existing = store.get()
            existing_ids = set(existing.get("ids", []))
        except Exception:
            # If the collection is new / empty, get() may raise or return nothing.
            existing_ids = set()

        # Build lists for chunks that are genuinely new.
        new_texts: list[str] = []
        new_metadatas: list[dict] = []
        new_ids: list[str] = []

        for doc in documents:
            source = doc.metadata.get("source", "unknown.md")
            chunk_id = _stable_chunk_id(source, doc.page_content)
            if chunk_id not in existing_ids:
                new_texts.append(doc.page_content)
                # Preserve only the safe filename, never an absolute path.
                new_metadatas.append({"source": Path(source).name})
                new_ids.append(chunk_id)

        if new_texts:
            try:
                store.add_texts(texts=new_texts, metadatas=new_metadatas, ids=new_ids)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to add documents to Chroma collection: {exc}"
                ) from exc

        # Assign _store only after the usable store is confirmed ready.
        self._store = store

    async def search(self, query: str, limit: int | None = None) -> list[dict[str, str]]:
        """Return relevant chunks grounded in the knowledge base.

        Returns a list of {"content": str, "source": str} dicts ordered
        from most to least relevant. Returns an empty list when no chunks pass
        the relevance threshold.
        """
        if self._store is None:
            raise ComponentNotReadyError(
                "KnowledgeRetriever has not been initialized. "
                "Call initialize() before searching."
            )

        if not query or not query.strip():
            return []

        # Use top_k=1 by default — the workflow only uses the top chunk anyway,
        # so fetching more would just waste embedding compute.
        top_k = limit if limit is not None else min(self.settings.rag_top_k, 1)

        try:
            # similarity_search_with_relevance_scores returns (Document, score)
            # pairs where score is a normalized relevance value in [0, 1].
            results_with_scores = self._store.similarity_search_with_relevance_scores(
                query=query.strip(),
                k=top_k,
            )
        except Exception as exc:
            raise ComponentNotReadyError(
                f"Retrieval failed: {exc}"
            ) from exc

        # Filter by relevance threshold and normalize to plain dicts.
        # Never expose Chroma-internal objects or absolute filesystem paths.
        output: list[dict[str, str]] = []
        seen_content: set[str] = set()

        for doc, score in results_with_scores:
            # Clamp: cosine similarity should be in [0, 1] but floating-point
            # precision can produce tiny negatives; treat those as 0.
            score = max(0.0, score)
            if score < _RELEVANCE_THRESHOLD:
                continue
            content = doc.page_content.strip()
            if content in seen_content:
                # Deduplicate repeated identical chunks while keeping ordering.
                continue
            seen_content.add(content)
            # Use only the safe filename from metadata; fall back to "unknown.md".
            source = Path(doc.metadata.get("source", "unknown.md")).name
            output.append({"content": content, "source": source})

        # Return at most the requested number of useful chunks,
        # already ordered most→least relevant by Chroma.
        return output[:top_k]
