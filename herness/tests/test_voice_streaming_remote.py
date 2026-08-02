from __future__ import annotations

import asyncio
import json
import struct
from unittest.mock import AsyncMock

import pytest

import octocoder.remote as remote_module
import octocoder.voice.session as session_module
from octocoder.config import VoiceConfig, VoiceProviderProfile
from octocoder.client import NetworkError
from octocoder.conversation import ConversationManager
from octocoder.agent import LoopComplete, StreamText, ThinkingText
from octocoder.remote import RemoteServer
from octocoder.voice.fallback import fallback_profiles, transcribe_with_fallback
from octocoder.voice.models import TranscriptionEvent
from octocoder.voice.provider import VoiceErrorKind, VoiceProviderError
from octocoder.voice.session import RealtimeVoiceSession


class FakeBatchProvider:
    def __init__(self, profile_id: str, calls: list, outcome) -> None:
        self.profile_id = profile_id
        self.calls = calls
        self.outcome = outcome

    async def transcribe(self, audio: bytes, **kwargs) -> str:
        self.calls.append((self.profile_id, audio, kwargs))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeStreamingSession:
    def __init__(self, *, result: str = "stream transcript", error=None, events=None) -> None:
        self.result = result
        self.error = error
        self.audio: list[bytes] = []
        self.cancelled = 0
        self._events = events or []

    async def start(self) -> None:
        return None

    async def send_audio(self, pcm16: bytes) -> None:
        self.audio.append(pcm16)

    async def finish(self) -> str:
        if self.error is not None:
            raise self.error
        return self.result

    async def cancel(self) -> None:
        self.cancelled += 1

    async def events(self):
        for event in self._events:
            yield event


class FakeStreamingProvider:
    def __init__(self, session: FakeStreamingSession) -> None:
        self.session = session
        self.requests: list[str] = []

    async def create_session(self, request_id: str):
        self.requests.append(request_id)
        return self.session


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str | bytes] = []

    async def send(self, value: str | bytes) -> None:
        self.sent.append(value)


class RetryAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, conversation):
        self.calls += 1
        if self.calls == 1:
            yield ThinkingText("partial thinking")
            raise NetworkError("incomplete chunked read")
        conversation.add_assistant_message("recovered")
        yield StreamText("recovered")
        yield LoopComplete(total_turns=1)


def _messages(socket: FakeSocket) -> list[dict]:
    return [json.loads(value) for value in socket.sent if isinstance(value, str)]


def _profile(profile_id: str, provider: str, *, base_url: str | None = None):
    return VoiceProviderProfile(
        id=profile_id,
        name=profile_id,
        provider=provider,
        base_url=base_url or f"https://{profile_id}.example/v1",
        api_key=f"{profile_id}-secret",
        batch_stt_model=f"{profile_id}-model",
    )


def _config() -> VoiceConfig:
    return VoiceConfig(
        enabled=True,
        primary_asr_profile="primary",
        fallback_asr_profiles=["backup", "last"],
        profiles=[
            _profile("primary", "aliyun"),
            _profile("backup", "siliconflow"),
            _profile("last", "openai-compatible"),
        ],
    )


def _streaming_config() -> VoiceConfig:
    profile = VoiceProviderProfile(
        id="aliyun-main",
        name="Aliyun",
        provider="aliyun",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        streaming_url="wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        api_key="test-secret",
        batch_stt_model="qwen3-asr-flash",
        streaming_stt_model="qwen-audio-3.0-asr-flash-streaming",
    )
    return VoiceConfig(
        enabled=True,
        auto_submit=True,
        primary_asr_profile=profile.id,
        profiles=[profile],
    )


@pytest.mark.asyncio
async def test_remote_retries_network_stream_without_leaving_stale_user_turn(monkeypatch) -> None:
    server = RemoteServer(providers=[])
    server.conversation = ConversationManager()
    server.agent = RetryAgent()
    server._broadcast = AsyncMock()
    sleep = AsyncMock()
    monkeypatch.setattr(remote_module.asyncio, "sleep", sleep)

    await server._handle_user_message("current voice text")

    assert server.agent.calls == 2
    assert [message.content for message in server.conversation.history] == [
        "current voice text",
        "recovered",
    ]
    assert any(
        call.args[0]["type"] == "retry"
        for call in server._broadcast.await_args_list
    )


@pytest.mark.asyncio
async def test_realtime_session_forwards_ordered_pcm_and_finishes_once() -> None:
    upstream = FakeStreamingSession()
    session = RealtimeVoiceSession(
        _streaming_config(), FakeStreamingProvider(upstream), "req-1"
    )
    await session.start()
    session.append_chunk(0, b"\x01\x00")
    session.append_chunk(1, b"\x02\x00")
    first, second = await asyncio.gather(session.finish(), session.finish())
    assert first == second
    assert upstream.audio == [b"\x01\x00", b"\x02\x00"]
    assert first.text == "stream transcript"
    assert session.mark_submitted() is True
    assert session.mark_submitted() is False


