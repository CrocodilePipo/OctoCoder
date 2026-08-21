from __future__ import annotations

from pathlib import Path

import pytest

from octocoder.context.manager import (
    SINGLE_RESULT_CHAR_LIMIT,
    apply_tool_result_budget,
    auto_compact,
    create_replacement_state,
)
from octocoder.context_observer import ContextLifecycleObservation, NullContextObserver
from octocoder.conversation import ConversationManager, Message, ToolResultBlock
from octocoder.memory.session import (
    RecordType,
    SessionRecord,
    SessionManager,
    make_compact_boundary,
)
from datetime import datetime, timezone
from octocoder.agent import Agent
from octocoder.tools import ToolRegistry


class Collector:
    def __init__(self) -> None:
        self.events: list[ContextLifecycleObservation] = []

    def emit(self, event: ContextLifecycleObservation) -> None:
        self.events.append(event)


class RaisingObserver:
    def emit(self, event: ContextLifecycleObservation) -> None:
        raise RuntimeError("observer failure")


class SummaryClient:
    async def stream(self, conversation, system="", tools=None):
        from octocoder.tools.base import StreamEnd, TextDelta

        yield TextDelta(text="<summary>bounded summary</summary>")
        yield StreamEnd(stop_reason="end_turn", input_tokens=10, output_tokens=2)


class FailingSummaryClient:
    async def stream(self, conversation, system="", tools=None):
        raise RuntimeError("provider secret must not be observed")
        yield  # pragma: no cover


def long_conversation() -> ConversationManager:
    conversation = ConversationManager()
    for index in range(12):
        conversation.history.append(
            Message(role="user", content=f"old-{index}-" + "x" * 12_000)
        )
        conversation.history.append(
            Message(role="assistant", content=f"answer-{index}-" + "y" * 12_000)
        )
    for index in range(6):
        conversation.history.append(
            Message(role="user", content=f"recent-{index}-" + "z" * 8_000)
        )
    return conversation


def test_usage_anchor_observation_keeps_accounting_unchanged() -> None:
    conversation = ConversationManager()
    conversation.add_user_message("hello")
    expected = ConversationManager()
    expected.add_user_message("hello")
    collector = Collector()

    conversation.record_usage_anchor(100, 10, 5, 3, observer=collector)
    expected.record_usage_anchor(100, 10, 5, 3, observer=NullContextObserver())

    assert conversation.current_tokens() == expected.current_tokens() == 118
    assert collector.events[0].event_type == "usage_anchor"
    assert collector.events[0].payload["provider_tokens"] == 118
    assert set(collector.events[0].payload) == {
        "estimated_tokens",
        "provider_tokens",
        "anchor_message_count",
    }


def test_tool_spill_observation_is_bounded_and_hashed(tmp_path: Path) -> None:
    conversation = ConversationManager()
    conversation.history.append(
        Message(
            role="user",
            content="",
            tool_results=[
                ToolResultBlock("sensitive-tool-id", "x" * (SINGLE_RESULT_CHAR_LIMIT + 1))
            ],
        )
    )
    collector = Collector()

    records = apply_tool_result_budget(
        conversation, tmp_path, create_replacement_state(), observer=collector
    )

    assert len(records) == 1
    event = collector.events[0]
    assert event.event_type == "tool_result_spill"
    assert event.payload["spilled_results"] == 1
    assert event.payload["spilled_chars"] > 0
    assert "sensitive-tool-id" not in repr(event.payload)


