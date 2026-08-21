from __future__ import annotations

from octocoder.evals.compare import compare_reports, render_comparison_markdown
from octocoder.evals.models import (
    CaseRunResult,
    CaseScore,
    ComparisonThresholds,
    ContextCheckpoint,
    ContextMetrics,
    DimensionScore,
    ExecutionResult,
    ExecutionStatus,
    Finding,
    RunStatus,
)
from octocoder.evals.report import build_suite_report


def run(
    *,
    passed: bool = True,
    retention: float = 1,
    resume: float = 1,
    token_error_tokens: float = 500,
    reclaimed_tokens: int = 100_000,
    retained_tokens: int = 10_000,
    compactions: int = 1,
    checkpoint: bool = True,
    hard_gate: bool = False,
) -> CaseRunResult:
    execution = ExecutionResult(
        run_id=f"run-{passed}-{retention}-{token_error_tokens}",
        case_id="context-case",
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="now",
        duration_ms=1,
        context_checkpoints=(
            [ContextCheckpoint(id="after", stage_id="probe", source="scripted")]
            if checkpoint
            else []
        ),
        context_metrics=ContextMetrics(
            retention_rate=retention,
            instruction_adherence_rate=retention,
            resume_consistency_rate=resume,
            token_error_tokens_mean=token_error_tokens,
            reclaimed_tokens_total=reclaimed_tokens,
            retained_tokens_max=retained_tokens,
            compaction_count=compactions,
        ),
    )
    findings = (
        [
            Finding(
                code="context.fact_retention",
                message="lost",
                hard_gate=True,
                evidence={"checkpoint_id": "after"},
            )
        ]
        if hard_gate
        else []
    )
    verdict = CaseScore(
        passed=passed,
        dimensions=[
            *[
                DimensionScore(name=name, checks_passed=1, checks_total=1)
                for name in ("outcome", "trajectory", "efficiency", "safety", "reliability")
            ],
            DimensionScore(
                name="context",
                checks_passed=0 if findings else 1,
                checks_total=1,
                findings=findings,
            ),
        ],
        findings=findings,
    )
    return CaseRunResult(
        status=RunStatus.SUCCESS if passed else RunStatus.EXPECTATION_FAILED,
        execution=execution,
        verdict=verdict,
    )


def thresholds() -> ComparisonThresholds:
    return ComparisonThresholds(
        context_retention_drop=0.05,
        context_adherence_drop=0.05,
        context_resume_drop=0.05,
        context_token_error_increase_tokens=1000,
        context_reclaimed_tokens_drop=20_000,
        context_retained_tokens_increase=10_000,
        context_compaction_count_increase=1,
    )


def report(result: CaseRunResult):
    return build_suite_report("context", [result], thresholds())


def test_context_regressions_apply_declared_thresholds() -> None:
    comparison = compare_reports(
        report(run()),
        report(
            run(
                passed=False,
                retention=0.8,
                resume=0.8,
                token_error_tokens=3000,
                reclaimed_tokens=50_000,
                retained_tokens=30_000,
                compactions=3,
                hard_gate=True,
            )
        ),
    )
    regressions = {
        change.metric
        for change in comparison.changes
        if change.classification == "regression"
    }
    assert {
        "failed_runs",
        "context.retention_rate",
        "context.instruction_adherence_rate",
        "context.resume_consistency_rate",
        "context.token_error_tokens_mean",
        "context.reclaimed_tokens_total",
        "context.retained_tokens_max",
        "context.compaction_count",
        "hard_gate.context.fact_retention",
    } <= regressions
    assert comparison.regression is True


def test_missing_checkpoint_is_unconditional_regression() -> None:
    comparison = compare_reports(report(run()), report(run(checkpoint=False)))
    change = next(
        item
        for item in comparison.changes
        if item.metric == "context_checkpoint.after"
    )
    assert change.classification == "regression"


def test_context_improvements_and_unchanged_are_classified() -> None:
    improvement = compare_reports(
        report(run(retention=0.8, token_error_tokens=3000, reclaimed_tokens=50_000)),
        report(run(retention=1, token_error_tokens=500, reclaimed_tokens=100_000)),
    )
    assert "improvement" in {change.classification for change in improvement.changes}
    unchanged = compare_reports(report(run()), report(run()))
    assert {change.classification for change in unchanged.changes} == {"unchanged"}
    assert "Context metric" in render_comparison_markdown(unchanged)


def test_reports_without_context_metrics_remain_comparable() -> None:
    execution = ExecutionResult(
        run_id="regular",
        case_id="regular",
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="now",
        duration_ms=1,
    )
    verdict = CaseScore(
        passed=True,
        dimensions=[
            DimensionScore(name=name, checks_passed=1, checks_total=1)
            for name in ("outcome", "trajectory", "efficiency", "safety", "reliability")
        ],
    )
    result = CaseRunResult(
        status=RunStatus.SUCCESS,
        execution=execution,
        verdict=verdict,
    )
    baseline = build_suite_report("regular", [result])
    candidate = build_suite_report("regular", [result])
    comparison = compare_reports(baseline, candidate)
    assert comparison.regression is False