@pytest.mark.asyncio
async def test_realtime_session_emits_revisioned_partial_events() -> None:
    seen: list[TranscriptionEvent] = []
    upstream = FakeStreamingSession(events=[
        TranscriptionEvent(type="partial", text="hello", sentence_id=1, revision=1),
        TranscriptionEvent(type="final", text="hello world", sentence_id=1, revision=2),
    ])
    session = RealtimeVoiceSession(
        _streaming_config(),
        FakeStreamingProvider(upstream),
        "req",
        on_partial=lambda event: _append_event(seen, event),
    )
    await session.start()
    await asyncio.sleep(0)
    session.append_chunk(0, b"\x00\x00")
    await session.finish()
    assert [(event.text, event.revision) for event in seen] == [
        ("hello", 1),
        ("hello world", 2),
    ]


async def _append_event(seen: list[TranscriptionEvent], event: TranscriptionEvent) -> None:
    seen.append(event)


@pytest.mark.asyncio
async def test_realtime_session_rejects_sequence_and_queue_overflow(monkeypatch) -> None:
    upstream = FakeStreamingSession()
    session = RealtimeVoiceSession(
        _streaming_config(), FakeStreamingProvider(upstream), "req"
    )
    await session.start()
    with pytest.raises(VoiceProviderError, match="expected 0"):
        session.append_chunk(1, b"\x00\x00")
    monkeypatch.setattr(session_module, "MAX_PCM_QUEUE_BYTES", 2)
    session.append_chunk(0, b"\x00\x00")
    with pytest.raises(VoiceProviderError, match="queue is full"):
        session.append_chunk(1, b"\x00\x00")
    await session.cancel()


@pytest.mark.asyncio
async def test_remote_stream_protocol_submits_exactly_once(monkeypatch) -> None:
    upstream = FakeStreamingSession(result="do the work")
    provider = FakeStreamingProvider(upstream)
    monkeypatch.setattr(
        remote_module, "create_streaming_asr_provider", lambda _profile: provider
    )
    server = RemoteServer(providers=[])
    server.voice_config = _streaming_config()
    server._handle_user_message = AsyncMock()
    socket = FakeSocket()

    start = await server._handle_voice_stream_start(socket, {
        "requestId": "req-1",
        "mode": "hold",
        "format": "pcm_s16le",
        "sampleRate": 16000,
        "channels": 1,
    })
    assert start is not None
    await start
    await server._handle_voice_stream_chunk(socket, {
        "requestId": "req-1", "sequence": 0, "byteLength": 2,
    })
    await server._handle_voice_binary(socket, b"\x00\x00")
    finish_one = await server._handle_voice_stream_finish(socket, {"requestId": "req-1"})
    finish_two = await server._handle_voice_stream_finish(socket, {"requestId": "req-1"})
    assert finish_one is finish_two
    assert finish_one is not None
    await finish_one

    server._handle_user_message.assert_awaited_once_with(
        "do the work",
        source="voice",
        voice_request_id="req-1",
        requester=socket,
    )
    transcripts = [message for message in _messages(socket) if message["type"] == "voice_transcript"]
    assert len(transcripts) == 1
    assert transcripts[0]["data"]["fallbackUsed"] is False
    assert upstream.audio == [b"\x00\x00"]


@pytest.mark.asyncio
async def test_remote_stream_rejects_mismatched_binary_length(monkeypatch) -> None:
    upstream = FakeStreamingSession()
    monkeypatch.setattr(
        remote_module,
        "create_streaming_asr_provider",
        lambda _profile: FakeStreamingProvider(upstream),
    )
    server = RemoteServer(providers=[])
    server.voice_config = _streaming_config()
    socket = FakeSocket()
    start = await server._handle_voice_stream_start(socket, {"requestId": "req"})
    assert start is not None
    await start
    await server._handle_voice_stream_chunk(
        socket, {"requestId": "req", "sequence": 0, "byteLength": 4}
    )
    await server._handle_voice_binary(socket, b"\x00\x00")
    assert socket not in server._voice_streams
    assert _messages(socket)[-1]["type"] == "voice_error"


