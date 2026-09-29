"""Whisper STT adapter using faster-whisper (local, no API key needed).

Provider chosen because:
- Fully open-source (MIT), no API key required.
- faster-whisper runs on CPU with acceptable latency for short audio clips.
- Supports any audio format that ffmpeg can decode (WAV, WebM, MP3, OGG).
- Does NOT use any prohibited end-to-end platform (Pipecat, LiveKit, etc.).
"""
from __future__ import annotations

import io
import logging

from .contracts import STTService

logger = logging.getLogger(__name__)

_MODEL_SIZE = "base"  # tiny | base | small — trade speed vs accuracy


class WhisperSTTAdapter(STTService):
    """Local Whisper transcription via faster-whisper."""

    def __init__(self, model_size: str = _MODEL_SIZE) -> None:
        self._model_size = model_size
        self._model = None  # loaded lazily in initialize()

    async def initialize(self) -> None:
        # Import lazily so startup is fast if voice is not used immediately.
        try:
            from faster_whisper import WhisperModel  # type: ignore[import]
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
            logger.info("WhisperSTTAdapter: model '%s' loaded.", self._model_size)
        except ImportError:
            logger.warning(
                "faster-whisper not installed; WhisperSTTAdapter will raise on use. "
                "Run: pip install faster-whisper"
            )
            self._model = None

    async def transcribe(self, audio_bytes: bytes, media_type: str) -> str:  # noqa: ARG002
        if self._model is None:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Install it with: pip install faster-whisper"
            )
        audio_io = io.BytesIO(audio_bytes)
        segments, _ = self._model.transcribe(audio_io, beam_size=5)
        return " ".join(seg.text for seg in segments).strip()
