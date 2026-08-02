from __future__ import annotations

from enum import Enum
from typing import AsyncIterator, Protocol

from octocoder.voice.models import VoiceAudio


class VoiceErrorKind(str, Enum):
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_RESPONSE = "invalid_response"


class VoiceProviderError(RuntimeError):
    """A provider failure safe to display without exposing credentials."""

    def __init__(
        self,
        message: str,
        *,
        kind: VoiceErrorKind = VoiceErrorKind.INVALID_RESPONSE,
        retryable: bool | None = None,
        provider: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message[:700])
        self.kind = kind
        self.retryable = (
            kind
            in {
                VoiceErrorKind.TRANSPORT,
                VoiceErrorKind.TIMEOUT,
                VoiceErrorKind.RATE_LIMIT,
                VoiceErrorKind.SERVER,
            }
            if retryable is None
            else retryable
        )
        self.provider = provider
        self.status_code = status_code


class BatchASRProvider(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str: ...


class TTSProvider(Protocol):
    async def synthesize(self, text: str) -> VoiceAudio: ...


class StreamingASRSession(Protocol):
    async def start(self) -> None: ...

    async def send_audio(self, pcm16: bytes) -> None: ...

    async def finish(self) -> str: ...

    async def cancel(self) -> None: ...

    def events(self) -> AsyncIterator[object]: ...


class StreamingASRProvider(Protocol):
    async def create_session(self, request_id: str) -> StreamingASRSession: ...


class VoiceProvider(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str: ...

    async def synthesize(self, text: str) -> VoiceAudio: ...
