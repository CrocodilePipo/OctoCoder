from __future__ import annotations

from pathlib import Path

from octocoder.evals.events import CHECKPOINT_END, CHECKPOINT_START, process_events
from octocoder.evals.models import ContextEventType, ContextExpectation
from octocoder.evals.redaction import SecretRedactor


def expectation() -> ContextExpectation:
    return ContextExpectation.model_validate(
        {
            "stages": [
                {"id": "pressure", "action": "pressure", "prompt": "fill"},
                {"id": "probe", "action": "checkpoint", "checkpoint": "after"},
                {"id": "resume", "action": "resume", "checkpoint": "resumed"},
            ]
        }
    )


def test_context_lifecycle_normalizes_and_validates_transitions(tmp_path: Path) -> None:
    processed = process_events(
        [
            {
                "type": "context",
                "event_type": "compact_started",
                "stage_id": "pressure",
                "sequence": 1,
                "before_tokens": 190_000,
                "trigger": "soft_threshold",
                "context_window": 200_000,
                "threshold_tokens": 187_000,
            },
            {
                "type": "context",
                "event_type": "compact_completed",
                "stage_id": "pressure",
                "sequence": 2,
                "before_tokens": 190_000,
                "after_tokens": 40_000,
                "retained_messages": 6,
                "retained_tokens": 9_000,
                "summary_hash": "a" * 64,
                "boundary_id": "boundary-stable",
            },
            {
                "type": "context",
                "event_type": "session_resumed",
                "stage_id": "resume",
                "checkpoint_id": "resumed",
                "sequence": 3,
                "boundary_id": "boundary-stable",
            },
        ],
        workspace=tmp_path,
        run_id="run",
        context=expectation(),
    )
    assert [event.event_type for event in processed.context_events] == [
        ContextEventType.COMPACT_STARTED,
        ContextEventType.COMPACT_COMPLETED,
        ContextEventType.SESSION_RESUMED,
    ]
    assert processed.context_events[1].after_tokens == 40_000
    assert not processed.findings


def test_scripted_and_agent_probe_checkpoints_are_extracted(tmp_path: Path) -> None:
    marker = (
        f"{CHECKPOINT_START}\n"
        '{"id":"resumed","stage_id":"resume","facts":{"name":"alpha"},'
        '"active_instructions":["json"],"task_state":{"next_action":"test"}}'
        f"\n{CHECKPOINT_END}"
    )
    processed = process_events(
        [
            {
                "type": "context",
                "event_type": "checkpoint",
                "stage_id": "probe",
                "checkpoint_id": "after",
                "source": "scripted",
                "checkpoint": {
                    "id": "after",
                    "stage_id": "probe",
                    "facts": {"name": "alpha"},
                    "active_instructions": ["json"],
                    "task_state": {"next_action": "test"},
                },
            },
            {"type": "assistant", "stage_id": "resume", "text": marker[:45]},
            {"type": "assistant", "stage_id": "resume", "text": marker[45:]},
        ],
        workspace=tmp_path,
        run_id="run",
        context=expectation(),
    )
    assert [checkpoint.id for checkpoint in processed.context_checkpoints] == [
        "after",
        "resumed",
    ]
    assert processed.context_checkpoints[1].facts["name"] == "alpha"
    assert processed.context_checkpoints[1].source == "agent_probe"


def test_agent_probe_accepts_fenced_json_and_derives_tool_pair_state(
    tmp_path: Path,
) -> None:
    marker = (
        f"{CHECKPOINT_START}\n```json\n"
        '{"id":"after","stage_id":null,"facts":{"name":"alpha"},'
        '"active_instructions":{"json":"Use JSON"},'
        '"task_state":{"next_action":"test"},"tool_pair_complete":null}'
        f"\n```\n{CHECKPOINT_END}"
    )
    processed = process_events(
        [{"type": "assistant", "stage_id": "probe", "text": marker}],
        workspace=tmp_path,
        run_id="run",
        context=expectation(),
    )
    assert not processed.findings
    checkpoint = processed.context_checkpoints[0]
    assert checkpoint.stage_id == "probe"
    assert checkpoint.active_instructions == ["json", "Use JSON"]
    assert checkpoint.tool_pair_complete is True


def test_invalid_context_transitions_remain_diagnostic_findings(tmp_path: Path) -> None:
    processed = process_events(
        [
            {
                "type": "context",
                "event_type": "compact_completed",
                "stage_id": "pressure",
                "before_tokens": 10,
                "after_tokens": 20,
                "boundary_id": "unknown",
            },
            {
                "type": "context",
                "event_type": "session_resumed",
                "stage_id": "resume",
                "boundary_id": "different",
            },
            {
                "type": "context",
                "event_type": "compact_started",
                "stage_id": "missing-stage",
            },
        ],
        workspace=tmp_path,
        run_id="run",
        context=expectation(),
    )
    codes = {finding.code for finding in processed.findings}
    assert {
        "invalid_context_transition",
        "compaction_increased_context",
        "unknown_resume_boundary",
        "unfinished_compaction",
        "unknown_context_stage",
    } <= codes


def test_context_checkpoint_is_bounded_and_redacted(tmp_path: Path) -> None:
    secret = "secret-value-123"
    processed = process_events(
        [
            {
                "type": "context",
                "event_type": "checkpoint",
                "stage_id": "probe",
                "checkpoint_id": "after",
                "checkpoint": {
                    "id": "after",
                    "stage_id": "probe",
                    "facts": {"output": secret + "x" * 5_000},
                },
            }
        ],
        workspace=tmp_path,
        run_id="run",
        context=expectation(),
        redactor=SecretRedactor([secret]),
    )
    rendered = repr(processed.context_checkpoints[0])
    assert secret not in rendered
    assert "[REDACTED]" in rendered
    assert len(processed.context_checkpoints[0].facts["output"]) < 2_100


def test_cross_platform_context_paths_normalize_equivalently(tmp_path: Path) -> None:
    windows = str(tmp_path / "src" / "app.py")
    unix = windows.replace("\\", "/")
    first = process_events(
        [{"type": "context", "event_type": "usage_anchor", "path": windows}],
        workspace=tmp_path,
        run_id="one",
    )
    second = process_events(
        [{"type": "context", "event_type": "usage_anchor", "path": unix}],
        workspace=tmp_path,
        run_id="two",
    )
    assert first.context_events[0].payload == second.context_events[0].payload
