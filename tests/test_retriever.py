"""Integration tests for KnowledgeRetriever using real Chroma + fake embeddings.

These tests use temporary directories and a deterministic fake embedding
function so they run offline without downloading any model.
"""
from __future__ import annotations

import pytest

from src.config import Settings
from src.rag.retriever import KnowledgeRetriever
from src.utils.errors import ComponentNotReadyError


def _make_settings(tmp_path, collection="test-support") -> Settings:
    return Settings(
        llm_base_url="http://localhost:11434/v1",
        llm_api_key="not-required",
        llm_model="test-model",
        vector_db_path=str(tmp_path / "vector_db"),
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        rag_collection=collection,
        rag_top_k=3,
        api_host="127.0.0.1",
        api_port=8000,
        streamlit_host="127.0.0.1",
        streamlit_port=8501,
    )


# ---------------------------------------------------------------------------
# Test: search before initialization raises ComponentNotReadyError
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_before_init_raises(tmp_path, knowledge_dir):
    settings = _make_settings(tmp_path)
    retriever = KnowledgeRetriever(settings, knowledge_dir)
    with pytest.raises(ComponentNotReadyError):
        await retriever.search("shipping policy")


# ---------------------------------------------------------------------------
# Test: blank query returns empty list without crashing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_blank_query_returns_empty(tmp_path, knowledge_dir):
    settings = _make_settings(tmp_path, collection="test-blank")
    retriever = KnowledgeRetriever(settings, knowledge_dir)
    await retriever.initialize()
    result = await retriever.search("")
    assert result == []


# ---------------------------------------------------------------------------
# Test: initialization is idempotent (no duplicates on re-init)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_initialize_is_idempotent(tmp_path, knowledge_dir):
    settings = _make_settings(tmp_path, collection="test-idempotent")
    retriever = KnowledgeRetriever(settings, knowledge_dir)
    await retriever.initialize()
    first_count = retriever._store._collection.count()
    # Re-initialize with the same directory — should not add new chunks.
    retriever2 = KnowledgeRetriever(settings, knowledge_dir)
    await retriever2.initialize()
    second_count = retriever2._store._collection.count()
    assert first_count == second_count, (
        f"Duplicate chunks added on re-init: {first_count} → {second_count}"
    )


# ---------------------------------------------------------------------------
# Test: search returns only safe source filenames (no absolute paths)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_returns_safe_source_names(tmp_path, knowledge_dir):
    settings = _make_settings(tmp_path, collection="test-sources")
    retriever = KnowledgeRetriever(settings, knowledge_dir)
    await retriever.initialize()
    results = await retriever.search("standard shipping delivery time")
    # Even if threshold filters some out, any returned result must be a filename
    for r in results:
        assert "/" not in r["source"], f"Absolute path leaked: {r['source']}"
        assert "\\" not in r["source"], f"Absolute path leaked: {r['source']}"
        assert r["source"].endswith(".md"), f"Unexpected source format: {r['source']}"


# ---------------------------------------------------------------------------
# Test: result dicts contain 'content' and 'source' keys
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_search_result_structure(tmp_path, knowledge_dir):
    settings = _make_settings(tmp_path, collection="test-structure")
    retriever = KnowledgeRetriever(settings, knowledge_dir)
    await retriever.initialize()
    results = await retriever.search("return policy refund")
    for r in results:
        assert "content" in r, "Missing 'content' key"
        assert "source" in r, "Missing 'source' key"
        assert isinstance(r["content"], str)
        assert isinstance(r["source"], str)