@pytest.mark.asyncio
async def test_continuous_stream_queues_one_turn_while_agent_busy(monkeypatch) -> None:
    upstream = FakeStreamingSession(result="queued follow up")
    monkeypatch.setattr(
        remote_module,
        "create_streaming_asr_provider",
        lambda _profile: FakeStreamingProvider(upstream),
    )
    server = RemoteServer(providers=[])
    server.voice_config = _streaming_config()
    server._streaming = True
    server._handle_user_message = AsyncMock()
    socket = FakeSocket()
    start = await server._handle_voice_stream_start(socket, {
        "requestId": "queued", "mode": "continuous",
    })
    assert start is not None
    await start
    await server._handle_voice_stream_chunk(
        socket, {"requestId": "queued", "sequence": 0, "byteLength": 2}
    )
    await server._handle_voice_binary(socket, b"\x00\x00")
    finish = await server._handle_voice_stream_finish(socket, {"requestId": "queued"})
    assert finish is not None
    await finish
    assert server._pending_voice_turn == (socket, "queued", "queued follow up")
    server._handle_user_message.assert_not_awaited()
    assert any(
        message["type"] == "voice_status" and message["data"]["phase"] == "queued"
        for message in _messages(socket)
    )

    server._streaming = False
    pending = server._start_pending_voice_turn()
    assert pending is not None
    await pending
    server._handle_user_message.assert_awaited_once_with(
        "queued follow up",
        source="voice",
        voice_request_id="queued",
        requester=socket,
    )


@pytest.mark.asyncio
async def test_fallback_uses_ordered_profiles_and_one_wav() -> None:
    config = _config()
    calls: list = []
    outcomes = {
        "primary": VoiceProviderError("primary busy", kind=VoiceErrorKind.SERVER),
        "backup": "fallback transcript",
        "last": "unused",
    }

    def factory(profile):
        return FakeBatchProvider(profile.id, calls, outcomes[profile.id])

    result = await transcribe_with_fallback(
        config,
        struct.pack("<hhhh", 1, 2, 3, 4),
        VoiceProviderError("stream closed", kind=VoiceErrorKind.TRANSPORT),
        provider_factory=factory,
    )
    assert result.text == "fallback transcript"
    assert result.profile_id == "backup"
    assert [call[0] for call in calls] == ["primary", "backup"]
    assert calls[0][1] is calls[1][1]
    assert calls[0][1][:4] == b"RIFF"


@pytest.mark.asyncio
async def test_non_retryable_streaming_error_never_calls_fallback() -> None:
    called = False

    def factory(_profile):
        nonlocal called
        called = True
        raise AssertionError("must not be called")

    error = VoiceProviderError("unauthorized", kind=VoiceErrorKind.AUTHORIZATION)
    with pytest.raises(VoiceProviderError) as caught:
        await transcribe_with_fallback(
            _config(), b"\x00\x00", error, provider_factory=factory
        )
    assert caught.value is error
    assert called is False


@pytest.mark.asyncio
async def test_non_retryable_fallback_error_stops_order() -> None:
    calls: list = []
    outcomes = {
        "primary": VoiceProviderError("bad key", kind=VoiceErrorKind.AUTHENTICATION),
        "backup": "must not run",
        "last": "must not run",
    }

    def factory(profile):
        return FakeBatchProvider(profile.id, calls, outcomes[profile.id])

    with pytest.raises(VoiceProviderError) as caught:
        await transcribe_with_fallback(
            _config(),
            b"\x00\x00",
            VoiceProviderError("stream lost", kind=VoiceErrorKind.TRANSPORT),
            provider_factory=factory,
        )
    assert caught.value.kind is VoiceErrorKind.AUTHENTICATION
    assert [call[0] for call in calls] == ["primary"]


def test_fallback_profiles_deduplicate_capabilities() -> None:
    primary = _profile("primary", "openai-compatible", base_url="https://same.example/v1")
    duplicate = VoiceProviderProfile(
        **{
            **primary.__dict__,
            "id": "duplicate",
            "name": "duplicate",
        }
    )
    config = VoiceConfig(
        enabled=True,
        primary_asr_profile="primary",
        fallback_asr_profiles=["duplicate"],
        profiles=[primary, duplicate],
    )
    assert [profile.id for profile in fallback_profiles(config)] == ["primary"]


@pytest.mark.asyncio
async def test_exhausted_retryable_fallback_is_sanitized() -> None:
    calls: list = []

    def factory(profile):
        return FakeBatchProvider(
            profile.id,
            calls,
            VoiceProviderError("temporary", kind=VoiceErrorKind.SERVER),
        )

    with pytest.raises(VoiceProviderError, match="fallback failed") as caught:
        await transcribe_with_fallback(
            _config(),
            b"\x00\x00",
            VoiceProviderError("stream lost", kind=VoiceErrorKind.TRANSPORT),
            provider_factory=factory,
        )
    assert caught.value.retryable is True
    assert [call[0] for call in calls] == ["primary", "backup", "last"]
