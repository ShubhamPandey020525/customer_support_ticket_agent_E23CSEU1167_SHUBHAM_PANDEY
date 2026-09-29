"""Extended ticket repository tests — covers CANDIDATE TEST PLAN from test_tickets.py."""
import pytest
from pydantic import ValidationError

from src.models import TicketCreate
from src.tools.ticket_tool import TicketRepository


def _make_request(**overrides) -> TicketCreate:
    defaults = dict(
        customer_name="Test User",
        customer_email="test@example.com",
        issue_description="Payment was charged twice",
        category="payment",
        summary="Duplicate payment charge",
    )
    defaults.update(overrides)
    return TicketCreate(**defaults)


def test_repository_prevents_duplicate_ticket_per_session() -> None:
    """Supplied test — preserved exactly."""
    repository = TicketRepository()
    request = _make_request()
    first = repository.create("session-1", request)
    second = repository.create("session-1", request)
    assert first.ticket_id == second.ticket_id
    assert len(list(repository.all())) == 1


def test_different_sessions_get_unique_ticket_ids() -> None:
    repository = TicketRepository()
    t1 = repository.create("session-A", _make_request())
    t2 = repository.create("session-B", _make_request())
    assert t1.ticket_id != t2.ticket_id
    assert len(list(repository.all())) == 2


def test_ticket_preserves_customer_details() -> None:
    repo = TicketRepository()
    req = _make_request(
        customer_name="Priya Sharma",
        customer_email="priya@example.com",
        issue_description="My order was delivered damaged",
        category="order",
        summary="Damaged order delivery",
    )
    ticket = repo.create("sess-details", req)
    assert ticket.customer_name == "Priya Sharma"
    assert ticket.customer_email == "priya@example.com"
    assert ticket.issue_description == "My order was delivered damaged"
    assert ticket.category == "order"
    assert ticket.status == "open"
    assert ticket.created_at is not None
    assert ticket.ticket_id.startswith("CST-")


def test_ticket_retrieval_by_id() -> None:
    repo = TicketRepository()
    ticket = repo.create("sess-get", _make_request())
    retrieved = repo.get(ticket.ticket_id)
    assert retrieved is not None
    assert retrieved.ticket_id == ticket.ticket_id


def test_unknown_ticket_id_returns_none() -> None:
    repo = TicketRepository()
    assert repo.get("CST-9999-9999") is None


def test_invalid_category_raises_validation_error() -> None:
    with pytest.raises((ValidationError, Exception)):
        TicketCreate(
            customer_name="Test",
            customer_email="test@example.com",
            issue_description="Some issue",
            category="invalid_cat",
            summary="Bad category test",
        )


def test_invalid_email_raises_validation_error() -> None:
    with pytest.raises((ValidationError, Exception)):
        TicketCreate(
            customer_name="Test",
            customer_email="not-an-email",
            issue_description="Some issue",
            category="technical",
            summary="Bad email test",
        )


def test_all_valid_categories_accepted() -> None:
    for cat in ("order", "payment", "account", "technical", "other"):
        req = _make_request(category=cat)
        assert req.category == cat
