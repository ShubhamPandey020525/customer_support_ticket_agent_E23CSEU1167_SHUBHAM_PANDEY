# DECISIONS.md — Architecture Decisions and Assumptions

This file records every assumption, design decision, and deviation from the
assignment specification so reviewers and evaluators can verify the reasoning.

---

## D1 — Mid-Session / Duplicate-Ticket Requirement

**Finding:** The phrase "mid-session" does not appear anywhere in the
repository code, README, or docs. The main Implementation Guide refers to it
only implicitly via §5.3 ("Do not create duplicate tickets when the same
completed request is retried in one session").

**Interpretation applied:**
- (a) Conversation state (`ConversationState`) persists for the entire life of
  a `session_id` — fields collected in turn 1 are available in turn 2, 3, etc.
- (b) If a customer retries an already-completed ticket request in the same
  session, the `TicketRepository` returns the existing ticket ID and the
  `collect_or_create` node returns the same confirmation without creating a
  duplicate.

**Evidence:** `TicketRepository._session_ticket` mapping (already in starter)
+ `collect_or_create` early-return check for `session.ticket_id`.

**Action required:** Confirm with the evaluator whether "mid-session" means
something more specific than this interpretation.

---

## D2 — Voice Integration Exclusion

**Finding:** The §10 Acceptance Boundary paragraph ends with "must work end to
end across the UI, API, LLM/agent, RAG, tools, **and voice integrations**."
This contradicts:
- §1 Objective: explicitly says "text-based customer support agent."
- No requirement bullet anywhere else mentions audio, speech, or voice.
- The entire UI is Streamlit with a text chat input.

**Decision:** Treated as copy-paste boilerplate from a different assignment
template. Voice features are **not implemented**.

**Action required:** Confirm with the evaluator before submission.

---

## D3 — Workflow Dependency Injection

**Finding/Problem:** The scaffold's `build_support_workflow(model)` signature
only accepted the LLM model. The LangGraph nodes need access to
`KnowledgeRetriever`, `SessionStore`, and `TicketRepository` to implement
their bodies.

**Decision:** Extended the signature to
`build_support_workflow(model, retriever, session_store, ticket_repo)`.
All four dependencies are injected as closures. `SupportPipeline.initialize()`
passes the already-constructed instances.

**Impact:** Backward-compatible for existing tests (they mock the pipeline,
not `build_support_workflow` directly). No external API change.

---

## D4 — Structured Output for Intent Classification

**Decision:** The `decide` node uses `model.with_structured_output(_IntentAndFields)`
(a Pydantic schema) to extract `route` + ticket fields in one LLM call.

**Rationale:** This avoids fragile prose-parsing and ensures `route` is always
exactly `"answer"` or `"ticket"`, making `select_route` deterministic and
unit-testable.

**Fallback:** If the LLM returns an unrecognised route value, it is silently
normalised to `"answer"` to prevent crashes.

---

## D5 — Relevance Threshold for "Not in KB" Detection

**Decision:** `KnowledgeRetriever.search()` applies a relevance threshold of
`0.30` (cosine similarity, normalised to [0, 1] by Chroma). Chunks scoring
below this threshold are excluded. When ALL chunks are excluded (empty result),
the `answer` node returns an explicit "I don't have information in the
knowledge base…" message.

**Rationale:** A threshold of 0.30 is conservative enough to pass highly
relevant KB chunks while blocking clearly unrelated queries. Adjust via the
`_RELEVANCE_THRESHOLD` constant in `retriever.py` if the selected model's
embedding distribution differs.

---

## D6 — LLM Provider: Ollama with Qwen2.5:3b (default)

**Finding:** The scaffold already chose `langchain-openai` (`ChatOpenAI`) with
an `LLM_BASE_URL` pointing to `http://localhost:11434/v1` (Ollama's
OpenAI-compatible endpoint) and defaulted `LLM_MODEL` to `qwen2.5:3b`.

**Decision:** Kept exactly as scaffolded. Qwen2.5:3b is an open-source,
instruction-tuned model (Apache 2.0 licence) served locally via Ollama — no
proprietary/closed model API is used.

**Alternative:** Any OpenAI-compatible endpoint (LM Studio, vLLM, Together AI
with an open-source model) works by updating `.env`.

---

## D7 — Vector Store: ChromaDB (scaffold choice)

**Finding:** `langchain-chroma` was already in `requirements.txt` and
`retriever.py` imported `Chroma`. FAISS was never mentioned in any file.

**Decision:** Used ChromaDB with local persistence as scaffolded.
The persistence directory (`.data/vector_db`) is gitignored.

---

## D8 — Embedding Model: sentence-transformers/all-MiniLM-L6-v2

**Finding:** Already configured as the default in `config.py` and `.env.example`.

**Decision:** Kept unchanged. Model is downloaded on first run via
`langchain-huggingface`; no internet required after the first download.

---

## D9 — pytest asyncio_mode = auto

**Decision:** Added `pytest.ini` with `asyncio_mode = auto` so all async test
functions run without needing the `@pytest.mark.asyncio` decorator on each.
This is recommended by `pytest-asyncio >= 0.21`.

---

## D10 — Video Length Discrepancy

**Finding:** The Implementation Guide §8 says a **five-minute** demonstration.
The covering email says a **two-minute** video. These contradict each other.

**Decision:** `DEMO_SCRIPT.md` is structured to fit the tighter **two-minute**
format (the more detailed and specific instruction). The human should confirm
which length the evaluator actually requires before recording.