@pytest.mark.asyncio
async def test_compaction_observations_cover_completed_and_skipped(tmp_path: Path) -> None:
    collector = Collector()
    conversation = long_conversation()
    conversation.record_usage_anchor(input_tokens=200_000)

    await auto_compact(
        conversation,
        SummaryClient(),
        context_window=200_000,
        session_dir=tmp_path,
        observer=collector,
    )

    assert [event.event_type for event in collector.events] == [
        "compact_started",
        "compact_completed",
    ]
    completed = collector.events[-1].payload
    assert completed["after_tokens"] < completed["before_tokens"]
    assert len(completed["summary_hash"]) == 64
    assert completed["retained_messages"] > 0
    assert "bounded summary" not in repr(completed)

    skipped = Collector()
    short = ConversationManager()
    short.add_user_message("small")
    await auto_compact(
        short,
        SummaryClient(),
        context_window=200_000,
        session_dir=tmp_path,
        observer=skipped,
    )
    assert skipped.events[0].event_type == "compact_skipped"
    assert skipped.events[0].payload["trigger"] == "below_threshold"


@pytest.mark.asyncio
async def test_compaction_failure_is_bounded_and_observer_errors_are_ignored(
    tmp_path: Path,
) -> None:
    conversation = long_conversation()
    conversation.record_usage_anchor(input_tokens=200_000)
    collector = Collector()
    result = await auto_compact(
        conversation,
        FailingSummaryClient(),
        context_window=200_000,
        session_dir=tmp_path,
        observer=collector,
    )
    assert isinstance(result, str)
    assert collector.events[-1].event_type == "compact_failed"
    assert "provider secret" not in repr(collector.events[-1].payload)

    unaffected = ConversationManager()
    unaffected.add_user_message("hello")
    unaffected.record_usage_anchor(100, observer=RaisingObserver())
    assert unaffected.current_tokens() == 100


def test_session_resume_observes_boundary_without_summary_text(tmp_path: Path) -> None:
    collector = Collector()
    manager = SessionManager(str(tmp_path), observer=collector)
    session = manager.create()
    session_id = session.session_id
    session.append(Message(role="user", content="old secret context"))
    session.append_record(
        make_compact_boundary(
            "summary secret must stay hashed",
            [Message(role="user", content="retained")],
        )
    )
    session.append(Message(role="assistant", content="continued"))
    session.close()

    result = manager.resume(session_id)

    assert result is not None
    event = collector.events[-1]
    assert event.event_type == "session_resumed"
    assert event.payload["status"] == "completed"
    assert event.payload["boundary_id"]
    assert event.payload["retained_messages"] == 1
    assert "summary secret" not in repr(event.payload)
    result.session.close()


def test_session_resume_observes_missing_and_degraded_boundaries(tmp_path: Path) -> None:
    collector = Collector()
    manager = SessionManager(str(tmp_path), observer=collector)
    assert manager.resume("missing") is None
    assert collector.events[-1].payload["status"] == "missing"

    session = manager.create()
    session_id = session.session_id
    session.append_record(
        SessionRecord(
            type=RecordType.COMPACT_BOUNDARY,
            content="malformed boundary",
            timestamp=datetime.now(timezone.utc),
        )
    )
    session.close()
    result = manager.resume(session_id)
    assert result is not None
    assert collector.events[-1].payload["status"] == "degraded"
    result.session.close()


def test_agent_context_event_snapshots_stage_and_trace_metadata(tmp_path: Path) -> None:
    downstream = Collector()
    agent = Agent(
        client=object(),
        registry=ToolRegistry(),
        protocol="anthropic",
        work_dir=str(tmp_path),
        context_observer=downstream,
    )
    agent.agent_id = "lead"
    agent.trace_id = "trace-1"
    agent.set_context_stage("pressure", "after-pressure")

    agent.emit(ContextLifecycleObservation("compact_started", {"before_tokens": 10}))
    notifications = agent._drain_context_events()

    assert len(notifications) == 1
    assert notifications[0].event_type == "compact_started"
    assert notifications[0].payload["stage_id"] == "pressure"
    assert notifications[0].payload["checkpoint_id"] == "after-pressure"
    assert notifications[0].payload["trace_id"] == "trace-1"
    assert downstream.events[0].payload["agent_id"] == "lead"
