from __future__ import annotations

import base64
from urllib.parse import urlsplit, urlunsplit

import httpx

from octocoder.config import VoiceConfig
from octocoder.voice.models import VoiceAudio
from octocoder.voice.openai_compatible import OpenAICompatibleVoiceProvider
from octocoder.voice.provider import VoiceProviderError


class AliyunVoiceProvider(OpenAICompatibleVoiceProvider):
    """Alibaba Cloud Model Studio Qwen-ASR and Qwen-Audio-TTS adapter."""

    def __init__(
        self,
        config: VoiceConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(config, client=client)

    def _service_url(self, path: str) -> str:
        parsed = urlsplit(self.config.base_url.rstrip("/"))
        current_path = parsed.path.rstrip("/")
        for suffix in ("/compatible-mode/v1", "/api/v1"):
            if current_path.endswith(suffix):
                current_path = current_path[: -len(suffix)]
                break
        target_path = f"{current_path}/{path.lstrip('/')}"
        return urlunsplit((parsed.scheme, parsed.netloc, target_path, "", ""))

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str:
        media_type = content_type.split(";", 1)[0] or "audio/webm"
        encoded = base64.b64encode(audio).decode("ascii")
        payload: dict = {
            "model": self.config.stt_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:{media_type};base64,{encoded}"
                            },
                        }
                    ],
                }
            ],
            "stream": False,
        }
        effective_language = language or self.config.language
        if effective_language:
            payload["asr_options"] = {"language": effective_language}
        response = await self._request(
            "POST",
            self._service_url("compatible-mode/v1/chat/completions"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json=payload,
        )
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise VoiceProviderError("Aliyun transcription returned an invalid response") from exc
        if not isinstance(content, str) or not content.strip():
            raise VoiceProviderError("Voice transcription returned no text")
        return content.strip()

    async def synthesize(self, text: str) -> VoiceAudio:
        if not text.strip():
            raise VoiceProviderError("Speech text is empty")
        input_data: dict = {
            "text": text,
            "voice": self.config.voice,
            "format": "mp3",
        }
        if self.config.language:
            input_data["language_hints"] = [self.config.language]
        response = await self._request(
            "POST",
            self._service_url("api/v1/services/audio/tts/SpeechSynthesizer"),
            headers={**self._headers(), "Content-Type": "application/json"},
            json={"model": self.config.tts_model, "input": input_data},
        )
        try:
            payload = response.json()
            audio = payload["output"]["audio"]
        except (ValueError, KeyError, TypeError) as exc:
            raise VoiceProviderError("Aliyun speech returned an invalid response") from exc

        encoded = audio.get("data") if isinstance(audio, dict) else None
        if isinstance(encoded, str) and encoded:
            try:
                return VoiceAudio(data=base64.b64decode(encoded), content_type="audio/mpeg")
            except ValueError as exc:
                raise VoiceProviderError("Aliyun speech returned invalid audio data") from exc

        audio_url = audio.get("url") if isinstance(audio, dict) else None
        if not isinstance(audio_url, str) or not audio_url:
            raise VoiceProviderError("Aliyun speech response did not contain audio")
        downloaded = await self._request("GET", audio_url)
        if not downloaded.content:
            raise VoiceProviderError("Aliyun speech response did not contain audio")
        content_type = downloaded.headers.get("content-type", "").split(";", 1)[0]
        if content_type in {"", "application/octet-stream"}:
            content_type = "audio/mpeg"
        if not content_type.startswith("audio/"):
            raise VoiceProviderError("Aliyun speech response did not contain audio")
        return VoiceAudio(data=downloaded.content, content_type=content_type)
