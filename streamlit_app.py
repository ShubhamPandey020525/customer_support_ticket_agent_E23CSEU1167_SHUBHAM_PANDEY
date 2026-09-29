"""Customer Support Chat UI — Streamlit frontend for the FastAPI backend.

Includes:
  - Full text-based chat (unchanged from original).
  - Microphone recording → editable transcript → existing POST /chat workflow.
  - Per-response speaker icon → TTS synthesis → audio playback on click.

This file calls no models, vector stores, or ticket repositories directly.
All AI work happens in the backend.
"""
import base64
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
    initial_sidebar_state="expanded",
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

    /* Voice section */
    .voice-section {
        background: linear-gradient(145deg, #0f172a, #1e293b);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .voice-label {
        color: #60a5fa;
        font-size: 0.85em;
        font-weight: 600;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
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
# Sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.image("https://api.dicebear.com/7.x/shapes/svg?seed=Zangoh&backgroundColor=0b0f19", width=60)
    st.title("Zangoh Support")
    st.markdown("Welcome to the **Zangoh Customer Support Portal**.")

    st.markdown("---")

    st.subheader("🤖 What I can do:")
    st.markdown("""
    - **Answer Policy Questions:** Ask about shipping, returns, or payments.
    - **Raise a Support Ticket:** Tell me your issue and I'll create a ticket.
    - **🎤 Voice Input:** Record your question and edit the transcript.
    - **🔊 Voice Playback:** Click the speaker icon on any response.
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
        st.session_state.audio_cache = {}
        st.rerun()

# --------------------------------------------------------------------------
# Session state initialisation — happens once per browser session
# --------------------------------------------------------------------------
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.messages.append({
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": "Hi there! 👋 I'm the Zangoh Support Agent. How can I help you today? You can type, or use the 🎤 mic below.",
        "sources": [],
        "ticket_id": None,
    })
if "audio_cache" not in st.session_state:
    # {message_id: bytes} — reuse within session
    st.session_state.audio_cache = {}
if "tts_loading" not in st.session_state:
    st.session_state.tts_loading = set()  # message_ids currently synthesizing


# --------------------------------------------------------------------------
# Helper: send a text message through existing POST /chat pipeline
# --------------------------------------------------------------------------
def _send_chat(prompt: str) -> None:
    """Send prompt to backend and append result to session messages."""
    st.session_state.messages.append({
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": prompt,
        "sources": [],
        "ticket_id": None,
    })

    payload = {"session_id": st.session_state.session_id, "message": prompt}
    msg_id = str(uuid.uuid4())

    with st.chat_message("assistant"):
        status_ph = st.empty()
        status_ph.markdown(
            "<span style='color:#64748b;font-size:0.9em'>⏳ Thinking...</span>",
            unsafe_allow_html=True,
        )
        try:
            response = httpx.post(
                f"{API_BASE_URL}/chat",
                json=payload,
                timeout=httpx.Timeout(connect=5.0, read=90.0, write=10.0, pool=5.0),
            )
            status_ph.empty()

            if response.status_code == 422:
                st.error(f"⚠️ Input validation error: {response.json().get('detail', '')}")
            elif response.status_code == 503:
                st.error("🔴 Backend component unavailable. Try again shortly.")
            elif response.status_code == 502:
                st.error("🔴 AI model unavailable. Try again shortly.")
            elif not response.is_success:
                st.error(f"🔴 Unexpected error (HTTP {response.status_code}). Try again.")
            else:
                try:
                    data = response.json()
                except Exception:
                    st.error("🔴 Malformed response from backend.")
                    return

                assistant_text = data.get("response", "")
                sources: list[str] = data.get("sources") or []
                ticket_id: str | None = data.get("ticket_id")

                st.write(assistant_text)

                if sources:
                    pills_html = "".join(
                        f'<span class="source-pill">📄 {s}</span>' for s in sources
                    )
                    st.markdown(
                        f"<div style='margin-top:6px'>"
                        f"<strong style='color:#888;font-size:0.8em'>Sources:</strong> "
                        f"{pills_html}</div>",
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

                st.session_state.messages.append({
                    "id": msg_id,
                    "role": "assistant",
                    "content": assistant_text,
                    "sources": sources,
                    "ticket_id": ticket_id,
                })

        except httpx.ConnectError:
            status_ph.empty()
            st.error(f"🔴 Cannot connect to backend at `{API_BASE_URL}`.")
        except httpx.TimeoutException:
            status_ph.empty()
            st.error("🔴 Request timed out. The model may be slow. Try again.")
        except Exception as exc:
            status_ph.empty()
            st.error(f"🔴 Unexpected error: {exc}")


# --------------------------------------------------------------------------
# Helper: synthesize TTS via POST /voice/synthesize
# --------------------------------------------------------------------------
def _synthesize(message_id: str, text: str) -> bytes | None:
    """Call backend TTS. Returns audio bytes or None on failure."""
    try:
        resp = httpx.post(
            f"{API_BASE_URL}/voice/synthesize",
            json={"message_id": message_id, "text": text},
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
        )
        if resp.is_success:
            return resp.content
        else:
            st.warning(f"🔇 TTS failed (HTTP {resp.status_code}). Text response preserved.")
    except Exception as exc:
        st.warning(f"🔇 TTS error: {exc}. Text response preserved.")
    return None


# --------------------------------------------------------------------------
# Main Chat Area Header
# --------------------------------------------------------------------------
st.markdown(
    "<h2 style='text-align: center; color: #f8fafc; margin-bottom: 1rem;'>How can we help you today?</h2>",
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------
# 🎤 Voice Input Section
# --------------------------------------------------------------------------
st.markdown("<div class='voice-section'>", unsafe_allow_html=True)
st.markdown("<div class='voice-label'>🎤 Voice Input (optional)</div>", unsafe_allow_html=True)

audio_data = st.audio_input(
    "Click to record your question",
    key="mic_input",
    label_visibility="collapsed",
)

if audio_data is not None:
    audio_bytes = audio_data.read()
    if audio_bytes:
        with st.spinner("🔄 Transcribing audio..."):
            try:
                transcribe_resp = httpx.post(
                    f"{API_BASE_URL}/voice/transcribe",
                    files={"file": ("recording.wav", audio_bytes, "audio/wav")},
                    timeout=httpx.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0),
                )
                if transcribe_resp.is_success:
                    result = transcribe_resp.json()
                    if result.get("success") and result.get("transcript"):
                        st.session_state["pending_transcript"] = result["transcript"]
                    else:
                        st.warning(f"⚠️ {result.get('error', 'Could not transcribe audio.')}")
                        st.session_state.pop("pending_transcript", None)
                elif transcribe_resp.status_code == 422:
                    st.warning("⚠️ Audio validation error. Please try recording again.")
                else:
                    st.error(f"🔴 Transcription failed (HTTP {transcribe_resp.status_code}).")
                    st.session_state.pop("pending_transcript", None)
            except httpx.ConnectError:
                st.error(f"🔴 Cannot connect to backend at `{API_BASE_URL}`.")
            except Exception as exc:
                st.error(f"🔴 Error during transcription: {exc}")

# Editable transcript + explicit submit
if "pending_transcript" in st.session_state:
    st.info("✏️ Review and edit the transcript below before submitting:")
    edited = st.text_area(
        "Transcript (edit if needed):",
        value=st.session_state["pending_transcript"],
        height=80,
        key="transcript_editor",
    )
    col_submit, col_cancel = st.columns([1, 1])
    with col_submit:
        if st.button("✅ Submit Transcript", type="primary", use_container_width=True):
            confirmed_text = edited.strip()
            if confirmed_text:
                del st.session_state["pending_transcript"]
                _send_chat(confirmed_text)
                st.rerun()
            else:
                st.warning("Transcript is empty. Please type something or record again.")
    with col_cancel:
        if st.button("❌ Cancel", use_container_width=True):
            del st.session_state["pending_transcript"]
            st.rerun()

st.markdown("</div>", unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Render existing conversation history
# --------------------------------------------------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    msg_id = msg.get("id", str(uuid.uuid4()))

    with st.chat_message(role):
        st.write(msg["content"])

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

            # 🔊 Speaker icon — generate TTS only on click, not on every render
            speaker_key = f"spk_{msg_id}"
            is_loading = msg_id in st.session_state.tts_loading

            # Reuse cached audio if available
            if msg_id in st.session_state.audio_cache:
                audio_b64 = base64.b64encode(st.session_state.audio_cache[msg_id]).decode()
                st.markdown(
                    f'<audio controls style="margin-top:6px;width:100%">'
                    f'<source src="data:audio/mpeg;base64,{audio_b64}" type="audio/mpeg">'
                    f"</audio>",
                    unsafe_allow_html=True,
                )
            else:
                btn_label = "🔄 Generating…" if is_loading else "🔊 Listen"
                btn_disabled = is_loading
                if st.button(btn_label, key=speaker_key, disabled=btn_disabled):
                    st.session_state.tts_loading.add(msg_id)
                    with st.spinner("🔊 Generating audio..."):
                        audio_bytes_result = _synthesize(msg_id, msg["content"])
                    st.session_state.tts_loading.discard(msg_id)
                    if audio_bytes_result:
                        st.session_state.audio_cache[msg_id] = audio_bytes_result
                    st.rerun()

# --------------------------------------------------------------------------
# Text chat input (unchanged from original — always works)
# --------------------------------------------------------------------------
if prompt := st.chat_input("Type your question here…"):
    with st.chat_message("user"):
        st.write(prompt)
    _send_chat(prompt)
    st.rerun()
