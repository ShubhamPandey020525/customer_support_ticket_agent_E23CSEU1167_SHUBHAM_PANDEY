from __future__ import annotations

import asyncio
import re
from typing import Annotated, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from src.llm.prompts import ANSWER_TEMPLATE, SYSTEM_PROMPT
from src.sessions.store import SessionStore
from src.tools.ticket_tool import TicketRepository, create_ticket_tool
from src.utils.errors import AgentProcessingError


class SupportWorkflowState(TypedDict, total=False):
    """Typed state shared by the supplied LangGraph node skeletons."""

    session_id: str
    customer_message: str
    messages: Annotated[list, add_messages]
    retrieved_chunks: list[dict[str, str]]
    route: str
    extracted_fields: dict[str, str]
    response_text: str
    sources: list[str]
    ticket_id: str | None


# ---------------------------------------------------------------------------
# Structured output schemas (used by the ``decide`` node)
# ---------------------------------------------------------------------------

class _IntentAndFields(BaseModel):
    """Structured extraction result produced by the decide node."""

    route: str = Field(
        description=(
            "Either 'answer' if the customer is asking a policy/information question, "
            "or 'ticket' if the customer wants to report an unresolved issue and needs support."
        )
    )
    customer_name: str = Field(
        default="",
        description="Customer's full name if explicitly stated in this turn, else empty string.",
    )
    customer_email: str = Field(
        default="",
        description="Customer's email address if explicitly stated in this turn, else empty string.",
    )
    issue_description: str = Field(
        default="",
        description=(
            "Concise description of the customer's reported issue if stated in this turn, "
            "else empty string."
        ),
    )
    category: str = Field(
        default="",
        description=(
            "One of: order, payment, account, technical, other — "
            "infer from the issue only when unambiguous, else empty string."
        ),
    )


