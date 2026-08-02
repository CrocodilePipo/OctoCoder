from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock

import pytest

import octocoder.remote as remote_module
from octocoder.agent import LoopComplete, StreamText, ToolUseEvent, TurnComplete
from octocoder.config import VoiceConfig
from octocoder.conversation import ConversationManager
from octocoder.remote import RemoteServer
from octocoder.voice import VoiceAudio, VoiceProviderError


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def send(self, value: str | bytes) -> None:
        self.sent.append(value)


class FakeVoiceProvider:
    def __init__(self, transcript: str = "voice task") -> None:
        self.transcript = transcript
        self.transcriptions: list[tuple[bytes, str, str, str]] = []
        self.speech_inputs: list[str] = []

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str:
        self.transcriptions.append((audio, filename, content_type, language))
        return self.transcript

    async def synthesize(self, text: str) -> VoiceAudio:
        self.speech_inputs.append(text)
        return VoiceAudio(data=f"audio:{text}".encode(), content_type="audio/mpeg")


class FakeAgent:
    def __init__(self, events) -> None:
        self.events = events

    async def run(self, _conversation):
        for event in self.events:
            yield event


def _server(*, auto_submit: bool = False) -> tuple[RemoteServer, FakeVoiceProvider]:
    server = RemoteServer(providers=[])
    server.voice_config = VoiceConfig(
        enabled=True,
        base_url="https://voice.example/v1",
        api_key="voice-secret",
        auto_submit=auto_submit,
        declared=True,
    )
    provider = FakeVoiceProvider()
    server.voice_provider = provider
    server.tts_provider = provider
    return server, provider


def _json_messages(socket: FakeSocket) -> list[dict]:
    return [json.loads(value) for value in socket.sent if isinstance(value, str)]


async def _record(server: RemoteServer, socket: FakeSocket, request_id: str = "req-1"):
    await server._handle_voice_start(
        socket, {"requestId": request_id, "mimeType": "audio/webm;codecs=opus"}
    )
    await server._handle_voice_binary(socket, b"encoded-audio")
    task = await server._handle_voice_stop(socket, {"requestId": request_id})
    assert task is not None
    await task


async def _drain_tasks(server: RemoteServer, socket: FakeSocket) -> None:
    await asyncio.sleep(0)
    tasks = list(server._voice_tasks.get(socket, set()))
    if tasks:
        await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_upload_transcribes_and_returns_manual_transcript() -> None:
    server, provider = _server(auto_submit=False)
    socket = FakeSocket()
    await _record(server, socket)

    assert provider.transcriptions == [
        (b"encoded-audio", "recording.webm", "audio/webm;codecs=opus", "")
    ]
    transcript = [m for m in _json_messages(socket) if m["type"] == "voice_transcript"]
    assert transcript == [
        {
            "type": "voice_transcript",
            "data": {"requestId": "req-1", "text": "voice task", "submitted": False},
        }
    ]


@pytest.mark.asyncio
async def test_auto_submit_invokes_user_handler_exactly_once() -> None:
    server, _provider = _server(auto_submit=True)
    socket = FakeSocket()
    server._handle_user_message = AsyncMock()
    await _record(server, socket)

    server._handle_user_message.assert_awaited_once_with(
        "voice task",
        source="voice",
        voice_request_id="req-1",
        requester=socket,
    )
    transcript = [m for m in _json_messages(socket) if m["type"] == "voice_transcript"]
    assert transcript[0]["data"]["submitted"] is True


@pytest.mark.asyncio
async def test_binary_without_upload_is_recoverable() -> None:
    server, _provider = _server()
    socket = FakeSocket()
    await server._handle_voice_binary(socket, b"unexpected")
    assert _json_messages(socket)[-1]["type"] == "voice_error"


@pytest.mark.asyncio
async def test_upload_size_limit_is_enforced(monkeypatch) -> None:
    monkeypatch.setattr(remote_module, "MAX_RECORDING_BYTES", 3)
    server, provider = _server()
    socket = FakeSocket()
    await server._handle_voice_start(socket, {"requestId": "req", "mimeType": "audio/webm"})
    await server._handle_voice_binary(socket, b"four")
    assert socket not in server._voice_uploads
    assert provider.transcriptions == []
    assert "16 MiB" in _json_messages(socket)[-1]["data"]["message"]


@pytest.mark.asyncio
async def test_upload_duration_limit_is_enforced() -> None:
    server, provider = _server()
    socket = FakeSocket()
    await server._handle_voice_start(socket, {"requestId": "req", "mimeType": "audio/webm"})
    await server._handle_voice_binary(socket, b"audio")
    server._voice_uploads[socket].started_at = time.monotonic() - 121
    task = await server._handle_voice_stop(socket, {"requestId": "req"})
    assert task is None
    assert provider.transcriptions == []
    assert "120 second" in _json_messages(socket)[-1]["data"]["message"]


@pytest.mark.asyncio
async def test_disconnect_style_cancel_clears_active_upload() -> None:
    server, _provider = _server()
    socket = FakeSocket()
    await server._handle_voice_start(socket, {"requestId": "req", "mimeType": "audio/webm"})
    await server._handle_voice_cancel(socket, {"requestId": "req"})
    assert socket not in server._voice_uploads
    assert _json_messages(socket)[-1]["data"]["phase"] == "idle"


