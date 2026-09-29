import pytest

from mid_session_requirements.voice.contracts import STTService, TTSService
from mid_session_requirements.voice.pipeline import VoicePipeline


class FakeSTT(STTService):
    async def initialize(self) -> None:
        return None

    async def transcribe(self, audio_bytes: bytes, media_type: str) -> str:
        return "My payment was charged twice"


class FakeTTS(TTSService):
    async def initialize(self) -> None:
        return None

    async def synthesize(self, text: str) -> tuple[bytes, str]:
        return b"fake-audio", "audio/mpeg"


@pytest.mark.asyncio
async def test_voice_pipeline_contracts() -> None:
    pipeline = VoicePipeline(FakeSTT(), FakeTTS())

    transcript, _ = await pipeline.transcribe(b"fake-input", "audio/wav")
    audio, media_type, _ = await pipeline.synthesize("Agent response")

    assert transcript == "My payment was charged twice"
    assert audio == b"fake-audio"
    assert media_type == "audio/mpeg"
