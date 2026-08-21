from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

from octocoder.evals.models import EvalCase, ExecutionStatus
from octocoder.evals.loader import load_catalog
from octocoder.evals.orchestration import EvaluationOrchestrator
from octocoder.evals.runners.base import RunRequest
from octocoder.evals.runners.real import RealRunner


def case(timeout: float = 5) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "real-run",
            "title": "Real run",
            "prompt": "hello",
            "fixture": "fixture",
            "execution": {"mode": "real"},
            "limits": {"timeout_seconds": timeout},
        }
    )


def write_module(root: Path, body: str) -> None:
    package = root / "fake_agent"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "__main__.py").write_text(body, encoding="utf-8")


def test_real_runner_captures_result(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_module(
        modules,
        'print(\'{"type":"result","result":"done","model":"fake","usage":{"input_tokens":1,"output_tokens":2}}\')',
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealRunner("fake_agent").run(
            RunRequest("run-1", case(), workspace, {"PYTHONPATH": str(modules)})
        )
    )
    assert output.status == ExecutionStatus.COMPLETED
    assert output.final_response == "done"
    assert output.usage.output_tokens == 2


def test_real_runner_captures_failure(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_module(modules, "import sys; print('bad output'); sys.exit(4)")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealRunner("fake_agent").run(
            RunRequest("run-1", case(), workspace, {"PYTHONPATH": str(modules)})
        )
    )
    assert output.status == ExecutionStatus.AGENT_FAILED
    assert "code 4" in output.errors[0]


def test_real_runner_preserves_caller_config_discovery(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_module(
        modules,
        "import json, os; print(json.dumps({'type':'result','result':os.environ['OCTOCODER_CONFIG_CWD']}))",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealRunner("fake_agent").run(
            RunRequest("run-1", case(), workspace, {"PYTHONPATH": str(modules)})
        )
    )
    assert Path(output.final_response).resolve() == Path.cwd().resolve()


def test_real_runner_times_out_and_keeps_partial_output(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_module(
        modules,
        "import time; print('{\"type\":\"assistant\",\"text\":\"partial\"}', flush=True); time.sleep(10)",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealRunner("fake_agent").run(
            RunRequest("run-1", case(timeout=0.1), workspace, {"PYTHONPATH": str(modules)})
        )
    )
    assert output.status == ExecutionStatus.TIMEOUT
    assert any("partial" in str(event) for event in output.raw_events)


def test_real_runner_timeout_terminates_child_process(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_module(
        modules,
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "open('child.pid', 'w', encoding='utf-8').write(str(child.pid))\n"
        "print('{\"type\":\"assistant\",\"text\":\"spawned\"}', flush=True)\n"
        "time.sleep(30)\n",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    output = asyncio.run(
        RealRunner("fake_agent").run(
            RunRequest("run-1", case(timeout=0.5), workspace, {"PYTHONPATH": str(modules)})
        )
    )
    child_pid = int((workspace / "child.pid").read_text(encoding="utf-8"))
    time.sleep(0.1)
    if os.name == "nt":
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        ).stdout
        alive = f'"{child_pid}"' in listing
    else:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            alive = False
        else:
            alive = True
    assert output.status == ExecutionStatus.TIMEOUT
    assert alive is False


def test_real_runner_uses_full_orchestration_pipeline(tmp_path: Path, monkeypatch) -> None:
    modules = tmp_path / "modules"
    modules.mkdir()
    write_module(
        modules,
        "import json, pathlib\n"
        "pathlib.Path('result.txt').write_text('complete\\n', encoding='utf-8')\n"
        "print(json.dumps({'type':'tool_use','tool_name':'WriteFile','tool_id':'call_localagent','args':{'path':'result.txt'}}))\n"
        "print(json.dumps({'type':'tool_result','tool_name':'WriteFile','tool_id':'call_localagent','output':'ok','is_error':False}))\n"
        "print(json.dumps({'type':'result','result':'done','provider':'local','model':'fake','num_turns':1}))\n",
    )
    monkeypatch.setenv("PYTHONPATH", str(modules))
    root = tmp_path / "evals"
    (root / "cases").mkdir(parents=True)
    (root / "suites").mkdir()
    (root / "fixtures" / "tiny").mkdir(parents=True)
    (root / "cases" / "real.yaml").write_text(
        """schema_version: 1
id: local-real
title: Local real process
prompt: write result
fixture: tiny
execution:
  mode: real
  env_allowlist: [PYTHONPATH]
expected:
  trajectory:
    required: [{tool: WriteFile}]
  outcome:
    - {id: result, type: file_contains, path: result.txt, text: complete}
""",
        encoding="utf-8",
    )
    catalog = load_catalog(root)
    evaluation = asyncio.run(
        EvaluationOrchestrator(
            catalog,
            tmp_path / "runs",
            real_runner=RealRunner("fake_agent"),
        ).run([catalog.cases["local-real"]], suite_id="local-real")
    )
    assert evaluation.report.passed is True
    assert evaluation.report.results[0].execution.model == "fake"
    assert evaluation.report.results[0].execution.workspace_diff.changed_files == ["result.txt"]
    assert evaluation.report_json.exists()
    assert not list(evaluation.output_directory.glob(".workspaces/*"))
