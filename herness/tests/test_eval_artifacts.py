from __future__ import annotations

from pathlib import Path

from octocoder.evals.artifacts import ArtifactWriter
from octocoder.evals.models import (
    CaseRunResult,
    CaseScore,
    DimensionScore,
    EvalCase,
    ExecutionResult,
    ExecutionStatus,
    RunStatus,
)
from octocoder.evals.redaction import SecretRedactor


def test_artifacts_have_stable_layout_and_no_secrets(tmp_path: Path) -> None:
    secret = "artifact-secret-value"
    case = EvalCase.model_validate(
        {
            "id": "artifact",
            "title": "Artifact",
            "prompt": f"do not leak {secret}",
            "fixture": "fixture",
            "script": {"events": [], "effects": []},
        }
    )
    execution = ExecutionResult(
        run_id="run-1",
        case_id=case.id,
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="2026-01-01T00:00:00Z",
        duration_ms=1,
        stderr=secret,
        final_response=secret,
        raw_events=[{"type": "assistant", "text": secret}],
        workspace_diff={"patch": f"+{secret}\n"},
    )
    verdict = CaseScore(
        passed=True,
        dimensions=[DimensionScore(name=name, checks_passed=1, checks_total=1) for name in (
            "outcome", "trajectory", "efficiency", "safety", "reliability"
        )],
    )
    result = CaseRunResult(status=RunStatus.SUCCESS, execution=execution, verdict=verdict)
    directory = ArtifactWriter(tmp_path, SecretRedactor([secret])).write_case(case, result)
    expected = {
        "case.yaml", "raw-events.jsonl", "events.jsonl", "trajectory.json",
        "workspace.patch", "stderr.txt", "verdict.json", "report.md",
    }
    assert {path.name for path in directory.iterdir()} == expected
    assert all(secret not in path.read_text(encoding="utf-8") for path in directory.iterdir())
    assert "[Raw events](raw-events.jsonl)" in (directory / "report.md").read_text(encoding="utf-8")
