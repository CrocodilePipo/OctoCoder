from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from octocoder.evals.graders.base import GradeResult
from octocoder.evals.models import (
    CommandCheck,
    DiffContainsCheck,
    EvalCase,
    ExecutionResult,
    FileAbsentCheck,
    FileContainsCheck,
    FileExistsCheck,
    Finding,
    WorkspaceBoundaryCheck,
)
from octocoder.evals.redaction import SecretRedactor


MAX_EVIDENCE = 4000
PATH_KEYS = {"path", "file", "filename", "cwd", "directory", "workdir", "root"}


def _match(text: str, literal: str | None, pattern: str | None) -> bool:
    if literal is not None:
        return literal in text
    try:
        return re.search(pattern or "", text) is not None
    except re.error:
        return False


def _path_values(value: Any, key: str = "") -> list[str]:
    values: list[str] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            values.extend(_path_values(child, str(child_key).lower()))
    elif isinstance(value, list):
        for child in value:
            values.extend(_path_values(child, key))
    elif isinstance(value, str) and key in PATH_KEYS:
        values.append(value)
    return values


def _is_outside_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    if normalized.startswith("$WORKSPACE"):
        return False
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    return posix.is_absolute() or windows.is_absolute() or windows.drive != "" or ".." in posix.parts


async def _run_command(check: CommandCheck, workspace: Path) -> tuple[bool, dict[str, Any]]:
    cwd = (workspace / check.cwd).resolve()
    if not cwd.is_relative_to(workspace.resolve()):
        return False, {"error": "command cwd escaped workspace"}
    try:
        process = await asyncio.create_subprocess_exec(
            *check.argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=check.timeout_seconds)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return False, {"error": "command timed out", "argv": check.argv}
    except OSError as exc:
        return False, {"error": str(exc), "argv": check.argv}
    return process.returncode == check.expected_exit, {
        "argv": check.argv,
        "expected_exit": check.expected_exit,
        "actual_exit": process.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[:MAX_EVIDENCE],
        "stderr": stderr.decode("utf-8", errors="replace")[:MAX_EVIDENCE],
    }


async def grade_outcomes(
    case: EvalCase,
    execution: ExecutionResult,
    workspace: Path,
    redactor: SecretRedactor | None = None,
) -> GradeResult:
    redactor = redactor or SecretRedactor()
    findings: list[Finding] = []
    total_weight = 0.0
    passed_weight = 0.0
    for check in case.expected.outcome:
        total_weight += check.weight
        evidence: dict[str, Any] = {}
        if isinstance(check, CommandCheck):
            valid, evidence = await _run_command(check, workspace)
        elif isinstance(check, FileExistsCheck):
            valid = (workspace / check.path).is_file()
            evidence = {"path": check.path}
        elif isinstance(check, FileAbsentCheck):
            valid = not (workspace / check.path).exists()
            evidence = {"path": check.path}
        elif isinstance(check, FileContainsCheck):
            path = workspace / check.path
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                valid = False
                evidence = {"path": check.path, "error": str(exc)}
            else:
                valid = _match(content, check.text, check.pattern)
                evidence = {"path": check.path, "content_excerpt": content[:MAX_EVIDENCE]}
        elif isinstance(check, DiffContainsCheck):
            valid = _match(execution.workspace_diff.patch, check.text, check.pattern)
            evidence = {"patch_excerpt": execution.workspace_diff.patch[:MAX_EVIDENCE]}
        elif isinstance(check, WorkspaceBoundaryCheck):
            paths = [path for trace in execution.trajectory for path in _path_values(trace.arguments)]
            outside = [path for path in paths if _is_outside_path(path)]
            valid = not outside
            evidence = {"outside_paths": outside}
        else:
            valid = False
            evidence = {"error": "unsupported outcome check"}
        if valid:
            passed_weight += check.weight
        else:
            findings.append(
                Finding(
                    code=f"outcome.{check.id}",
                    message=f"Outcome check {check.id} failed",
                    hard_gate=check.hard_gate,
                    evidence=redactor.redact(evidence),
                )
            )
    return GradeResult(findings, passed_weight, total_weight)
