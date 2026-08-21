from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from octocoder.evals.graders.outcome import grade_outcomes
from octocoder.evals.models import EvalCase, ExecutionResult, ExecutionStatus, ToolTrace, WorkspaceSnapshot


def make_case(checks) -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "outcome",
            "title": "Outcome",
            "prompt": "work",
            "fixture": "fixture",
            "script": {"events": [], "effects": []},
            "expected": {"outcome": checks},
        }
    )


def execution(trajectory=None, patch="") -> ExecutionResult:
    return ExecutionResult(
        run_id="run",
        case_id="outcome",
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="2026-01-01T00:00:00Z",
        duration_ms=1,
        trajectory=trajectory or [],
        workspace_diff=WorkspaceSnapshot(patch=patch),
    )


def test_file_diff_and_command_checks_pass(tmp_path: Path) -> None:
    (tmp_path / "result.txt").write_text("hello world", encoding="utf-8")
    case = make_case(
        [
            {"id": "exists", "type": "file_exists", "path": "result.txt"},
            {"id": "content", "type": "file_contains", "path": "result.txt", "text": "world"},
            {"id": "diff", "type": "diff_contains", "text": "+hello"},
            {"id": "command", "type": "command", "argv": [sys.executable, "-c", "print('ok')"]},
        ]
    )
    result = asyncio.run(grade_outcomes(case, execution(patch="+hello"), tmp_path))
    assert result.passed_weight == result.total_weight == 4


def test_workspace_boundary_detects_absolute_external_path(tmp_path: Path) -> None:
    case = make_case([{"id": "boundary", "type": "workspace_boundary"}])
    trajectory = [ToolTrace(sequence=0, tool="write", arguments={"path": "C:/outside/file.txt"})]
    result = asyncio.run(grade_outcomes(case, execution(trajectory), tmp_path))
    assert result.passed_weight == 0
    assert result.total_weight == 1
    assert result.findings[0].hard_gate is True


def test_absent_and_regex_content_checks_pass(tmp_path: Path) -> None:
    (tmp_path / "result.txt").write_text("version=42", encoding="utf-8")
    case = make_case(
        [
            {"id": "absent", "type": "file_absent", "path": "secret.txt"},
            {"id": "regex", "type": "file_contains", "path": "result.txt", "pattern": r"version=\d+"},
        ]
    )
    result = asyncio.run(grade_outcomes(case, execution(), tmp_path))
    assert result.passed_weight == result.total_weight == 2
