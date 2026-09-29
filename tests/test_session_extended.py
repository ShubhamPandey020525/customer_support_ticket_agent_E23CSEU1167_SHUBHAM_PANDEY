"""Extended session state tests — covers CANDIDATE TEST PLAN from test_session.py."""
from src.sessions.store import ConversationState, SessionStore


def test_new_session_has_no_fields() -> None:
    state = ConversationState()
    assert state.customer_name is None
    assert state.customer_email is None
    assert state.issue_description is None
    assert state.category is None
    assert state.ticket_id is None
    assert state.history == []
    assert state.missing_ticket_fields() == [
        "customer_name",
        "customer_email",
        "issue_description",
        "category",
    ]


def test_complete_state_has_no_missing_fields() -> None:
    state = ConversationState(
        customer_name="Ravi Singh",
        customer_email="ravi@example.com",
        issue_description="Order not delivered after 10 days",
        category="order",
    )
    assert state.missing_ticket_fields() == []


def test_session_reports_only_missing_ticket_fields() -> None:
    # Supplied test — preserved exactly.
    state = ConversationState(customer_name="Asha", customer_email="asha@example.com")
    assert state.missing_ticket_fields() == ["issue_description", "category"]


def test_sessions_are_isolated() -> None:
    """Two session IDs must not share state."""
    store = SessionStore()
    s1 = store.get_or_create("session-A")
    s2 = store.get_or_create("session-B")
    s1.customer_name = "Alice"
    assert s2.customer_name is None, "Session B should not inherit Session A's name"


def test_get_or_create_returns_same_object() -> None:
    """get_or_create must return the SAME object on repeated calls."""
    store = SessionStore()
    s1 = store.get_or_create("stable-session")
    s1.customer_name = "Bob"
    s2 = store.get_or_create("stable-session")
    assert s2.customer_name == "Bob"


def test_blank_session_id_raises() -> None:
    store = SessionStore()
    try:
        store.get_or_create("   ")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


def test_conversation_history_order() -> None:
    """History must preserve role and content in insertion order."""
    state = ConversationState()
    state.history.append({"role": "user", "content": "Hello"})
    state.history.append({"role": "assistant", "content": "Hi there!"})
    state.history.append({"role": "user", "content": "I need help"})
    assert state.history[0]["role"] == "user"
    assert state.history[1]["role"] == "assistant"
    assert state.history[2]["content"] == "I need help"


def test_completed_session_retains_ticket_id() -> None:
    """Once a ticket ID is stored in a session it must be retrievable."""
    store = SessionStore()
    session = store.get_or_create("ticket-session")
    session.ticket_id = "CST-2026-0001"
    retrieved = store.get_or_create("ticket-session")
    assert retrieved.ticket_id == "CST-2026-0001"
