from __future__ import annotations

from typing import Any

import httpx

from octocoder.config import VoiceConfig
from octocoder.voice.models import VoiceAudio
from octocoder.voice.provider import VoiceErrorKind, VoiceProviderError


class OpenAICompatibleVoiceProvider:
    def __init__(
        self,
        config: VoiceConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = client

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        key = self.config.resolve_api_key()
        if not key:
            raise VoiceProviderError(
                "Voice API key is not configured",
                kind=VoiceErrorKind.INVALID_REQUEST,
            )
        return {"Authorization": f"Bearer {key}"}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            if self._client is not None:
                response = await self._client.request(method, url, **kwargs)
            else:
                timeout = httpx.Timeout(90.0, connect=15.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise VoiceProviderError(
                f"Voice service timed out: {exc}",
                kind=VoiceErrorKind.TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise VoiceProviderError(
                f"Voice service request failed: {exc}",
                kind=VoiceErrorKind.TRANSPORT,
            ) from exc

        if response.is_success:
            return response
        detail = self._error_detail(response)
        status = response.status_code
        if status == 401:
            kind = VoiceErrorKind.AUTHENTICATION
        elif status == 403:
            kind = VoiceErrorKind.AUTHORIZATION
        elif status == 429:
            kind = VoiceErrorKind.RATE_LIMIT
        elif status >= 500:
            kind = VoiceErrorKind.SERVER
        elif status == 415:
            kind = VoiceErrorKind.UNSUPPORTED_FORMAT
        else:
            kind = VoiceErrorKind.INVALID_REQUEST
        raise VoiceProviderError(
            f"Voice service returned HTTP {status}: {detail}",
            kind=kind,
            status_code=status,
        )

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:500]
            if payload.get("message"):
                return str(payload["message"])[:500]
        text = response.text.strip()
        return text[:500] or "unknown provider error"

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str:
        data = {
            "model": self.config.stt_model,
            "response_format": "json",
        }
        effective_language = language or self.config.language
        if effective_language:
            data["language"] = effective_language
        response = await self._request(
            "POST",
            self._url("audio/transcriptions"),
            headers=self._headers(),
            data=data,
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

    async def synthesize(self, text: str) -> VoiceAudio:
        if not text.strip():
            raise VoiceProviderError("Speech text is empty")
        response = await self._request(
            "POST",
            self._url("audio/speech"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "model": self.config.tts_model,
                "voice": self.config.voice,
                "input": text,
                "response_format": "mp3",
            },
        )
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type in {"application/octet-stream", "application/audio"}:
            content_type = "audio/mpeg"
        if not content_type.startswith("audio/") or not response.content:
            raise VoiceProviderError("Voice speech response did not contain audio")
        return VoiceAudio(data=response.content, content_type=content_type)
