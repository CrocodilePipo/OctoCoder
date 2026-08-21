from __future__ import annotations

import io
import json

from octocoder.__main__ import StructuredEventEmitter


def test_structured_event_emitter_adds_ordered_metadata() -> None:
    output = io.StringIO()
    times = iter([10.0, 10.1, 10.2])
    emitter = StructuredEventEmitter(output, run_id="run-test", clock=lambda: next(times))
    emitter.emit({"type": "assistant", "text": "hello"})
    emitter.complete_turn(2)
    emitter.emit({"type": "result", "result": "hello"})
    events = [json.loads(line) for line in output.getvalue().splitlines()]

    assert [event["sequence"] for event in events] == [0, 1]
    assert {event["run_id"] for event in events} == {"run-test"}
    assert events[0]["turn"] == 0
    assert events[1]["turn"] == 2
    assert events[0]["text"] == "hello"
    assert events[1]["timestamp_ms"] == 199


def test_structured_event_emitter_preserves_context_payload() -> None:
    output = io.StringIO()
    times = iter([4.0, 4.1])
    emitter = StructuredEventEmitter(output, run_id="context-run", clock=lambda: next(times))
    emitter.emit(
        {
            "type": "context",
            "event_type": "compact_completed",
            "stage_id": "pressure",
            "before_tokens": 100,
            "after_tokens": 40,
        }
    )
    event = json.loads(output.getvalue())
    assert event["type"] == "context"
    assert event["event_type"] == "compact_completed"
    assert event["stage_id"] == "pressure"
    assert event["sequence"] == 0
    assert event["run_id"] == "context-run"
