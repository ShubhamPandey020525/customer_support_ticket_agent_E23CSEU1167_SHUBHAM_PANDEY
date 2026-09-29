"""Edge-TTS adapter for text-to-speech synthesis.

Provider chosen because:
- edge-tts uses Microsoft Edge's neural TTS voices completely free, no API key.
- Returns high-quality audio/mpeg (MP3) suitable for browser playback.
- Lightweight pure-Python async library, zero external dependencies beyond pip.
- Does NOT use any prohibited end-to-end platform (Pipecat, LiveKit, etc.).
"""
from __future__ import annotations

import io
import logging

from .contracts import TTSService

logger = logging.getLogger(__name__)

_VOICE = "en-US-JennyNeural"  # Neural voice — clear, natural sounding


class EdgeTTSAdapter(TTSService):
    """Microsoft Edge neural TTS via the edge-tts library."""

    def __init__(self, voice: str = _VOICE) -> None:
        self._voice = voice

    async def initialize(self) -> None:
        try:
            import edge_tts  # noqa: F401  # type: ignore[import]
            logger.info("EdgeTTSAdapter: ready with voice '%s'.", self._voice)
        except ImportError:
            logger.warning(
                "edge-tts not installed; EdgeTTSAdapter will raise on use. "
                "Run: pip install edge-tts"
            )

    async def synthesize(self, text: str) -> tuple[bytes, str]:
        try:
            import edge_tts  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError(
                "edge-tts is not installed. Install it with: pip install edge-tts"
            ) from exc

        communicate = edge_tts.Communicate(text, self._voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        audio_bytes = buf.getvalue()
        return audio_bytes, "audio/mpeg"
