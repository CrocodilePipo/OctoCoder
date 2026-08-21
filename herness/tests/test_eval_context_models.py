from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from octocoder.evals.loader import EvaluationLoadError, load_case
from octocoder.evals.models import (
    ContextEvent,
    ContextEventType,
    ContextMetrics,
    EvalCase,
    ExecutionResult,
)


def context_case() -> dict:
    return {
        "id": "context-retention",
        "title": "Context retention",
        "prompt": "Run the context scenario",
        "fixture": "context-project",
        "execution": {"mode": "scripted"},
        "limits": {"max_turns": 5, "max_stages": 10},
        "script": {"events": [], "effects": []},
        "context": {
            "stages": [
                {"id": "setup", "action": "turn", "prompt": "Remember alpha"},
                {"id": "probe", "action": "checkpoint", "checkpoint": "after"},
                {"id": "resume", "action": "resume", "checkpoint": "resumed"},
            ],
            "facts": [
                {
                    "id": "name",
                    "value": "alpha",
                    "required_at": ["after", "resumed"],
                }
            ],
            "instructions": [
                {
                    "id": "format",
                    "text": "Use JSON",
                    "priority": "user",
                    "active_at": ["after", "resumed"],
                }
            ],
            "states": [{"checkpoint": "after", "required_files": ["README.md"]}],
            "token": {"max_absolute_error_tokens": 1000},
            "compression": {"min_compactions": 1, "max_compactions": 2},
            "resumes": [
                {
                    "before_checkpoint": "after",
                    "after_checkpoint": "resumed",
                    "equivalent_fact_ids": ["name"],
                    "equivalent_instruction_ids": ["format"],
                    "equivalent_state_fields": ["next_action"],
                }
            ],
        },
    }


def test_context_schema_is_optional_and_complete() -> None:
    case = EvalCase.model_validate(context_case())
    assert case.context is not None
    assert case.context.stages[1].checkpoint == "after"
    assert case.context.facts[0].operator.value == "equals"
    assert case.context.compression is not None


def test_execution_result_accepts_context_evidence() -> None:
    result = ExecutionResult.model_validate(
        {
            "run_id": "run",
            "case_id": "case",
            "mode": "scripted",
            "status": "completed",
            "started_at": "2026-08-20T00:00:00Z",
            "duration_ms": 1,
            "context_events": [
                ContextEvent(
                    sequence=0,
                    stage_id="setup",
                    event_type=ContextEventType.USAGE_ANCHOR,
                    provider_tokens=100,
                )
            ],
            "context_metrics": ContextMetrics(retention_rate=1.0),
        }
    )
    assert result.context_metrics is not None
    assert result.context_metrics.retention_rate == 1.0


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("context", "stages", 0, "prompt"), "", "requires a prompt"),
        (("context", "stages", 1, "checkpoint"), None, "requires a checkpoint"),
        (("context", "facts", 0, "value"), None, "requires a value"),
        (("context", "instructions", 0, "pattern"), "also", "exactly one"),
        (("context", "states", 0, "required_files", 0), "../secret", "traversal"),
    ],
)
def test_context_schema_rejects_malformed_fields(path, value, match: str) -> None:
    data = context_case()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError, match=match):
        EvalCase.model_validate(data)


def test_context_schema_rejects_duplicate_stage_and_checkpoint_ids() -> None:
    for key in ("id", "checkpoint"):
        data = context_case()
        data["context"]["stages"][2][key] = data["context"]["stages"][1][key]
        with pytest.raises(ValidationError, match="unique"):
            EvalCase.model_validate(data)


def write_case(tmp_path: Path, data: dict) -> Path:
    import yaml

    path = tmp_path / "case.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda data: data["context"]["facts"][0]["required_at"].append("missing"), "unknown checkpoints"),
        (lambda data: data["context"]["resumes"][0]["equivalent_fact_ids"].append("missing"), "unknown facts"),
        (lambda data: data["context"]["resumes"][0]["equivalent_instruction_ids"].append("missing"), "unknown instructions"),
        (lambda data: data["limits"].update({"max_stages": 2}), "stages, limit"),
        (lambda data: data["limits"].update({"max_turns": 0}), "greater than 0"),
    ],
)
def test_loader_rejects_invalid_context_references(tmp_path: Path, mutate, match: str) -> None:
    data = context_case()
    mutate(data)
    with pytest.raises(EvaluationLoadError, match=match):
        load_case(write_case(tmp_path, data))


def test_loader_rejects_context_without_observable_checkpoint(tmp_path: Path) -> None:
    data = context_case()
    data["context"]["stages"] = [
        {"id": "setup", "action": "turn", "prompt": "Remember alpha"}
    ]
    data["context"]["facts"] = []
    data["context"]["instructions"] = []
    data["context"]["states"] = []
    data["context"]["resumes"] = []
    with pytest.raises(EvaluationLoadError, match="observable checkpoint"):
        load_case(write_case(tmp_path, data))
