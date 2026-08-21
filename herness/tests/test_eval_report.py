from __future__ import annotations

from octocoder.evals.models import (
    CaseRunResult,
    CaseScore,
    DimensionScore,
    ExecutionResult,
    ExecutionStatus,
    RunStatus,
)
from octocoder.evals.report import build_suite_report, render_suite_markdown


def result(run_id: str, passed: bool, duration: int) -> CaseRunResult:
    execution = ExecutionResult(
        run_id=run_id,
        case_id="case-a",
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="2026-01-01T00:00:00Z",
        duration_ms=duration,
    )
    verdict = CaseScore(
        passed=passed,
        dimensions=[DimensionScore(
            name=name,
            checks_passed=1 if passed else 0,
            checks_total=1,
        ) for name in (
            "outcome", "trajectory", "efficiency", "safety", "reliability"
        )],
    )
    return CaseRunResult(
        status=RunStatus.SUCCESS if passed else RunStatus.EXPECTATION_FAILED,
        execution=execution,
        verdict=verdict,
        artifact_path=run_id,
    )


def test_report_aggregates_repetitions_deterministically() -> None:
    report = build_suite_report("smoke", [result("one", True, 10), result("two", False, 30)])
    assert report.total_runs == 2
    assert report.passed_runs == 1
    assert report.failed_runs == 1
    assert report.duration_summary.median == 20
    assert report.duration_summary.p95 == 30
    markdown = render_suite_markdown(report)
    assert "| case-a | 2 | 1 | 1 | 20 ms |" in markdown
    assert "## Execution Measurements" in markdown
    assert "| duration_ms | 20.0 ms | 20.0 ms | 10.0 ms | 30.0 ms | 30.0 ms |" in markdown
