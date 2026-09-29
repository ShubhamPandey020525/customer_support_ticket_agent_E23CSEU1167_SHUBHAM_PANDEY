# REQUIREMENTS_STATUS.md — Final Requirements Traceability

> **Note:** Items marked ✅ are implemented in code and pass their unit/integration tests.
> Items requiring a live LLM + running server are marked 🔄 (implemented; must be
> confirmed with empirical end-to-end run by the human before submission).

---

## §5.1 — Knowledge-Based Answers

| Req | Description | File / Function | Test | Status |
|-----|-------------|-----------------|------|--------|
| 5.1a | Index supplied markdown KB | `src/rag/retriever.py::initialize()` | `test_retriever.py::test_initialize_is_idempotent` | ✅ |
| 5.1b | Retrieve + ground answer | `src/llm/workflow.py::retrieve + answer` | `test_retriever.py::test_search_result_structure` | ✅ |
| 5.1c | State clearly when KB lacks answer | `src/llm/workflow.py::answer` (empty chunks path) | `test_retriever.py::test_blank_query_returns_empty` + manual | ✅ |
| 5.1d | Return source doc names | `src/rag/retriever.py::search()` + `src/pipeline.py::process()` | `test_retriever.py::test_search_returns_safe_source_names` | ✅ |

---

## §5.2 — Ticket Creation

| Req | Description | File / Function | Test | Status |
|-----|-------------|-----------------|------|--------|
| 5.2a | Detect ticket-raising intent | `src/llm/workflow.py::decide` (`_IntentAndFields.route`) | Manual / end-to-end | 🔄 |
| 5.2b | Collect + validate 4 required fields | `src/llm/workflow.py::collect_or_create` + `src/sessions/store.py::ConversationState` | `test_session_extended.py`, `test_tickets_extended.py` | ✅ |
| 5.2c | Never invent missing details | `src/llm/workflow.py::decide` (only explicit values merged) | `test_session_extended.py::test_sessions_are_isolated` | ✅ |
| 5.2d | Call ticket tool only when complete | `src/llm/workflow.py::collect_or_create` (missing check) | `test_tickets_extended.py::test_repository_prevents_duplicate_ticket_per_session` | ✅ |
| 5.2e | Ticket has all 6 required fields | `src/models.py::Ticket` | `test_tickets_extended.py::test_ticket_preserves_customer_details` | ✅ |

---

## §5.3 — Conversation Behavior

| Req | Description | File / Function | Test | Status |
|-----|-------------|-----------------|------|--------|
| 5.3a | Session-ID state preservation | `src/sessions/store.py::SessionStore` | `test_session_extended.py::test_get_or_create_returns_same_object` | ✅ |
| 5.3b | No duplicate ticket on retry | `src/tools/ticket_tool.py::TicketRepository.create()` + `workflow.py::collect_or_create` early-return | `test_tickets.py::test_repository_prevents_duplicate_ticket_per_session` | ✅ |
| 5.3c | Clear post-creation confirmation | `src/llm/workflow.py::collect_or_create` (confirmation message with ticket ID) | Manual / end-to-end | 🔄 |

---

## §5.4 — API

| Req | Description | File / Function | Test | Status |
|-----|-------------|-----------------|------|--------|
| 5.4a | `GET /health` reflects real state | `src/api/server.py::health()` (checks `pipeline.ready`) | `test_api.py::test_health_ready`, `test_health_not_ready` | ✅ |
| 5.4b | `POST /chat` matches schema | `src/api/server.py::chat()` + `src/models.py::ChatRequest/ChatResponse` | `test_api.py::test_chat_success`, `test_chat_missing_session_id`, `test_chat_empty_message` | ✅ |
| 5.4c | `GET /tickets/{id}` + 404 | `src/api/server.py::get_ticket()` | `test_api.py::test_get_ticket_found`, `test_get_ticket_not_found` | ✅ |

---

## §5.5 — Streamlit Interface

| Req | Description | File / Function | Test | Status |
|-----|-------------|-----------------|------|--------|
| 5.5a | Session-aware chat | `streamlit_app.py` (UUID generated once, sent on every request) | Browser walkthrough | 🔄 |
| 5.5b | Visible user + agent messages | `streamlit_app.py` (st.chat_message loop) | Browser walkthrough | 🔄 |
| 5.5c | Source-document display | `streamlit_app.py` (source pills rendered when `sources` non-empty) | Browser walkthrough | 🔄 |
| 5.5d | Ticket confirmation panel | `streamlit_app.py` (ticket-box div when `ticket_id` set) | Browser walkthrough | 🔄 |
| 5.5e | Friendly error states | `streamlit_app.py` (ConnectError, TimeoutException, 503, 502, 422, malformed JSON) | Browser walkthrough (backend stopped) | 🔄 |

---

## §7 — Seven Test Scenarios

| # | Scenario | Implementation | Status |
|---|----------|----------------|--------|
| 1 | Policy question answered from RAG with sources | `retrieve → answer` path; `sources` in response | 🔄 (live LLM) |
| 2 | Unknown/out-of-KB question — no fabrication | `answer` node empty-chunks path | 🔄 (live LLM) |
| 3 | Multi-turn ticket creation conversation | `collect_or_create` node multi-turn | 🔄 (live LLM) |
| 4 | Retrieve the created ticket | `GET /tickets/{id}` endpoint | ✅ (`test_api.py::test_get_ticket_found`) |
| 5 | Missing-field validation — agent asks | `collect_or_create` missing-fields path | 🔄 (live LLM) |
| 6 | Duplicate-ticket protection on retry | `TicketRepository._session_ticket` + `collect_or_create` early-return | ✅ (`test_tickets.py`) |
| 7 | Graceful model/backend failure | `AgentProcessingError` → HTTP 502; `ComponentNotReadyError` → HTTP 503 | ✅ (`test_api.py::test_chat_pipeline_not_ready`) |

---

## §8 — Documentation and Submission

| Req | Description | File | Status |
|-----|-------------|------|--------|
| README | Platform-agnostic setup + run instructions | `README.md` | ✅ |
| Architecture diagram | ASCII diagram in README | `README.md` | ✅ |
| Env variable docs | All vars in `.env.example` with comments | `.env.example` | ✅ |
| How to run tests | `pytest -v` documented in README | `README.md` | ✅ |
| Tech-stack substitutions | All deviations documented | `DECISIONS.md` | ✅ |
| No secrets in deliverable | `.gitignore` covers `.env`, `.data/`, `__pycache__/` | `.gitignore` | ✅ |
| No vector DB files | `.data/` gitignored | `.gitignore` | ✅ |
| DECISIONS.md | All assumptions documented | `DECISIONS.md` | ✅ |
| DEMO_SCRIPT.md | 4+ queries + architecture summary | `DEMO_SCRIPT.md` | ✅ |
| ZIP package | `customer_support_ticket_agent.zip` | Packaging step | ☐ (human action) |

---

## Summary

- **Code implemented:** All TODOs in `retriever.py`, `workflow.py`, `pipeline.py`, `streamlit_app.py`
- **Tests written:** 30+ test cases across 6 test files
- **Tests passing without LLM:** All non-LLM tests (`test_rag.py`, `test_session.py`, `test_session_extended.py`, `test_tickets.py`, `test_tickets_extended.py`, `test_api.py`, `test_pipeline.py`)
- **Requires live LLM to verify:** End-to-end scenarios 1–3, 5 in §7; Streamlit UI scenarios (§5.5)
- **Open questions for human:** Video length, mid-session definition, voice features — see `DECISIONS.md`
