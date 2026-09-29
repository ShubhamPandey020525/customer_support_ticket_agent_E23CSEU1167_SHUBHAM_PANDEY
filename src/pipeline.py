from __future__ import annotations

from pathlib import Path

from src.config import Settings
from src.llm.client import build_chat_model
from src.llm.workflow import build_support_workflow
from src.models import ChatResponse
from src.rag.retriever import KnowledgeRetriever
from src.sessions.store import SessionStore
from src.tools.ticket_tool import TicketRepository
from src.utils.errors import AgentProcessingError, ComponentNotReadyError


class SupportPipeline:
    """Top-level binding for model, RAG, workflow, sessions, and ticket tool."""

    def __init__(self, settings: Settings, documents_dir: Path) -> None:
        self.settings = settings
        self.model = build_chat_model(settings)
        self.retriever = KnowledgeRetriever(settings, documents_dir)
        self.sessions = SessionStore()
        self.tickets = TicketRepository()
        self.workflow = None
        self.ready = False

    async def initialize(self) -> None:
        """Initialize shared components once during FastAPI startup."""
        # The order is intentional: retrieval must be ready before a workflow
        # capable of accepting traffic is exposed. If either step fails, leave
        # ``ready`` false and let the FastAPI lifespan fail clearly.
        await self.retriever.initialize()
        # Inject all dependencies into the workflow so nodes use closures
        # rather than globals. This makes the workflow fully testable.
        self.workflow = build_support_workflow(
            model=self.model,
            retriever=self.retriever,
            session_store=self.sessions,
            ticket_repo=self.tickets,
        )
        self.ready = True

    async def process(self, session_id: str, message: str) -> ChatResponse:
        """Process one customer turn end-to-end and return a ChatResponse.

        INPUT:
        - Strips boundary whitespace; rejects blank IDs/messages.
        - Obtains one isolated ConversationState from self.sessions.
        - Appends the customer turn without discarding prior valid state.

        WORKFLOW INVOCATION:
        - Builds the typed initial SupportWorkflowState.
        - Passes retriever/session/tool dependencies via workflow closures.
        - Awaits workflow.ainvoke; no synchronous network work on the loop.

        OUTPUT:
        - Validates workflow result before constructing ChatResponse.
        - Requires a non-empty customer-facing response.
        - Includes only source filenames used for this answer.
        - Includes a ticket ID only when the repository holds that ticket.
        - Appends the successful assistant turn to conversation history.
        - Converts known provider/retrieval failures to AgentProcessingError.
        - Never exposes prompts, secrets, stack traces, or filesystem paths.
        """
        if not self.ready or self.workflow is None:
            raise ComponentNotReadyError("Support pipeline is not ready")

        # Validate and normalise inputs.
        session_id = (session_id or "").strip()
        message = (message or "").strip()

        if not session_id:
            raise AgentProcessingError("session_id must not be blank")
        if not message:
            raise AgentProcessingError("message must not be blank")

        # Load or create conversation state for this session.
        session = self.sessions.get_or_create(session_id)

        # Append the customer's turn to conversation history.
        session.history.append({"role": "user", "content": message})

        # Build the initial workflow state for this invocation.
        initial_state = {
            "session_id": session_id,
            "customer_message": message,
            "retrieved_chunks": [],
            "route": "",
            "extracted_fields": {},
            "response_text": "",
            "sources": [],
            "ticket_id": session.ticket_id,  # Carry forward any prior ticket
            "messages": [],
        }

        try:
            result = await self.workflow.ainvoke(initial_state)
        except AgentProcessingError:
            # Re-raise domain errors directly without wrapping.
            raise
        except Exception as exc:
            raise AgentProcessingError(
                f"Agent processing failed: {type(exc).__name__}: {exc}"
            ) from exc

        # Validate the workflow result.
        response_text = (result.get("response_text") or "").strip()
        if not response_text:
            raise AgentProcessingError(
                "Agent returned an empty response — cannot deliver to customer."
            )

        sources: list[str] = result.get("sources") or []
        # Never expose absolute paths — normalise to basenames only.
        sources = [Path(s).name for s in sources if s]

        # Only include a ticket ID when the repository actually holds it.
        raw_ticket_id: str | None = result.get("ticket_id")
        ticket_id: str | None = None
        if raw_ticket_id and self.tickets.get(raw_ticket_id) is not None:
            ticket_id = raw_ticket_id
            # Sync ticket_id back to session state.
            session.ticket_id = ticket_id

        # Append the assistant's successful turn to conversation history.
        session.history.append({"role": "assistant", "content": response_text})

        return ChatResponse(
            success=True,
            session_id=session_id,
            response=response_text,
            sources=sources,
            ticket_id=ticket_id,
        )
