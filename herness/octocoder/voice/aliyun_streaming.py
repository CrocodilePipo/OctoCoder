from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from octocoder.config import VoiceProviderProfile
from octocoder.voice.models import TranscriptionEvent
from octocoder.voice.provider import VoiceErrorKind, VoiceProviderError


Connector = Callable[..., Awaitable[Any]]


class AliyunStreamingASRProvider:
    def __init__(
        self,
        profile: VoiceProviderProfile,
        *,
        connector: Connector | None = None,
    ) -> None:
        self.profile = profile
        self._connector = connector or connect

    async def create_session(self, request_id: str) -> "AliyunStreamingASRSession":
        return AliyunStreamingASRSession(
            self.profile,
            request_id=request_id,
            connector=self._connector,
        )


class AliyunStreamingASRSession:
    def __init__(
        self,
        profile: VoiceProviderProfile,
        *,
        request_id: str,
        connector: Connector,
    ) -> None:
        self.profile = profile
        self.request_id = request_id
        self.task_id = str(uuid.uuid4())
        self._connector = connector
        self._socket: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._started = asyncio.Event()
        self._finished = asyncio.Event()
        self._events: asyncio.Queue[TranscriptionEvent | None] = asyncio.Queue()
        self._error: VoiceProviderError | None = None
        self._final_sentences: dict[int, str] = {}
        self._partials: dict[int, str] = {}
        self._revision = 0
        self._finishing = False
        self._cancelled = False

    async def start(self) -> None:
        key = self.profile.resolve_api_key()
        if not key:
            raise VoiceProviderError(
                "Aliyun API key is not configured",
                kind=VoiceErrorKind.INVALID_REQUEST,
                provider="aliyun",
            )
        headers = {
            "Authorization": f"Bearer {key}",
            "User-Agent": "OctoCoder/0.2 realtime-voice",
        }
        if self.profile.workspace_id:
            headers["X-DashScope-WorkSpace"] = self.profile.workspace_id
        try:
            self._socket = await self._connector(
                self.profile.streaming_url,
                additional_headers=headers,
                open_timeout=15,
                ping_interval=20,
                ping_timeout=20,
                max_size=1024 * 1024,
            )
            self._reader_task = asyncio.create_task(self._read_events())
            await self._socket.send(json.dumps(self._run_task(), ensure_ascii=False))
            await asyncio.wait_for(self._started.wait(), timeout=15)
            if self._error is not None:
                raise self._error
        except VoiceProviderError:
            await self.cancel()
            raise
        except asyncio.TimeoutError as exc:
            await self.cancel()
            raise VoiceProviderError(
                "Aliyun realtime ASR did not start in time",
                kind=VoiceErrorKind.TIMEOUT,
                provider="aliyun",
            ) from exc
        except Exception as exc:
            await self.cancel()
            raise self._connection_error(exc) from exc

    async def send_audio(self, pcm16: bytes) -> None:
        if self._socket is None or not self._started.is_set() or self._finishing:
            raise VoiceProviderError(
                "Aliyun realtime ASR session is not accepting audio",
                kind=VoiceErrorKind.INVALID_REQUEST,
                provider="aliyun",
            )
        if self._error is not None:
            raise self._error
        try:
            await self._socket.send(pcm16)
        except Exception as exc:
            error = self._connection_error(exc)
            self._set_error(error)
            raise error from exc

    async def finish(self) -> str:
        if self._socket is None:
            raise VoiceProviderError(
                "Aliyun realtime ASR session was not started",
                kind=VoiceErrorKind.INVALID_REQUEST,
                provider="aliyun",
            )
        if not self._finishing:
            self._finishing = True
            try:
                await self._socket.send(json.dumps(self._finish_task()))
            except Exception as exc:
                error = self._connection_error(exc)
                self._set_error(error)
                raise error from exc
        try:
            await asyncio.wait_for(self._finished.wait(), timeout=25)
            if self._error is not None:
                raise self._error
            text = self._combined_text()
            if not text:
                raise VoiceProviderError(
                    "Aliyun realtime ASR returned no text",
                    kind=VoiceErrorKind.INVALID_RESPONSE,
                    provider="aliyun",
                )
            return text
        except asyncio.TimeoutError as exc:
            raise VoiceProviderError(
                "Aliyun realtime ASR did not finish in time",
                kind=VoiceErrorKind.TIMEOUT,
                provider="aliyun",
            ) from exc
        finally:
            await self._close_socket()

    async def cancel(self) -> None:
        self._cancelled = True
        self._finished.set()
        self._started.set()
        await self._close_socket()

    async def events(self) -> AsyncIterator[TranscriptionEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                break
            yield event

    def _run_task(self) -> dict[str, Any]:
        parameters: dict[str, Any] = {
            "format": "pcm",
            "sample_rate": 16000,
            "heartbeat": True,
        }
        if self.profile.language:
            parameters["language_hints"] = [self.profile.language]
        return {
            "header": {
                "action": "run-task",
                "task_id": self.task_id,
                "streaming": "duplex",
            },
            "payload": {
                "task_group": "audio",
                "task": "asr",
                "function": "recognition",
                "model": self.profile.streaming_stt_model,
                "parameters": parameters,
                "input": {},
            },
        }

    def _finish_task(self) -> dict[str, Any]:
        return {
            "header": {
                "action": "finish-task",
                "task_id": self.task_id,
                "streaming": "duplex",
            },
            "payload": {"input": {}},
        }

    async def _read_events(self) -> None:
        assert self._socket is not None
        try:
            async for raw in self._socket:
                if not isinstance(raw, str):
                    raise VoiceProviderError(
                        "Aliyun realtime ASR returned an unexpected binary event",
                        kind=VoiceErrorKind.INVALID_RESPONSE,
                        provider="aliyun",
                    )
                try:
                    message = json.loads(raw)
                    header = message["header"]
                    event_name = header["event"]
                except (ValueError, KeyError, TypeError) as exc:
                    raise VoiceProviderError(
                        "Aliyun realtime ASR returned a malformed event",
                        kind=VoiceErrorKind.INVALID_RESPONSE,
                        provider="aliyun",
                    ) from exc
                if header.get("task_id") != self.task_id:
                    continue
                if event_name == "task-started":
                    self._started.set()
                elif event_name == "result-generated":
                    await self._handle_result(message)
                elif event_name == "task-finished":
                    self._finished.set()
                    await self._events.put(TranscriptionEvent(type="finished", text=self._combined_text()))
                    break
                elif event_name == "task-failed":
                    code = str(header.get("error_code", "provider error"))[:120]
                    detail = str(header.get("error_message", "recognition failed"))[:500]
                    kind = (
                        VoiceErrorKind.TIMEOUT
                        if "timeout" in detail.lower()
                        else VoiceErrorKind.SERVER
                    )
                    raise VoiceProviderError(
                        f"Aliyun realtime ASR failed ({code}): {detail}",
                        kind=kind,
                        provider="aliyun",
                    )
        except asyncio.CancelledError:
            raise
        except VoiceProviderError as exc:
            self._set_error(exc)
        except ConnectionClosed as exc:
            if not self._cancelled and not self._finished.is_set():
                self._set_error(self._connection_error(exc))
        except Exception as exc:
            self._set_error(self._connection_error(exc))
        finally:
            if not self._started.is_set():
                self._started.set()
            if self._error is not None:
                self._finished.set()
            await self._events.put(None)

    async def _handle_result(self, message: dict[str, Any]) -> None:
        try:
            sentence = message["payload"]["output"]["sentence"]
            if sentence.get("heartbeat"):
                return
            sentence_id = int(sentence["sentence_id"])
            text = str(sentence.get("text", "")).strip()
            sentence_end = bool(sentence.get("sentence_end", False))
        except (KeyError, TypeError, ValueError) as exc:
            raise VoiceProviderError(
                "Aliyun realtime ASR returned an invalid result event",
                kind=VoiceErrorKind.INVALID_RESPONSE,
                provider="aliyun",
            ) from exc
        self._revision += 1
        if sentence_end:
            self._partials.pop(sentence_id, None)
            if text:
                self._final_sentences[sentence_id] = text
            event_type = "final"
        else:
            if text:
                self._partials[sentence_id] = text
            else:
                self._partials.pop(sentence_id, None)
            event_type = "partial"
        await self._events.put(
            TranscriptionEvent(
                type=event_type,
                text=self._combined_text(),
                sentence_id=sentence_id,
                revision=self._revision,
            )
        )

    def _combined_text(self) -> str:
        sentence_ids = sorted(set(self._final_sentences) | set(self._partials))
        return " ".join(
            self._final_sentences.get(index, self._partials.get(index, ""))
            for index in sentence_ids
            if self._final_sentences.get(index, self._partials.get(index, ""))
        ).strip()

    def _set_error(self, error: VoiceProviderError) -> None:
        if self._error is None:
            self._error = error
        self._started.set()
        self._finished.set()

    @staticmethod
    def _connection_error(exc: Exception) -> VoiceProviderError:
        status = None
        if isinstance(exc, InvalidStatus):
            status = getattr(getattr(exc, "response", None), "status_code", None)
        status = status or getattr(exc, "status_code", None)
        if status == 401:
            kind = VoiceErrorKind.AUTHENTICATION
        elif status == 403:
            kind = VoiceErrorKind.AUTHORIZATION
        elif status == 429:
            kind = VoiceErrorKind.RATE_LIMIT
        elif isinstance(status, int) and status >= 500:
            kind = VoiceErrorKind.SERVER
        else:
            kind = VoiceErrorKind.TRANSPORT
        suffix = f" (HTTP {status})" if status else ""
        return VoiceProviderError(
            f"Aliyun realtime ASR connection failed{suffix}: {str(exc)[:400]}",
            kind=kind,
            provider="aliyun",
            status_code=status if isinstance(status, int) else None,
        )

    async def _close_socket(self) -> None:
        reader = self._reader_task
        self._reader_task = None
        if reader is not None and reader is not asyncio.current_task() and not reader.done():
            reader.cancel()
            try:
                await reader
            except asyncio.CancelledError:
                pass
        socket = self._socket
        self._socket = None
        if socket is not None:
            try:
                await socket.close()
            except Exception:
                pass
