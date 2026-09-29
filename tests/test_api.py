"""FastAPI integration tests using TestClient.

All tests run against a mock pipeline so no real LLM or vector DB is needed.
The module-level `pipeline` in server.py is patched AND pipeline.initialize()
is an AsyncMock so the FastAPI lifespan `await pipeline.initialize()` succeeds.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.models import ChatResponse
from src.tools.ticket_tool import TicketCreate, TicketRepository
from src.utils.errors import AgentProcessingError, ComponentNotReadyError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pipeline(ready: bool = True, response: ChatResponse | None = None):
    """Return a mock SupportPipeline where every async method is an AsyncMock.

    Crucially, ``initialize`` must be an AsyncMock so the FastAPI lifespan
    ``await pipeline.initialize()`` does not raise TypeError.
    """
    pipeline = MagicMock()
    pipeline.ready = ready
    pipeline.tickets = TicketRepository()
    pipeline.initialize = AsyncMock(return_value=None)

    if response is None:
        response = ChatResponse(
            success=True,
            session_id="test-session",
            response="Standard shipping takes 3–5 business days.",
            sources=["shipping.md"],
            ticket_id=None,
        )
    pipeline.process = AsyncMock(return_value=response)
    return pipeline


# ---------------------------------------------------------------------------
# Test: GET /health — pipeline ready
# ---------------------------------------------------------------------------
def test_health_ready():
    from src.api import server

    mock = _make_mock_pipeline(ready=True)
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# ---------------------------------------------------------------------------
# Test: GET /health — pipeline not ready → 503
# ---------------------------------------------------------------------------
def test_health_not_ready():
    from src.api import server

    mock = _make_mock_pipeline(ready=False)
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.get("/health")
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Test: POST /chat — happy path matches documented schema
# ---------------------------------------------------------------------------
def test_chat_success():
    from src.api import server

    mock = _make_mock_pipeline()
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.post(
                "/chat",
                json={"session_id": "demo-session-1", "message": "How long does shipping take?"},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert "response" in body
    assert isinstance(body["sources"], list)
    assert body["ticket_id"] is None


# ---------------------------------------------------------------------------
# Test: POST /chat — missing session_id → 422
# ---------------------------------------------------------------------------
def test_chat_missing_session_id():
    from src.api import server

    mock = _make_mock_pipeline()
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.post("/chat", json={"message": "hello"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Test: POST /chat — empty message → 422 (min_length=1)
# ---------------------------------------------------------------------------
def test_chat_empty_message():
    from src.api import server

    mock = _make_mock_pipeline()
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.post("/chat", json={"session_id": "s1", "message": ""})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /tickets/{ticket_id} — known ticket returns full object
# ---------------------------------------------------------------------------
def test_get_ticket_found():
    from src.api import server

    repo = TicketRepository()
    ticket = repo.create(
        "session-x",
        TicketCreate(
            customer_name="Asha Kumar",
            customer_email="asha@example.com",
            issue_description="My payment was charged twice",
            category="payment",
            summary="Duplicate payment charge",
        ),
    )
    mock = _make_mock_pipeline()
    mock.tickets = repo

    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.get(f"/tickets/{ticket.ticket_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["ticket_id"] == ticket.ticket_id
    assert body["customer_email"] == "asha@example.com"
    assert body["category"] == "payment"
    assert body["status"] == "open"
    assert "created_at" in body


# ---------------------------------------------------------------------------
# Test: GET /tickets/{ticket_id} — unknown ID → 404
# ---------------------------------------------------------------------------
def test_get_ticket_not_found():
    from src.api import server

    mock = _make_mock_pipeline()
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.get("/tickets/CST-0000-9999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Test: POST /chat — ComponentNotReadyError → 503
# ---------------------------------------------------------------------------
def test_chat_component_not_ready():
    from src.api import server

    mock = _make_mock_pipeline()
    mock.process = AsyncMock(side_effect=ComponentNotReadyError("Retriever not initialized"))
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.post("/chat", json={"session_id": "s1", "message": "hello"})
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Test: POST /chat — AgentProcessingError → 502
# ---------------------------------------------------------------------------
def test_chat_agent_processing_error():
    from src.api import server

    mock = _make_mock_pipeline()
    mock.process = AsyncMock(side_effect=AgentProcessingError("LLM timed out"))
    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.post("/chat", json={"session_id": "s1", "message": "hello"})
    assert r.status_code == 502


# ---------------------------------------------------------------------------
# Test: POST /chat — response with ticket_id populated
# ---------------------------------------------------------------------------
def test_chat_returns_ticket_id():
    from src.api import server

    repo = TicketRepository()
    ticket = repo.create(
        "sess-t",
        TicketCreate(
            customer_name="Test User",
            customer_email="test@example.com",
            issue_description="Cannot log in to my account",
            category="account",
            summary="Login issue",
        ),
    )
    mock_response = ChatResponse(
        success=True,
        session_id="sess-t",
        response=f"Your ticket {ticket.ticket_id} has been created.",
        sources=[],
        ticket_id=ticket.ticket_id,
    )
    mock = _make_mock_pipeline(response=mock_response)
    mock.tickets = repo

    with patch.object(server, "pipeline", mock):
        with TestClient(server.app, raise_server_exceptions=False) as client:
            r = client.post(
                "/chat",
                json={"session_id": "sess-t", "message": "I have an account issue"},
            )
    assert r.status_code == 200
    assert r.json()["ticket_id"] == ticket.ticket_id
