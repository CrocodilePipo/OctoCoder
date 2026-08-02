from __future__ import annotations

import httpx

from octocoder.config import VoiceConfig
from octocoder.voice.openai_compatible import OpenAICompatibleVoiceProvider
from octocoder.voice.provider import VoiceProviderError


class SiliconFlowVoiceProvider(OpenAICompatibleVoiceProvider):
    """SiliconFlow's OpenAI-shaped audio API with its documented STT fields."""

    def __init__(
        self,
        config: VoiceConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config, client=client)

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str:
        response = await self._request(
            "POST",
            self._url("audio/transcriptions"),
            headers=self._headers(),
            data={"model": self.config.stt_model},
            files={"file": (filename, audio, content_type)},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise VoiceProviderError("Voice transcription returned invalid JSON") from exc
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise VoiceProviderError("Voice transcription returned no text")
        return text.strip()
