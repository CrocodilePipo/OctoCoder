from __future__ import annotations

from octocoder.evals.compare import compare_reports
from octocoder.evals.models import (
    CaseRunResult,
    CaseScore,
    DimensionScore,
    ExecutionResult,
    ExecutionStatus,
    RunStatus,
    SuiteReport,
)
from octocoder.evals.report import build_suite_report


def run(passed: bool) -> CaseRunResult:
    execution = ExecutionResult(
        run_id=f"run-{passed}", case_id="case", mode="scripted",
        status=ExecutionStatus.COMPLETED, started_at="now", duration_ms=1,
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
        execution=execution, verdict=verdict,
    )


def test_compare_classifies_regression_improvement_and_unchanged() -> None:
    regression = compare_reports(build_suite_report("s", [run(True)]), build_suite_report("s", [run(False)]))
    assert regression.regression is True
    assert "regression" in {change.classification for change in regression.changes}
    improvement = compare_reports(build_suite_report("s", [run(False)]), build_suite_report("s", [run(True)]))
    assert "improvement" in {change.classification for change in improvement.changes}
    unchanged = compare_reports(build_suite_report("s", [run(True)]), build_suite_report("s", [run(True)]))
    assert {change.classification for change in unchanged.changes} == {"unchanged"}
