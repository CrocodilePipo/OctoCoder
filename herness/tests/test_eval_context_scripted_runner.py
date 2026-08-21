from __future__ import annotations

import asyncio
from pathlib import Path

from octocoder.evals.events import process_events
from octocoder.evals.models import EvalCase, ExecutionStatus
from octocoder.evals.runners.base import RunRequest
from octocoder.evals.runners.context_scripted import ScriptedContextRunner
from octocoder.evals.orchestration import EvaluationOrchestrator
from types import SimpleNamespace


def make_case(*, status: str = "completed", duration_ms: int = 10) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "context-scripted",
            "title": "Context scripted",
            "prompt": "run stages",
            "fixture": "fixture",
            "limits": {"max_turns": 10, "max_context_events": 20, "timeout_seconds": 1},
            "context": {
                "stages": [
                    {"id": "setup", "action": "turn", "prompt": "remember"},
                    {"id": "pressure", "action": "pressure", "prompt": "fill", "repeat": 2},
                    {"id": "probe", "action": "checkpoint", "checkpoint": "after"},
                    {"id": "resume", "action": "resume", "checkpoint": "resumed"},
                ]
            },
            "script": {
                "status": status,
                "duration_ms": duration_ms,
                "events": [
                    {
                        "type": "context",
                        "event_type": "compact_started",
                        "stage_id": "pressure",
                        "before_tokens": 190000,
                    },
                    {
                        "type": "context",
                        "event_type": "compact_completed",
                        "stage_id": "pressure",
                        "before_tokens": 190000,
                        "after_tokens": 40000,
                        "boundary_id": "stable-boundary",
                    },
                    {
                        "type": "context",
                        "event_type": "checkpoint",
                        "stage_id": "probe",
                        "checkpoint_id": "after",
                        "checkpoint": {
                            "id": "after",
                            "stage_id": "probe",
                            "facts": {"name": "alpha"},
                        },
                    },
                    {"type": "result", "result": "done", "num_turns": 3},
                ],
                "effects": [
                    {"type": "write", "path": "result.txt", "content": "done\n"}
                ],
            },
        }
    )


def test_scripted_context_runner_replays_stage_order_and_resume(tmp_path: Path) -> None:
    case = make_case()
    output = asyncio.run(
        ScriptedContextRunner().run(RunRequest("run", case, tmp_path))
    )
    assert output.status == ExecutionStatus.COMPLETED
    assert output.turns == 3
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "done\n"
    stage_ids = [event.get("stage_id") for event in output.raw_events if event.get("stage_id")]
    assert stage_ids[:4] == ["pressure", "pressure", "pressure", "pressure"]
    resumed = [
        event
        for event in output.raw_events
        if event.get("event_type") == "session_resumed"
    ][0]
    assert resumed["boundary_id"] == "stable-boundary"
    processed = process_events(
        output.raw_events,
        workspace=tmp_path,
        run_id="run",
        context=case.context,
    )
    assert processed.context_checkpoints[0].id == "after"


def test_scripted_context_runner_is_deterministic(tmp_path: Path) -> None:
    first_path = tmp_path / "one"
    second_path = tmp_path / "two"
    first_path.mkdir()
    second_path.mkdir()
    case = make_case()
    first = asyncio.run(
        ScriptedContextRunner().run(RunRequest("one", case, first_path))
    )
    second = asyncio.run(
        ScriptedContextRunner().run(RunRequest("two", case, second_path))
    )
    assert first.raw_events == second.raw_events
    assert first.final_response == second.final_response


def test_scripted_context_runner_enforces_timeout(tmp_path: Path) -> None:
    output = asyncio.run(
        ScriptedContextRunner().run(
            RunRequest("run", make_case(duration_ms=1_500), tmp_path)
        )
    )
    assert output.status == ExecutionStatus.TIMEOUT
    assert output.errors == ["Evaluation timed out"]


def test_orchestrator_selects_context_runner_only_for_context_cases(tmp_path: Path) -> None:
    regular_scripted = object()
    regular_real = object()
    context_scripted = object()
    context_real = object()
    orchestrator = EvaluationOrchestrator(
        SimpleNamespace(),
        tmp_path,
        scripted_runner=regular_scripted,
        real_runner=regular_real,
        context_scripted_runner=context_scripted,
        context_real_runner=context_real,
    )
    assert orchestrator._select_runner(make_case()) is context_scripted

    context_real_case = make_case().model_copy(
        update={"execution": make_case().execution.model_copy(update={"mode": "real"})}
    )
    assert orchestrator._select_runner(context_real_case) is context_real

    regular = EvalCase.model_validate(
        {
            "id": "regular",
            "title": "Regular",
            "prompt": "run",
            "fixture": "fixture",
            "script": {"events": []},
        }
    )
    assert orchestrator._select_runner(regular) is regular_scripted
