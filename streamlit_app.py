"""Customer Support Chat UI — Streamlit frontend for the FastAPI backend.

Every customer message is sent to POST /chat on the backend.
This file calls no models, vector stores, or ticket repositories directly.
"""
import os
import uuid

import httpx
import streamlit as st


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# --------------------------------------------------------------------------
# Page configuration
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Zangoh Support",
    page_icon="🎧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------------------------------
# Custom CSS for a polished look
# --------------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Clean dark theme overrides */
    .stApp { background-color: #0b0f19; color: #e2e8f0; }
    
    /* Hide top header line */
    header {visibility: hidden;}

    /* Styling for the ticket panel */
    .ticket-box {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        border: 1px solid #3b82f6;
        border-radius: 12px;
        padding: 20px;
        margin-top: 12px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .ticket-id {
        font-size: 1.5em;
        font-weight: 700;
        color: #60a5fa;
        letter-spacing: 0.05em;
        margin: 8px 0;
    }
    
    /* Styling for source documents */
    .source-pill {
        display: inline-block;
        background: #1e293b;
        color: #94a3b8;
        border: 1px solid #334155;
        border-radius: 16px;
        padding: 4px 12px;
        margin: 4px 6px 4px 0;
        font-size: 0.8em;
        font-weight: 500;
    }
    
    /* Chat message styling */
    .stChatMessage {
        background-color: transparent;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# Sidebar with Details & Instructions
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://api.dicebear.com/7.x/shapes/svg?seed=Zangoh&backgroundColor=0b0f19", width=60)
    st.title("Zangoh Support")
    st.markdown("Welcome to the **Zangoh Customer Support Portal**.")
    
    st.markdown("---")
    
    st.subheader("🤖 What I can do:")
    st.markdown("""
    - **Answer Policy Questions:** Ask about shipping, returns, or payments. I will pull the exact answer from our knowledge base.
    - **Raise a Support Ticket:** If you have an unresolved issue, just tell me. I'll ask for your details and create a ticket for our human team.
    """)
    
    st.markdown("---")
    
    st.subheader("💡 Example Queries:")
    st.markdown("""
    * "How long does standard shipping take?"
    * "What is your refund policy?"
    * "I was double charged for my last order."
    """)
    
    st.markdown("---")
    st.caption(f"Session ID:\n`{st.session_state.get('session_id', 'Not started')}`")
    
    if st.button("🔄 Start New Chat", use_container_width=True, type="primary"):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.rerun()

# --------------------------------------------------------------------------
# Session state initialisation — happens once per browser session
# --------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []  # Each entry: {role, content, sources, ticket_id}
    # Add a welcoming initial message
    st.session_state.messages.append({
        "role": "assistant", 
        "content": "Hi there! 👋 I'm the Zangoh Support Agent. How can I help you today? You can ask me a question or tell me about an issue you're facing.",
        "sources": [],
        "ticket_id": None
    })

# --------------------------------------------------------------------------
# Main Chat Area Header
# --------------------------------------------------------------------------
st.markdown("<h2 style='text-align: center; color: #f8fafc; margin-bottom: 2rem;'>How can we help you today?</h2>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Render existing conversation history
# --------------------------------------------------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    with st.chat_message(role):
        st.write(msg["content"])

        # Restore sources and ticket ID for already-rendered assistant messages.
        if role == "assistant":
            sources = msg.get("sources") or []
            ticket_id = msg.get("ticket_id")

            if sources:
                pills_html = "".join(
                    f'<span class="source-pill">📄 {s}</span>' for s in sources
                )
                st.markdown(
                    f"<div style='margin-top:6px'><strong style='color:#888;font-size:0.8em'>"
                    f"Sources:</strong> {pills_html}</div>",
                    unsafe_allow_html=True,
                )

            if ticket_id:
                st.markdown(
                    f'<div class="ticket-box">'
                    f'<div style="color:#aaa;font-size:0.8em">✅ Ticket Created</div>'
                    f'<div class="ticket-id">{ticket_id}</div>'
                    f'<div style="color:#888;font-size:0.8em;margin-top:4px">'
                    f"Our team will reach out soon.</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

# --------------------------------------------------------------------------
# Chat input and API call
# --------------------------------------------------------------------------
if prompt := st.chat_input("How can we help you today?"):
    # Append the user's message and display it immediately.
    st.session_state.messages.append(
        {"role": "user", "content": prompt, "sources": [], "ticket_id": None}
    )
    with st.chat_message("user"):
        st.write(prompt)

    # Build the request payload using the stable session ID.
    payload = {"session_id": st.session_state.session_id, "message": prompt}

    with st.chat_message("assistant"):
        # Show a "Thinking…" indicator while the backend processes the request
        status_placeholder = st.empty()
        status_placeholder.markdown(
            "<span style='color:#64748b;font-size:0.9em'>⏳ Thinking...</span>",
            unsafe_allow_html=True,
        )
        try:
            response = httpx.post(
                f"{API_BASE_URL}/chat",
                json=payload,
                timeout=httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
            )
            status_placeholder.empty()  # Remove the typing indicator

            # ---------- Handle HTTP-level errors ----------
            if response.status_code == 422:
                error_detail = response.json().get("detail", "Invalid request.")
                st.error(f"⚠️ Input validation error: {error_detail}")

            elif response.status_code == 503:
                detail = ""
                try:
                    detail = response.json().get("detail", "")
                except Exception:
                    pass
                st.error(
                    "🔴 A required backend component is currently unavailable. "
                    f"Please try again shortly. {f'({detail})' if detail else ''}"
                )

            elif response.status_code == 502:
                detail = ""
                try:
                    detail = response.json().get("detail", "")
                except Exception:
                    pass
                st.error(
                    "🔴 The AI model is unavailable right now. "
                    f"Please try again shortly. {f'({detail})' if detail else ''}"
                )

            elif not response.is_success:
                st.error(
                    f"🔴 Unexpected error from the backend "
                    f"(HTTP {response.status_code}). Please try again."
                )

            else:
                # ---------- Parse the successful response ----------
                try:
                    data = response.json()
                except Exception:
                    st.error(
                        "🔴 Received a malformed response from the backend. "
                        "Please try again."
                    )
                    data = None

                if data:
                    assistant_text = data.get("response", "")
                    sources: list[str] = data.get("sources") or []
                    ticket_id: str | None = data.get("ticket_id")

                    # Display the assistant's answer.
                    st.write(assistant_text)

                    # Display source documents if any were used.
                    if sources:
                        pills_html = "".join(
                            f'<span class="source-pill">📄 {s}</span>'
                            for s in sources
                        )
                        st.markdown(
                            f"<div style='margin-top:6px'>"
                            f"<strong style='color:#888;font-size:0.8em'>Sources:</strong> "
                            f"{pills_html}</div>",
                            unsafe_allow_html=True,
                        )

                    # Display a ticket confirmation panel when a ticket was created.
                    if ticket_id:
                        st.markdown(
                            f'<div class="ticket-box">'
                            f'<div style="color:#aaa;font-size:0.8em">✅ Ticket Created</div>'
                            f'<div class="ticket-id">{ticket_id}</div>'
                            f'<div style="color:#888;font-size:0.8em;margin-top:4px">'
                            f"Our team will reach out soon.</div>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

                    # Persist the assistant message WITH sources and ticket_id
                    # so they are correctly restored on Streamlit reruns.
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_text,
                            "sources": sources,
                            "ticket_id": ticket_id,
                        }
                    )

        except httpx.ConnectError:
            status_placeholder.empty()
            st.error(
                "🔴 Cannot connect to the backend API. "
                f"Is it running at `{API_BASE_URL}`?"
            )
        except httpx.TimeoutException:
            status_placeholder.empty()
            st.error(
                "🔴 The request timed out. The model may be taking longer than expected. "
                "Please try again."
            )
        except Exception as exc:
            status_placeholder.empty()
            st.error(f"🔴 An unexpected error occurred: {exc}")

