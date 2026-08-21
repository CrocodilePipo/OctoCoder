from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from octocoder.evals.context_worker import build_probe_prompt, run_request
from octocoder.evals.models import EvalCase, ExecutionStatus
from octocoder.evals.runners.base import RunRequest
from octocoder.evals.runners.context_real import RealContextRunner


def real_case(timeout: float = 5) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "context-real",
            "title": "Context real",
            "prompt": "run",
            "fixture": "fixture",
            "execution": {"mode": "real", "env_allowlist": ["PYTHONPATH"]},
            "limits": {"timeout_seconds": timeout},
            "context": {
                "stages": [
                    {"id": "setup", "action": "turn", "prompt": "remember alpha"},
                    {"id": "probe", "action": "checkpoint", "checkpoint": "after"},
                    {"id": "resume", "action": "resume", "checkpoint": "resumed"},
                ],
                "facts": [
                    {"id": "name", "value": "alpha", "required_at": ["after", "resumed"]}
                ],
            },
        }
    )


def write_worker(root: Path, body: str) -> None:
    package = root / "fake_context_worker"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(body, encoding="utf-8")


def test_real_context_runner_captures_multi_stage_evidence(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_worker(
        modules,
        "import json, sys\n"
        "request=json.loads(sys.stdin.read())\n"
        "print(json.dumps({'type':'context','event_type':'compact_started','stage_id':'setup','sequence':0}), flush=True)\n"
        "print(json.dumps({'type':'context','event_type':'compact_completed','stage_id':'setup','sequence':1,'before_tokens':100,'after_tokens':20,'boundary_id':'b'}), flush=True)\n"
        "print(json.dumps({'type':'context','event_type':'checkpoint','stage_id':'probe','checkpoint_id':'after','sequence':2,'checkpoint':{'id':'after','stage_id':'probe','facts':{'name':'alpha'}}}), flush=True)\n"
        "print(json.dumps({'type':'result','result':'done','provider':'fake','model':'fake-model','num_turns':3,'usage':{'input_tokens':10,'output_tokens':2}}), flush=True)\n",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealContextRunner("fake_context_worker").run(
            RunRequest(
                "run",
                real_case(),
                workspace,
                {"PYTHONPATH": str(modules)},
            )
        )
    )
    assert output.status == ExecutionStatus.COMPLETED
    assert output.final_response == "done"
    assert output.usage.input_tokens == 10
    assert any("checkpoint" in str(event) for event in output.raw_events)


def test_real_context_runner_aggregates_turns_across_stage_results(
    tmp_path: Path,
) -> None:
    worker = tmp_path / "fake_context_worker.py"
    worker.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'result','result':'one','num_turns':2,'usage':{'input_tokens':10,'output_tokens':2}}), flush=True)\n"
        "print(json.dumps({'type':'result','result':'two','provider':'fake','model':'model','num_turns':3,'usage':{'input_tokens':20,'output_tokens':4}}), flush=True)\n",
        encoding="utf-8",
    )
    request = RunRequest("run", real_case(), tmp_path)
    output = asyncio.run(RealContextRunner("fake_context_worker").run(request))
    assert output.turns == 5
    assert output.final_response == "two"
    assert output.usage.input_tokens == 20


def test_real_context_runner_keeps_partial_events_on_timeout(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_worker(
        modules,
        "import sys, time\n"
        "sys.stdin.read()\n"
        "print('{\"type\":\"context\",\"event_type\":\"compact_started\",\"stage_id\":\"setup\"}', flush=True)\n"
        "time.sleep(10)\n",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealContextRunner("fake_context_worker").run(
            RunRequest(
                "run",
                real_case(timeout=0.1),
                workspace,
                {"PYTHONPATH": str(modules)},
            )
        )
    )
    assert output.status == ExecutionStatus.TIMEOUT
    assert any("compact_started" in str(event) for event in output.raw_events)


def test_real_context_runner_classifies_worker_failure(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_worker(modules, "import sys; sys.stdin.read(); sys.exit(2)\n")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealContextRunner("fake_context_worker").run(
            RunRequest(
                "run",
                real_case(),
                workspace,
                {"PYTHONPATH": str(modules)},
            )
        )
    )
    assert output.status == ExecutionStatus.FRAMEWORK_FAILED
    assert "code 2" in output.errors[0]


class FakeSession:
    def __init__(self, sink) -> None:
        self.sink = sink
        self.turns: list[tuple[str, str, str | None]] = []
        self.resumed = False

    async def run_turn(self, prompt: str, stage_id: str, checkpoint_id=None):
        self.turns.append((prompt, stage_id, checkpoint_id))
        self.sink({"type": "assistant", "text": "ok", "stage_id": stage_id})
        return SimpleNamespace(errors=[])

    async def persist_and_resume(self, stage_id: str):
        self.resumed = True
        self.sink(
            {
                "type": "context",
                "event_type": "session_resumed",
                "stage_id": stage_id,
            }
        )

    async def close(self):
        return None


def test_context_worker_uses_one_session_and_real_resume_boundary() -> None:
    created: list[FakeSession] = []
    events: list[dict] = []

    async def factory(config, mode, hooks, event_sink, work_dir):
        session = FakeSession(event_sink)
        created.append(session)
        return session

    code = asyncio.run(
        run_request(
            {"case": real_case().model_dump(mode="json"), "work_dir": "."},
            config=SimpleNamespace(raw_hooks=[]),
            hook_engine=SimpleNamespace(),
            session_factory=factory,
            sink=events.append,
        )
    )
    assert code == 0
    assert len(created) == 1
    assert created[0].resumed is True
    assert [turn[1] for turn in created[0].turns] == ["setup", "probe", "resume"]
    assert "OCTOCODER_CONTEXT_CHECKPOINT_START" in created[0].turns[1][0]
    assert any(event.get("event_type") == "session_resumed" for event in events)


def test_probe_prompt_declares_ids_and_bounded_marker() -> None:
    prompt = build_probe_prompt(real_case(), "after")
    assert "name" in prompt
    assert "after" in prompt
    assert "OCTOCODER_CONTEXT_CHECKPOINT_START" in prompt
    assert len(prompt) < 2_000
