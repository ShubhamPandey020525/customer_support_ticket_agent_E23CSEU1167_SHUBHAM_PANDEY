"""FastAPI router for voice endpoints.

Adds POST /voice/transcribe and POST /voice/synthesize without touching the
existing POST /chat contract.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response

from src.voice.models import TranscriptionResponse, SynthesisRequest
from src.voice.pipeline import VoicePipeline
from src.voice.stt_adapter import WhisperSTTAdapter
from src.voice.tts_adapter import EdgeTTSAdapter

logger = logging.getLogger(__name__)

# One shared VoicePipeline instance per process; initialized on first request.
_pipeline: VoicePipeline | None = None
_pipeline_ready: bool = False


async def _get_pipeline() -> VoicePipeline:
    global _pipeline, _pipeline_ready  # noqa: PLW0603
    if _pipeline is None:
        _pipeline = VoicePipeline(stt=WhisperSTTAdapter(), tts=EdgeTTSAdapter())
        await _pipeline.initialize()
        _pipeline_ready = True
    return _pipeline


router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe", response_model=TranscriptionResponse)
async def transcribe(file: UploadFile = File(...)) -> TranscriptionResponse:
    """Accept an uploaded audio file and return its transcript.

    - Supports any audio format Whisper can decode (wav, webm, mp3, ogg, …).
    - Returns a clear JSON error if audio is empty or unintelligible.
    - Validation errors use a structured JSON response body.
    """
    import time

    audio_bytes = await file.read()
    media_type = file.content_type or "audio/wav"

    if not audio_bytes:
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": "Uploaded audio file is empty."},
        )

    pipeline = await _get_pipeline()
    t0 = time.perf_counter()
    try:
        transcript, processing_time_ms = await pipeline.transcribe(audio_bytes, media_type)
    except ValueError as exc:
        # Empty audio / no speech detected
        return TranscriptionResponse(
            success=False,
            transcript="",
            processing_time_ms=round((time.perf_counter() - t0) * 1000),
            error=str(exc),
        )
    except Exception as exc:
        logger.exception("STT error: %s", exc)
        raise HTTPException(status_code=500, detail={"success": False, "error": str(exc)}) from exc

    return TranscriptionResponse(
        success=True,
        transcript=transcript,
        processing_time_ms=processing_time_ms,
    )


@router.post("/synthesize")
async def synthesize(request: SynthesisRequest) -> Response:
    """Accept response text and return playable audio bytes (audio/mpeg).

    The response body is raw audio so the Streamlit UI can play it directly
    via st.audio(). The message_id is echoed in the X-Message-Id header.
    """
    pipeline = await _get_pipeline()
    try:
        audio_bytes, media_type, _ = await pipeline.synthesize(request.text)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"success": False, "error": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception("TTS error: %s", exc)
        raise HTTPException(
            status_code=500,
            detail={"success": False, "error": str(exc)},
        ) from exc

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={"X-Message-Id": request.message_id},
    )
