from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from octocoder.config import VoiceConfig
from octocoder.voice.fallback import BatchFactory, transcribe_with_fallback
from octocoder.voice.models import (
    MAX_PCM_FRAME_BYTES,
    MAX_PCM_QUEUE_BYTES,
    MAX_RECORDING_BYTES,
    MAX_RECORDING_SECONDS,
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH,
    TranscriptionEvent,
)
from octocoder.voice.provider import (
    StreamingASRProvider,
    StreamingASRSession,
    VoiceErrorKind,
    VoiceProviderError,
)


PartialCallback = Callable[[TranscriptionEvent], Awaitable[None]]


@dataclass(frozen=True)
class RealtimeVoiceResult:
    text: str
    profile_id: str
    provider: str
    fallback_used: bool = False


class RealtimeVoiceSession:
    """Own one realtime ASR request and its bounded PCM forwarding queue."""

    def __init__(
        self,
        config: VoiceConfig,
        provider: StreamingASRProvider,
        request_id: str,
        *,
        mode: str = "hold",
        on_partial: PartialCallback | None = None,
        batch_provider_factory: BatchFactory | None = None,
    ) -> None:
        self.config = config
        self.provider = provider
        self.request_id = request_id
        self.mode = mode
        self.on_partial = on_partial
        self._batch_provider_factory = batch_provider_factory
        self._upstream: StreamingASRSession | None = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._queued_bytes = 0
        self._pcm = bytearray()
        self._next_sequence = 0
        self._sender_task: asyncio.Task[None] | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._finish_task: asyncio.Task[RealtimeVoiceResult] | None = None
        self._provider_error: VoiceProviderError | None = None
        self._started = False
        self._cancelled = False
        self._submitted = False

    @property
    def pcm_bytes(self) -> int:
        return len(self._pcm)

    @property
    def next_sequence(self) -> int:
        return self._next_sequence

    async def start(self) -> None:
        if self._started:
            return
        upstream = await self.provider.create_session(self.request_id)
        await upstream.start()
        self._upstream = upstream
        self._started = True
        self._sender_task = asyncio.create_task(self._send_audio())
        self._reader_task = asyncio.create_task(self._read_events())

    def append_chunk(self, sequence: int, pcm16: bytes) -> None:
        if not self._started or self._cancelled or self._finish_task is not None:
            raise self._invalid("Realtime voice session is not accepting audio")
        if sequence != self._next_sequence:
            raise self._invalid(
                f"Unexpected audio sequence {sequence}; expected {self._next_sequence}"
            )
        if not pcm16 or len(pcm16) > MAX_PCM_FRAME_BYTES or len(pcm16) % 2:
            raise self._invalid("Audio frame must be non-empty 16-bit PCM up to 64 KiB")
        if len(self._pcm) + len(pcm16) > MAX_RECORDING_BYTES:
            raise self._invalid("Recording exceeds the 16 MiB limit")
        duration = (len(self._pcm) + len(pcm16)) / (
            PCM_SAMPLE_RATE * PCM_CHANNELS * PCM_SAMPLE_WIDTH
        )
        if duration > MAX_RECORDING_SECONDS:
            raise self._invalid("Recording exceeds the 120 second limit")
        if self._queued_bytes + len(pcm16) > MAX_PCM_QUEUE_BYTES:
            raise VoiceProviderError(
                "Realtime audio queue is full; please retry",
                kind=VoiceErrorKind.TRANSPORT,
                provider=self.config.primary_profile.provider,
            )
        frame = bytes(pcm16)
        self._pcm.extend(frame)
        self._queued_bytes += len(frame)
        self._next_sequence += 1
        self._queue.put_nowait(frame)

    async def finish(self) -> RealtimeVoiceResult:
        if self._finish_task is None:
            self._finish_task = asyncio.create_task(self._finish_once())
        return await asyncio.shield(self._finish_task)

    def mark_submitted(self) -> bool:
        if self._submitted:
            return False
        self._submitted = True
        return True

    async def cancel(self) -> None:
        if self._cancelled:
            return
        self._cancelled = True
        finish_task = self._finish_task
        if finish_task is not None and not finish_task.done():
            finish_task.cancel()
        self._queue.put_nowait(None)
        upstream = self._upstream
        if upstream is not None:
            await upstream.cancel()
        for task in (self._sender_task, self._reader_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (self._sender_task, self._reader_task) if task is not None),
            return_exceptions=True,
        )
        self._pcm.clear()
        self._queued_bytes = 0

    async def _finish_once(self) -> RealtimeVoiceResult:
        if not self._started or self._upstream is None:
            raise self._invalid("Realtime voice session was not started")
        if not self._pcm:
            raise self._invalid("Recording is empty")
        await self._queue.put(None)
        if self._sender_task is not None:
            await self._sender_task
        try:
            if self._provider_error is not None:
                raise self._provider_error
            text = await self._upstream.finish()
            if self._reader_task is not None:
                await self._reader_task
            return RealtimeVoiceResult(
                text=text.strip(),
                profile_id=self.config.primary_profile.id,
                provider=self.config.primary_profile.provider,
            )
        except VoiceProviderError as exc:
            await self._upstream.cancel()
            kwargs = {}
            if self._batch_provider_factory is not None:
                kwargs["provider_factory"] = self._batch_provider_factory
            fallback = await transcribe_with_fallback(
                self.config,
                bytes(self._pcm),
                exc,
                **kwargs,
            )
            return RealtimeVoiceResult(
                text=fallback.text,
                profile_id=fallback.profile_id,
                provider=fallback.provider,
                fallback_used=True,
            )

    async def _send_audio(self) -> None:
        assert self._upstream is not None
        while True:
            frame = await self._queue.get()
            if frame is None:
                return
            self._queued_bytes -= len(frame)
            if self._provider_error is not None:
                continue
            try:
                await self._upstream.send_audio(frame)
            except VoiceProviderError as exc:
                self._provider_error = exc
            except Exception as exc:
                self._provider_error = VoiceProviderError(
                    f"Realtime ASR audio transport failed: {str(exc)[:400]}",
                    kind=VoiceErrorKind.TRANSPORT,
                    provider=self.config.primary_profile.provider,
                )

    async def _read_events(self) -> None:
        assert self._upstream is not None
        try:
            async for event in self._upstream.events():
                if (
                    isinstance(event, TranscriptionEvent)
                    and event.type in {"partial", "final"}
                    and self.on_partial is not None
                    and self._provider_error is None
                ):
                    await self.on_partial(event)
        except VoiceProviderError as exc:
            self._provider_error = exc
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._provider_error = VoiceProviderError(
                f"Realtime ASR event transport failed: {str(exc)[:400]}",
                kind=VoiceErrorKind.TRANSPORT,
                provider=self.config.primary_profile.provider,
            )

    @staticmethod
    def _invalid(message: str) -> VoiceProviderError:
        return VoiceProviderError(message, kind=VoiceErrorKind.INVALID_REQUEST)
