# DEMO_SCRIPT.md — Screen Recording Guide

> ⚠️ **Video length ambiguity:** The Implementation Guide §8 says **five minutes**.
> The covering email says **two minutes**. This script is structured for the
> tighter **two-minute** format. Confirm with the evaluator before recording.

---

## Architecture Summary (~30 seconds)

Read aloud over a quick architecture diagram:

> "This is a text-based Customer Support Ticket Agent. A customer types a
> message in the **Streamlit UI**, which sends it to a **FastAPI backend**. The
> backend passes it to a **LangGraph agent** that runs in two paths: if the
> customer has a policy question, it retrieves relevant chunks from a
> **ChromaDB vector store** built from our Markdown knowledge base and returns
> a grounded answer with source documents. If the customer needs support, the
> agent collects their name, email, issue description, and category over
> multiple turns, then calls the **mock ticket tool** to create a unique ticket.
> Session state is preserved by session ID, so retrying a completed ticket
> request in the same session always returns the original ticket — never a
> duplicate."

---

## Demo Queries (in order — ~90 seconds total)

### Query 1 — KB-Grounded Policy Question (20 s)

**Type in chat:**
```
How long does standard shipping take?
```

**Expected response:** ~"Standard delivery usually takes three to five business
days…" with `shipping.md` shown as a source document.

**Point out:** The source pill shows `📄 shipping.md` — the answer is grounded,
not invented.

---

### Query 2 — Out-of-KB Question (15 s)

**Type in chat:**
```
What are your store opening hours?
```

**Expected response:** Something like "I'm sorry, I don't have information in
the knowledge base to answer that question."

**Point out:** The knowledge base has no opening-hours policy, so the agent
says so clearly rather than fabricating an answer.

---

### Query 3 — Multi-Turn Ticket Creation (40 s)

**Turn 1 — trigger ticket flow:**
```
My payment was charged twice and I need help.
```
Agent asks for your name.

**Turn 2 — provide name:**
```
My name is Priya Sharma
```
Agent asks for email.

**Turn 3 — provide email:**
```
priya@example.com
```
Agent may ask for more details or confirm category.

**Turn 4 — confirm/provide remaining fields if asked:**
```
This is a payment issue - I was double-charged for my last order
```
Agent creates the ticket and shows:
- ✅ Ticket ID (e.g., `CST-2026-0001`)
- Category: payment
- Confirmation that the team will follow up at `priya@example.com`

**Point out:** The ticket panel appears only after ALL four fields are present
and validated. The agent never guessed a field.

---

### Query 4 — Ticket Retrieval by ID (10 s)

In the browser, open `http://localhost:8000/docs`, find `GET /tickets/{ticket_id}`,
enter the ticket ID from Query 3, and execute.

**Expected:** Full ticket object with unique ID, category, summary, customer
details, status `"open"`, and a `created_at` timestamp.

---

### (Optional) Query 5 — Duplicate-Ticket Protection (10 s)

**Type in chat again (same session):**
```
I still have the same payment issue, please create another ticket
```

**Expected:** Agent returns the **same ticket ID** (`CST-2026-0001`) with a
message like "Your support ticket has already been created."

**Point out:** This is the mid-session idempotency guarantee — session state
maps one session to one ticket, implemented in `TicketRepository._session_ticket`.

---

## Mid-Session Implementation Explanation

> "The 'mid-session requirement' was not defined explicitly anywhere in the
> repository or documentation. Based on §5.3 of the guide, I implemented it as:
> (a) all conversation state — collected ticket fields, conversation history, and
> the created ticket ID — persists for the life of a `session_id`; and
> (b) the `TicketRepository` uses a `_session_ticket` map to enforce one-ticket-
> per-session, and the `collect_or_create` LangGraph node checks `session.ticket_id`
> at the start of every turn — if a ticket already exists for this session, it
> returns the existing ID immediately without calling the ticket tool again."

---

## Open Questions (flag before recording)

1. **Video length:** 2 minutes (covering email) vs. 5 minutes (guide §8)?
2. **Mid-session definition:** Is the fallback interpretation above correct?
3. **Voice integrations:** Excluded as boilerplate — is that correct?

See `DECISIONS.md` for full rationale on all three.
