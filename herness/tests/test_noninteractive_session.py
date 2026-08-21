from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from octocoder.agent import LoopComplete, StreamText, TurnComplete, UsageEvent
from octocoder.context_observer import ContextLifecycleObservation
from octocoder.conversation import ConversationManager
from octocoder.memory.session import SessionManager
from octocoder.noninteractive import NonInteractiveSession
from octocoder.permissions import PermissionMode


class FakeAgent:
    def __init__(self) -> None:
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.session_id = ""
        self.stage_id = ""
        self._events = []

    def set_context_stage(self, stage_id: str, checkpoint_id: str | None = None) -> None:
        self.stage_id = stage_id

    def emit(self, event: ContextLifecycleObservation) -> None:
        from octocoder.agent import ContextEventNotification

        self._events.append(ContextEventNotification(event.event_type, dict(event.payload)))

    def _drain_context_events(self):
        events = self._events
        self._events = []
        return events

    async def run(self, conversation: ConversationManager):
        prompt = conversation.history[-1].content
        response = f"reply:{prompt}"
        self.total_input_tokens += 10
        self.total_output_tokens += 2
        yield StreamText(response)
        yield UsageEvent(self.total_input_tokens, self.total_output_tokens)
        conversation.add_assistant_message(response)
        yield TurnComplete(1)
        yield LoopComplete(1)


def make_session(
    tmp_path: Path,
    events: list[dict],
    *,
    model: str = "fake-model",
) -> NonInteractiveSession:
    provider = SimpleNamespace(name="fake", model=model)
    config = SimpleNamespace(providers=[provider])
    session = NonInteractiveSession(
        config=config,
        permission_mode=PermissionMode.BYPASS,
        hook_engine=None,
        event_sink=events.append,
        work_dir=str(tmp_path),
    )
    session.client = object()
    session.agent = FakeAgent()
    session.conversation = ConversationManager()
    session.trace_manager = SimpleNamespace(_nodes={})
    session.task_manager = SimpleNamespace(_async_tasks={})
    session.team_manager = SimpleNamespace(_teams={})
    session.session_manager = SessionManager(str(tmp_path), observer=session.agent)
    session.session = session.session_manager.create()
    session.agent.session_id = session.session.session_id
    return session


@pytest.mark.asyncio
async def test_persistent_session_keeps_multiple_turns(tmp_path: Path) -> None:
    events: list[dict] = []
    session = make_session(tmp_path, events)

    first = await session.run_turn("one", stage_id="setup")
    second = await session.run_turn("two", stage_id="probe")

    assert first.text == "reply:one"
    assert second.text == "reply:two"
    assert [message.content for message in session.conversation.history] == [
        "one",
        "reply:one",
        "two",
        "reply:two",
    ]
    assert second.input_tokens == 20
    assert [event["type"] for event in events].count("result") == 2
    await session.close()


@pytest.mark.asyncio
async def test_persist_resume_reconstructs_real_session_records(tmp_path: Path) -> None:
    events: list[dict] = []
    session = make_session(tmp_path, events)
    await session.run_turn("remember alpha", stage_id="setup")

    resumed = await session.persist_and_resume("resume")

    assert resumed.restored_messages == 2
    assert [message.content for message in session.conversation.history] == [
        "remember alpha",
        "reply:remember alpha",
    ]
    assert any(
        event.get("type") == "context"
        and event.get("event_type") == "session_resumed"
        for event in events
    )
    follow_up = await session.run_turn("continue", stage_id="after-resume")
    assert follow_up.text == "reply:continue"
    await session.close()


@pytest.mark.asyncio
async def test_new_agent_with_different_model_resumes_existing_session(
    tmp_path: Path,
) -> None:
    first_events: list[dict] = []
    first = make_session(tmp_path, first_events, model="model-alpha")
    await first.run_turn("remember release RC-42", stage_id="setup")
    session_id = first.session.session_id
    await first.close()

    second_events: list[dict] = []
    second = make_session(tmp_path, second_events, model="model-beta")
    resumed = await second.resume_existing(session_id, "cross-model-resume")

    assert resumed.restored_messages == 2
    assert second.provider.model == "model-beta"
    assert [message.content for message in second.conversation.history] == [
        "remember release RC-42",
        "reply:remember release RC-42",
    ]
    follow_up = await second.run_turn("continue", stage_id="after-restart")
    assert follow_up.text == "reply:continue"
    assert any(
        event.get("type") == "context"
        and event.get("event_type") == "session_resumed"
        for event in second_events
    )
    await second.close()


@pytest.mark.asyncio
async def test_checkpoint_reports_tool_pair_and_bounded_state(tmp_path: Path) -> None:
    session = make_session(tmp_path, [])
    await session.run_turn("hello")
    checkpoint = await session.checkpoint("after")
    assert checkpoint["id"] == "after"
    assert checkpoint["answer"] == "reply:hello"
    assert checkpoint["tool_pair_complete"] is True
    assert checkpoint["task_state"]["message_count"] == 2
    await session.close()


@pytest.mark.asyncio
async def test_close_is_idempotent_and_rejects_future_turns(tmp_path: Path) -> None:
    session = make_session(tmp_path, [])
    await session.close()
    await session.close()
    with pytest.raises(RuntimeError, match="closed"):
        await session.run_turn("too late")
