from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from octocoder.config import VoiceProviderProfile
from octocoder.voice import VoiceErrorKind, VoiceProviderError, create_streaming_asr_provider


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []
        self.incoming: asyncio.Queue[str | None] = asyncio.Queue()
        self.sent_event = asyncio.Event()
        self.closed = False

    async def send(self, value: str | bytes) -> None:
        self.sent.append(value)
        self.sent_event.set()

    async def close(self) -> None:
        self.closed = True
        await self.incoming.put(None)

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        value = await self.incoming.get()
        if value is None:
            raise StopAsyncIteration
        return value

    async def push(self, value: dict[str, Any]) -> None:
        await self.incoming.put(json.dumps(value))

    async def wait_for_sent(self, count: int) -> None:
        while len(self.sent) < count:
            self.sent_event.clear()
            await asyncio.wait_for(self.sent_event.wait(), 1)


def _profile() -> VoiceProviderProfile:
    return VoiceProviderProfile(
        id="aliyun-main",
        provider="aliyun",
        base_url="https://dashscope.aliyuncs.com",
        streaming_url="wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        workspace_id="workspace-id",
        api_key="fake-secret",
        batch_stt_model="qwen3-asr-flash",
        streaming_stt_model="qwen-audio-3.0-asr-flash-streaming",
        language="zh",
    )


def _event(task_id: str, name: str, **header_values: Any) -> dict[str, Any]:
    return {
        "header": {"task_id": task_id, "event": name, **header_values},
        "payload": {},
    }


def _result(task_id: str, sentence_id: int, text: str, *, final: bool, heartbeat: bool = False):
    return {
        "header": {"task_id": task_id, "event": "result-generated"},
        "payload": {
            "output": {
                "sentence": {
                    "sentence_id": sentence_id,
                    "text": text,
                    "sentence_end": final,
                    "heartbeat": heartbeat,
                }
            }
        },
    }


@pytest.mark.asyncio
async def test_aliyun_streaming_command_and_event_flow() -> None:
    socket = FakeWebSocket()
    captured: dict[str, Any] = {}

    async def connector(url: str, **kwargs):
        captured.update({"url": url, **kwargs})
        return socket

    provider = create_streaming_asr_provider(_profile(), connector=connector)
    session = await provider.create_session("request-1")
    start_task = asyncio.create_task(session.start())
    await socket.wait_for_sent(1)
    run_task = json.loads(socket.sent[0])
    assert captured["url"].startswith("wss://dashscope.aliyuncs.com")
    assert captured["additional_headers"]["Authorization"] == "Bearer fake-secret"
    assert captured["additional_headers"]["X-DashScope-WorkSpace"] == "workspace-id"
    assert run_task["header"]["action"] == "run-task"
    assert run_task["payload"]["model"] == "qwen-audio-3.0-asr-flash-streaming"
    assert run_task["payload"]["parameters"] == {
        "format": "pcm",
        "sample_rate": 16000,
        "heartbeat": True,
        "language_hints": ["zh"],
    }
    await socket.push(_event(session.task_id, "task-started"))
    await start_task

    events_task = asyncio.create_task(_collect(session.events()))
    await session.send_audio(b"\x00\x00" * 800)
    assert socket.sent[1] == b"\x00\x00" * 800
    await socket.push(_result(session.task_id, 0, "", final=False, heartbeat=True))
    await socket.push(_result(session.task_id, 1, "你", final=False))
    await socket.push(_result(session.task_id, 1, "你好", final=False))
    await socket.push(_result(session.task_id, 1, "你好", final=True))
    await socket.push(_result(session.task_id, 2, "世界", final=True))

    finish_task = asyncio.create_task(session.finish())
    await socket.wait_for_sent(3)
    finish = json.loads(socket.sent[2])
    assert finish["header"]["action"] == "finish-task"
    await socket.push(_event(session.task_id, "task-finished"))
    assert await finish_task == "你好 世界"
    events = await events_task
    assert [event.type for event in events] == ["partial", "partial", "final", "final", "finished"]
    assert events[0].text == "你"
    assert events[1].text == "你好"
    assert events[-1].text == "你好 世界"
    assert socket.closed is True


async def _collect(iterator) -> list:
    return [event async for event in iterator]


@pytest.mark.asyncio
async def test_aliyun_task_failure_is_classified_and_sanitized() -> None:
    socket = FakeWebSocket()

    async def connector(_url: str, **_kwargs):
        return socket

    provider = create_streaming_asr_provider(_profile(), connector=connector)
    session = await provider.create_session("request-2")
    start_task = asyncio.create_task(session.start())
    await socket.wait_for_sent(1)
    await socket.push(
        _event(
            session.task_id,
            "task-failed",
            error_code="CLIENT_ERROR",
            error_message="request timeout after 23 seconds",
        )
    )
    with pytest.raises(VoiceProviderError) as caught:
        await start_task
    assert caught.value.kind is VoiceErrorKind.TIMEOUT
    assert caught.value.retryable is True
    assert "fake-secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, kind, retryable",
    [
        (401, VoiceErrorKind.AUTHENTICATION, False),
        (403, VoiceErrorKind.AUTHORIZATION, False),
        (429, VoiceErrorKind.RATE_LIMIT, True),
        (503, VoiceErrorKind.SERVER, True),
    ],
)
async def test_aliyun_handshake_failures_are_classified(status, kind, retryable) -> None:
    class HandshakeFailure(Exception):
        status_code = status

    async def connector(_url: str, **_kwargs):
        raise HandshakeFailure("handshake rejected")

    provider = create_streaming_asr_provider(_profile(), connector=connector)
    session = await provider.create_session("request-3")
    with pytest.raises(VoiceProviderError) as caught:
        await session.start()
    assert caught.value.kind is kind
    assert caught.value.retryable is retryable
    assert caught.value.status_code == status


@pytest.mark.asyncio
async def test_aliyun_malformed_event_is_recoverable() -> None:
    socket = FakeWebSocket()

    async def connector(_url: str, **_kwargs):
        return socket

    provider = create_streaming_asr_provider(_profile(), connector=connector)
    session = await provider.create_session("request-4")
    start_task = asyncio.create_task(session.start())
    await socket.wait_for_sent(1)
    await socket.incoming.put("not-json")
    with pytest.raises(VoiceProviderError) as caught:
        await start_task
    assert caught.value.kind is VoiceErrorKind.INVALID_RESPONSE
    assert caught.value.retryable is False
