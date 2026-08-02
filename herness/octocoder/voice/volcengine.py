from __future__ import annotations

import base64
import uuid

import httpx

from octocoder.config import VoiceConfig
from octocoder.voice.models import VoiceAudio
from octocoder.voice.openai_compatible import OpenAICompatibleVoiceProvider
from octocoder.voice.provider import VoiceProviderError


class VolcengineVoiceProvider(OpenAICompatibleVoiceProvider):
    """Volcengine Doubao flash ASR and non-streaming TTS adapter."""

    def __init__(
        self,
        config: VoiceConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config, client=client)

    def _credentials(self) -> tuple[str, str]:
        app_id = self.config.resolve_app_id()
        access_token = self.config.resolve_api_key().strip()
        if access_token.lower().startswith("bearer;"):
            access_token = access_token.split(";", 1)[1].strip()
        if not app_id:
            raise VoiceProviderError("Volcengine App ID is not configured")
        if not access_token:
            raise VoiceProviderError("Volcengine Access Token is not configured")
        return app_id, access_token

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str:
        app_id, access_token = self._credentials()
        request_id = str(uuid.uuid4())
        response = await self._request(
            "POST",
            self._url("api/v3/auc/bigmodel/recognize/flash"),
            headers={
                "Content-Type": "application/json",
                "X-Api-App-Key": app_id,
                "X-Api-Access-Key": access_token,
                "X-Api-Resource-Id": self.config.stt_model,
                "X-Api-Request-Id": request_id,
                "X-Api-Sequence": "-1",
            },
            json={
                "user": {"uid": app_id},
                "audio": {"data": base64.b64encode(audio).decode("ascii")},
                "request": {"model_name": "bigmodel"},
            },
        )
        status_code = response.headers.get("X-Api-Status-Code", "")
        if status_code and status_code != "20000000":
            message = response.headers.get("X-Api-Message", "recognition failed")
            raise VoiceProviderError(
                f"Volcengine transcription failed ({status_code}): {message[:300]}"
            )
        try:
            payload = response.json()
            text = payload["result"]["text"]
        except (ValueError, KeyError, TypeError) as exc:
            raise VoiceProviderError(
                "Volcengine transcription returned an invalid response"
            ) from exc
        if not isinstance(text, str) or not text.strip():
            raise VoiceProviderError("Voice transcription returned no text")
        return text.strip()

    async def synthesize(self, text: str) -> VoiceAudio:
        if not text.strip():
            raise VoiceProviderError("Speech text is empty")
        app_id, access_token = self._credentials()
        response = await self._request(
            "POST",
            self._url("api/v1/tts"),
            headers={
                "Authorization": f"Bearer;{access_token}",
                "Content-Type": "application/json",
            },
            json={
                "app": {
                    "appid": app_id,
                    "token": access_token,
                    "cluster": "volcano_tts",
                },
                "user": {"uid": "octocoder-desktop"},
                "audio": {
                    "voice_type": self.config.voice,
                    "encoding": "mp3",
                    "speed_ratio": 1.0,
                },
                "request": {
                    "reqid": str(uuid.uuid4()),
                    "text": text,
                    "operation": "query",
                    "model": self.config.tts_model,
                },
            },
        )
        try:
            payload = response.json()
            code = payload.get("code")
            encoded = payload.get("data")
        except (ValueError, AttributeError) as exc:
            raise VoiceProviderError(
                "Volcengine speech returned an invalid response"
            ) from exc
        if code != 3000:
            message = str(payload.get("message", "speech synthesis failed"))[:300]
            raise VoiceProviderError(f"Volcengine speech failed ({code}): {message}")
        if not isinstance(encoded, str) or not encoded:
            raise VoiceProviderError("Volcengine speech response did not contain audio")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise VoiceProviderError("Volcengine speech returned invalid audio data") from exc
        if not audio:
            raise VoiceProviderError("Volcengine speech response did not contain audio")
        return VoiceAudio(data=audio, content_type="audio/mpeg")
