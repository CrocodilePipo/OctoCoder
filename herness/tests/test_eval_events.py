from __future__ import annotations

from pathlib import Path

from octocoder.evals.events import process_events


def test_events_normalize_paths_ids_and_pair_tools(tmp_path: Path) -> None:
    tool_id = "call_abcdef123456"
    events = [
        {
            "type": "tool_use",
            "tool_name": "read_file",
            "tool_id": tool_id,
            "args": {"path": str(tmp_path / "README.md")},
        },
        {
            "type": "tool_result",
            "tool_name": "read_file",
            "tool_id": tool_id,
            "output": "ok",
            "elapsed": 0.01,
        },
    ]
    processed = process_events(events, workspace=tmp_path, run_id="run-test")
    assert processed.malformed_count == 0
    assert processed.unpaired_count == 0
    assert processed.trajectory[0].arguments["path"] == "$WORKSPACE/README.md"
    assert processed.trajectory[0].result_status == "success"
    assert processed.trajectory[0].duration_ms == 10


def test_events_preserve_malformed_and_unpaired_findings(tmp_path: Path) -> None:
    processed = process_events(
        ["not-json", '{"type":"tool_result","tool_id":"call_abcdef"}'],
        workspace=tmp_path,
        run_id="run-test",
    )
    assert processed.malformed_count == 1
    assert processed.unpaired_count == 1
    assert {finding.code for finding in processed.findings} == {"malformed_event", "missing_tool_use"}


def test_generated_ids_normalize_stably(tmp_path: Path) -> None:
    first = process_events(
        [{"type": "tool_use", "tool_id": "call_abcdef", "tool_name": "read", "args": {}}],
        workspace=tmp_path,
        run_id="run-one",
    )
    second = process_events(
        [{"type": "tool_use", "tool_id": "call_uvwxyz", "tool_name": "read", "args": {}}],
        workspace=tmp_path,
        run_id="run-two",
    )
    assert first.events[0].payload == second.events[0].payload


def test_normalized_events_remove_volatile_timestamps(tmp_path: Path) -> None:
    processed = process_events(
        [{"type": "assistant", "text": "ok", "timestamp_ms": 987654}],
        workspace=tmp_path,
        run_id="run-test",
    )
    assert processed.raw_events[0]["timestamp_ms"] == 987654
    assert processed.events[0].timestamp_ms == 0


def test_long_results_keep_bounded_summary_and_full_hash(tmp_path: Path) -> None:
    processed = process_events(
        [
            {"type": "tool_use", "tool_name": "read", "tool_id": "call_longvalue", "args": {}},
            {"type": "tool_result", "tool_name": "read", "tool_id": "call_longvalue", "output": "x" * 5000},
        ],
        workspace=tmp_path,
        run_id="run-test",
    )
    trace = processed.trajectory[0]
    assert len(trace.result_summary) < 2100
    assert len(trace.result_hash) == 64