_VALID_ROUTES = frozenset({"answer", "ticket"})
_VALID_CATEGORIES = frozenset({"order", "payment", "account", "technical", "other"})
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def build_support_workflow(
    model: BaseChatModel,
    retriever,  # KnowledgeRetriever — avoid circular import
    session_store: SessionStore,
    ticket_repo: TicketRepository,
):
    """Build the compiled LangGraph agent graph.

    All dependencies (retriever, session store, ticket repository) are injected
    here so every node can access them through closures without using global
    state. This keeps the graph testable and the pipeline explicit.
    """

    # ------------------------------------------------------------------
    # Node: retrieve
    # ------------------------------------------------------------------
    async def retrieve(state: SupportWorkflowState) -> SupportWorkflowState:
        """Search the knowledge base for chunks relevant to the customer message."""
        message = state.get("customer_message", "")

        if not message or not message.strip():
            return {"retrieved_chunks": []}

        try:
            chunks = await retriever.search(message)
        except Exception:
            # Retrieval failure must not crash the turn; treat as empty KB hit.
            chunks = []

        # Deduplicate repeated chunks while preserving relevance ordering.
        seen: set[str] = set()
        unique_chunks: list[dict[str, str]] = []
        for chunk in chunks:
            content = chunk.get("content", "")
            if content and content not in seen:
                seen.add(content)
                unique_chunks.append({"content": content, "source": chunk.get("source", "")})

        return {"retrieved_chunks": unique_chunks}

    # ------------------------------------------------------------------
    # Node: decide
    # OPTIMISATION: Tighter, shorter prompt — fewer tokens = faster LLM response.
    # ------------------------------------------------------------------
    async def decide(state: SupportWorkflowState) -> SupportWorkflowState:
        """Classify the customer's intent and extract any ticket fields present.

        Uses structured output (.with_structured_output) so the route is
        always deterministic and parseable — not inferred from prose.
        """
        message = state.get("customer_message", "")
        session_id = state.get("session_id", "")
        session = session_store.get_or_create(session_id) if session_id else None

        # ── Mid-collection fast-path ────────────────────────────────────────
        # If a ticket collection is already in progress (we have at least one
        # field collected but no ticket_id yet), ALWAYS continue collecting.
        # This prevents the LLM from misrouting field answers (like a name)
        # back to the 'answer' path, which would make the agent "forget" context.
        if session and session.ticket_id is None:
            collected_fields = [
                f for f in ["customer_name", "customer_email", "issue_description", "category"]
                if getattr(session, f, None)
            ]
            if collected_fields:
                # Session has partial ticket data — extract any new fields from
                # this message and keep routing to 'ticket'.
                extracted: dict[str, str] = {}
                # Simple heuristic extraction for field-answering turns:
                # The structured LLM call below will do the real extraction.
                # We still need to classify in case the user switches intent.
                pass  # fall through to full LLM classification below

        # Build a minimal context summary for the decision prompt
        session_summary = ""
        in_ticket_flow = False
        if session:
            fields = {
                "customer_name": session.customer_name,
                "customer_email": session.customer_email,
                "issue_description": session.issue_description,
                "category": session.category,
                "ticket_id": session.ticket_id,
            }
            collected = {k: v for k, v in fields.items() if v}
            if collected:
                session_summary = "Collected so far: " + ", ".join(
                    f"{k}={v}" for k, v in collected.items()
                )
                # We're in a ticket collection flow if we have any field but no ticket yet
                if session.ticket_id is None and any(
                    getattr(session, f) for f in ["customer_name", "customer_email", "issue_description", "category"]
                ):
                    in_ticket_flow = True

        retrieved_chunks = state.get("retrieved_chunks", [])
        # Only use first 300 chars of the top-1 chunk — enough for classification,
        # much fewer tokens sent to LLM.
        context_text = retrieved_chunks[0]["content"][:300] if retrieved_chunks else ""

        # OPTIMISED: Short, direct prompt — no long preamble.
        if in_ticket_flow:
            decide_prompt = (
                f"You are collecting details for a support ticket.\n"
                f"{session_summary}\n"
                f"Customer's latest message: {message}\n\n"
                f"Route MUST be 'ticket' — we are mid-collection. "
                f"Extract any NEW name, email, issue description, or category the customer just provided. "
                f"Do NOT extract values already listed in 'Collected so far'."
            )
        else:
            decide_prompt = (
                f"Context: {context_text or '(none)'}\n"
                f"{session_summary}\n"
                f"Message: {message}\n\n"
                f"Route: 'answer' if asking policy/info question, 'ticket' if reporting a problem.\n"
                f"Extract name, email, issue, category only if explicitly stated."
            )

        structured_model = model.with_structured_output(_IntentAndFields)

        try:
            result: _IntentAndFields = await structured_model.ainvoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=decide_prompt)]
            )
        except Exception as exc:
            raise AgentProcessingError(
                f"Intent classification failed: {exc}"
            ) from exc

        # Validate route; default to 'answer' on unexpected values.
        route = result.route.strip().lower()
        if route not in _VALID_ROUTES:
            route = "answer"

        # If we are mid-collection, enforce ticket route regardless of LLM output.
        if in_ticket_flow:
            route = "ticket"

        # Validate category if provided; clear it if unrecognised.
        category = result.category.strip().lower() if result.category else ""
        if category and category not in _VALID_CATEGORIES:
            category = ""

        extracted: dict[str, str] = {}
        if result.customer_name.strip():
            extracted["customer_name"] = result.customer_name.strip()
        if result.customer_email.strip() and _EMAIL_RE.match(result.customer_email.strip()):
            extracted["customer_email"] = result.customer_email.strip()
        if result.issue_description.strip():
            extracted["issue_description"] = result.issue_description.strip()
        if category:
            extracted["category"] = category

        return {"route": route, "extracted_fields": extracted}

    # ------------------------------------------------------------------
    # Node: answer
    # OPTIMISATION: Compact prompt — include only top-1 most relevant chunk.
    # ------------------------------------------------------------------
    async def answer(state: SupportWorkflowState) -> SupportWorkflowState:
        """Generate a grounded answer using only retrieved knowledge chunks.

        When no chunks pass the retriever's relevance threshold, the node
        explicitly states the knowledge base cannot answer rather than falling
        back to the model's general knowledge.
        """
        retrieved_chunks = state.get("retrieved_chunks", [])
        message = state.get("customer_message", "")
        session_id = state.get("session_id", "")
        session = session_store.get_or_create(session_id) if session_id else None

        if not retrieved_chunks:
            # No KB match — but this might be a greeting or general conversation.
            # Use the LLM with a short prompt so greetings get a friendly reply
            # and truly out-of-scope questions get a clear "I don't know" message.
            conversational_prompt = (
                f"You are a friendly customer support agent for Zangoh, an e-commerce store. "
                f"The customer said: '{message}'\n\n"
                f"If this is a greeting or general message, respond warmly and ask how you can help. "
                f"If they are asking a specific question you cannot answer from your knowledge base "
                f"(which covers shipping, returns, payments, and accounts), say you don't have that "
                f"information but offer to help with something else or create a support ticket. "
                f"Keep your reply short (2-3 sentences max)."
            )
            try:
                conv_response = await model.ainvoke(
                    [HumanMessage(content=conversational_prompt)]
                )
                no_kb_response = (
                    conv_response.content
                    if hasattr(conv_response, "content")
                    else str(conv_response)
                )
            except Exception:
                no_kb_response = (
                    "Hello! I'm the Zangoh support agent. I can help you with questions about "
                    "shipping, returns, payments, and accounts — or create a support ticket for you. "
                    "What can I help you with today?"
                )
            return {
                "response_text": no_kb_response,
                "sources": [],
                "ticket_id": state.get("ticket_id"),
            }

        # OPTIMISATION: Only use the single most-relevant chunk to keep
        # the prompt small and LLM inference fast.
        top_chunk = retrieved_chunks[0]
        context_text = top_chunk["content"][:600]  # hard cap at 600 chars
        sources = [top_chunk["source"]] if top_chunk.get("source") else []

        # OPTIMISATION: Limit session context to the single last assistant turn
        # (not 2 turns) to save tokens.
        session_context = ""
        if session and session.history:
            last = session.history[-1]
            session_context = f"{last['role'].capitalize()}: {last['content'][:150]}"

        prompt_text = ANSWER_TEMPLATE.format(
            context=context_text,
            session=session_context or "(no prior conversation)",
            message=message,
        )

        try:
            response = await model.ainvoke(
                [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt_text)]
            )
            response_text = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            raise AgentProcessingError(
                f"Answer generation failed: {exc}"
            ) from exc

        return {
            "response_text": response_text,
            "sources": sources,
            "ticket_id": state.get("ticket_id"),
        }

    # ------------------------------------------------------------------
    # Node: collect_or_create
    # OPTIMISATION: Summary is now generated inline without a 3rd LLM call.
    # ------------------------------------------------------------------
    async def collect_or_create(state: SupportWorkflowState) -> SupportWorkflowState:
        """Collect required ticket fields and create a ticket when all are present.

        Field collection strategy:
        1. Load existing session state (persists across turns).
        2. Merge only fields explicitly extracted in this turn — never invent.
        3. If any required field is still missing, ask a focused follow-up.
        4. Once all four fields are present and valid, invoke the ticket tool.
        5. If a ticket already exists for this session, return it without a
           duplicate — this is the mid-session idempotency guarantee.
        """
        session_id = state.get("session_id", "")
        extracted_fields = state.get("extracted_fields", {})

        if not session_id:
            raise AgentProcessingError("session_id is required for ticket creation")

        session = session_store.get_or_create(session_id)

        # Mid-session idempotency: if a ticket already exists for this session,
        # return it immediately without creating a duplicate.
        if session.ticket_id:
            ticket = ticket_repo.get(session.ticket_id)
            if ticket:
                confirmation = (
                    f"Your support ticket has already been created. "
                    f"Your ticket ID is **{session.ticket_id}**. "
                    f"Our support team will be in touch soon."
                )
                return {
                    "response_text": confirmation,
                    "sources": [],
                    "ticket_id": session.ticket_id,
                }

        # Merge only fields that were explicitly stated in this turn.
        # Never overwrite an already-collected valid field with an empty string.
        if extracted_fields.get("customer_name"):
            session.customer_name = extracted_fields["customer_name"]
        if extracted_fields.get("customer_email"):
            session.customer_email = extracted_fields["customer_email"]
        if extracted_fields.get("issue_description"):
            session.issue_description = extracted_fields["issue_description"]
        if extracted_fields.get("category"):
            session.category = extracted_fields["category"]

        # Determine which required fields are still missing.
        missing = session.missing_ticket_fields()

        if missing:
            # Ask a single, focused follow-up for the FIRST missing field.
            # Never ask for passwords, OTPs, or full card numbers.
            field_questions = {
                "customer_name": "Could you please tell me your full name?",
                "customer_email": "What email address should we associate with your ticket?",
                "issue_description": (
                    "Could you describe the issue you're experiencing in a bit more detail?"
                ),
                "category": (
                    "What type of issue is this? "
                    "(order / payment / account / technical / other)"
                ),
            }
            next_field = missing[0]
            follow_up = field_questions.get(
                next_field, f"Could you provide your {next_field.replace('_', ' ')}?"
            )

            # Provide context-aware introduction on the first ticket turn.
            already_have = [
                f for f in ["customer_name", "customer_email", "issue_description", "category"]
                if getattr(session, f)
            ]
            if not already_have:
                response_text = (
                    f"I'd be happy to create a support ticket for you. "
                    f"{follow_up}"
                )
            else:
                response_text = follow_up

            return {
                "response_text": response_text,
                "sources": [],
                "ticket_id": None,
            }

        # OPTIMISATION: Derive summary directly from session data — no 3rd LLM call.
        # The issue_description already contains the customer's own words; truncate it.
        summary_text = session.issue_description[:155]

        # Bind the ticket tool to the current session and invoke it.
        tool = create_ticket_tool(ticket_repo, session_id)
        try:
            ticket_id = tool.func(
                customer_name=session.customer_name,
                customer_email=session.customer_email,
                issue_description=session.issue_description,
                category=session.category,
                summary=summary_text,
            )
        except Exception as exc:
            raise AgentProcessingError(
                f"Ticket creation failed: {exc}"
            ) from exc

        # Store the repository-issued ID in session state.
        session.ticket_id = ticket_id

        confirmation = (
            f"Your support ticket has been created successfully! 🎫\n\n"
            f"**Ticket ID:** {ticket_id}\n"
            f"**Category:** {session.category}\n"
            f"**Summary:** {summary_text}\n\n"
            f"Our support team will review your issue and follow up at {session.customer_email}."
        )

        return {
            "response_text": confirmation,
            "sources": [],
            "ticket_id": ticket_id,
        }

    # ------------------------------------------------------------------
    # Conditional edge: select_route
    # ------------------------------------------------------------------
    def select_route(state: SupportWorkflowState) -> str:
        """Return 'answer' or 'ticket' based on the decide node's output.

        Uses the structured ``route`` field set by the decide node — never
        parses arbitrary prose. Rejects unexpected values via controlled error.
        """
        route = state.get("route", "")
        if route not in _VALID_ROUTES:
            raise AgentProcessingError(
                f"Unexpected route '{route}' from decide node. "
                f"Expected one of: {sorted(_VALID_ROUTES)}"
            )
        return route

    # ------------------------------------------------------------------
    # Graph assembly (provided by scaffold — structure unchanged)
    # ------------------------------------------------------------------
    graph = StateGraph(SupportWorkflowState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("decide", decide)
    graph.add_node("answer", answer)
    graph.add_node("ticket", collect_or_create)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "decide")
    graph.add_conditional_edges(
        "decide",
        select_route,
        {"answer": "answer", "ticket": "ticket"},
    )
    graph.add_edge("answer", END)
    graph.add_edge("ticket", END)
    return graph.compile()