@pytest.mark.asyncio
async def test_disconnected_requester_does_not_start_tts() -> None:
    server, provider = _server()
    socket = FakeSocket()
    server.conversation = ConversationManager()
    server.agent = FakeAgent(
        [StreamText("Final answer."), TurnComplete(turn=1), LoopComplete(total_turns=1)]
    )

    await server._handle_user_message(
        "voice", source="voice", voice_request_id="req", requester=socket
    )
    await _drain_tasks(server, socket)

    assert provider.speech_inputs == []


@pytest.mark.asyncio
async def test_voice_agent_speaks_only_latest_non_tool_final_turn() -> None:
    server, provider = _server()
    socket = FakeSocket()
    server._connections.add(socket)
    server.conversation = ConversationManager()
    server.agent = FakeAgent(
        [
            StreamText("I will inspect the project."),
            ToolUseEvent(tool_name="read_file", tool_id="tool-1", arguments={}),
            TurnComplete(turn=1),
            StreamText("Final **answer**.\n```python\nsecret = 1\n```"),
            TurnComplete(turn=2),
            LoopComplete(total_turns=2),
        ]
    )

    await server._handle_user_message(
        "do work", source="voice", voice_request_id="req", requester=socket
    )
    await _drain_tasks(server, socket)

    assert provider.speech_inputs == ["Final answer."]
    messages = _json_messages(socket)
    assert any(message["type"] == "voice_audio_start" for message in messages)
    assert any(isinstance(value, bytes) and value.startswith(b"audio:") for value in socket.sent)


@pytest.mark.asyncio
async def test_typed_agent_task_never_calls_tts() -> None:
    server, provider = _server()
    socket = FakeSocket()
    server._connections.add(socket)
    server.conversation = ConversationManager()
    server.agent = FakeAgent(
        [StreamText("Typed final."), TurnComplete(turn=1), LoopComplete(total_turns=1)]
    )
    await server._handle_user_message("typed", requester=socket)
    await _drain_tasks(server, socket)
    assert provider.speech_inputs == []


@pytest.mark.asyncio
async def test_tts_failure_does_not_remove_completed_text() -> None:
    class FailingProvider(FakeVoiceProvider):
        async def synthesize(self, text: str) -> VoiceAudio:
            raise VoiceProviderError("tts unavailable")

    server, _provider = _server()
    server.tts_provider = FailingProvider()
    socket = FakeSocket()
    server._connections.add(socket)
    server.conversation = ConversationManager()
    server.agent = FakeAgent(
        [StreamText("Final answer."), TurnComplete(turn=1), LoopComplete(total_turns=1)]
    )
    await server._handle_user_message(
        "voice", source="voice", voice_request_id="req", requester=socket
    )
    await _drain_tasks(server, socket)
    messages = _json_messages(socket)
    assert any(message["type"] == "stream_text" for message in messages)
    assert any(
        message["type"] == "voice_error" and "tts unavailable" in message["data"]["message"]
        for message in messages
    )


@pytest.mark.asyncio
async def test_asr_only_voice_task_never_calls_tts() -> None:
    server, provider = _server()
    server.tts_provider = None
    socket = FakeSocket()
    server._connections.add(socket)
    server.conversation = ConversationManager()
    server.agent = FakeAgent(
        [StreamText("Final answer."), TurnComplete(turn=1), LoopComplete(total_turns=1)]
    )
    await server._handle_user_message(
        "voice", source="voice", voice_request_id="req", requester=socket
    )
    await _drain_tasks(server, socket)
    assert provider.speech_inputs == []
    phases = [
        message["data"]["phase"]
        for message in _json_messages(socket)
        if message["type"] == "voice_status"
    ]
    assert phases == ["analyzing", "idle"]


@pytest.mark.asyncio
async def test_voice_agent_phases_are_visible_and_deduplicated() -> None:
    server, _provider = _server()
    socket = FakeSocket()
    server._connections.add(socket)
    server.conversation = ConversationManager()
    server.agent = FakeAgent([
        ToolUseEvent(tool_name="read_file", tool_id="tool-1", arguments={}),
        ToolUseEvent(tool_name="read_file", tool_id="tool-2", arguments={}),
        LoopComplete(total_turns=1),
    ])
    await server._handle_user_message(
        "voice", source="voice", voice_request_id="req", requester=socket
    )
    await _drain_tasks(server, socket)
    phases = [
        message["data"]["phase"]
        for message in _json_messages(socket)
        if message["type"] == "voice_status"
    ]
    assert phases == ["analyzing", "executing", "idle"]


@pytest.mark.asyncio
async def test_playback_interrupt_does_not_cancel_agent() -> None:
    server, _provider = _server()
    socket = FakeSocket()
    agent_cancel = asyncio.Event()
    server._cancel_event = agent_cancel
    blocker = asyncio.Event()

    async def blocked_synthesis():
        await blocker.wait()

    task = server._track_voice_playback(socket, blocked_synthesis())
    await asyncio.sleep(0)
    await server._handle_voice_playback_interrupt(socket, {"requestId": "req"})
    await asyncio.gather(task, return_exceptions=True)
    assert agent_cancel.is_set() is False
    assert _json_messages(socket)[-1]["type"] == "voice_audio_cancel"
