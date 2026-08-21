from __future__ import annotations

import asyncio
from pathlib import Path

from octocoder.evals.models import EvalCase, ExecutionStatus
from octocoder.evals.runners.base import RunRequest
from octocoder.evals.runners.scripted import ScriptedRunner


def make_case() -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "scripted-edit",
            "title": "Scripted edit",
            "prompt": "Edit the file",
            "fixture": "fixture",
            "script": {
                "events": [{"type": "result", "result": "done", "num_turns": 1}],
                "effects": [{"type": "write", "path": "src/value.txt", "content": "done\n"}],
            },
        }
    )


def test_scripted_runner_replays_events_and_effects(tmp_path: Path) -> None:
    output = asyncio.run(
        ScriptedRunner().run(RunRequest("run-1", make_case(), tmp_path))
    )
    assert output.status == ExecutionStatus.COMPLETED
    assert output.final_response == "done"
    assert (tmp_path / "src" / "value.txt").read_text(encoding="utf-8") == "done\n"


def test_scripted_runner_is_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    first = asyncio.run(ScriptedRunner().run(RunRequest("one", make_case(), first_dir)))
    second = asyncio.run(ScriptedRunner().run(RunRequest("two", make_case(), second_dir)))
    assert first == second
