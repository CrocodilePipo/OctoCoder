from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

from octocoder.evals.models import (
    ComparisonChange,
    ComparisonReport,
    ComparisonThresholds,
    ExecutionMode,
    SuiteReport,
)


def load_report(path: Path) -> SuiteReport:
    return SuiteReport.model_validate(json.loads(path.read_text(encoding="utf-8")))


def compare_reports(
    baseline: SuiteReport,
    candidate: SuiteReport,
    thresholds: ComparisonThresholds | None = None,
) -> ComparisonReport:
    thresholds = thresholds or candidate.thresholds
    changes: list[ComparisonChange] = []
    baseline_cases: dict[str, list] = defaultdict(list)
    candidate_cases: dict[str, list] = defaultdict(list)
    for result in baseline.results:
        baseline_cases[result.execution.case_id].append(result)
    for result in candidate.results:
        candidate_cases[result.execution.case_id].append(result)

    def mean(items, getter) -> float | None:
        values = [value for item in items if (value := getter(item)) is not None]
        return statistics.fmean(values) if values else None

    def token_count(item, field: str) -> int | None:
        usage = item.execution.usage
        if (
            item.execution.mode == ExecutionMode.REAL
            and usage.input_tokens == 0
            and usage.output_tokens == 0
        ):
            return None
        return int(getattr(usage, field))

    def increase_change(before: float, after: float, maximum: float) -> str:
        delta = after - before
        if delta > maximum:
            return "regression"
        if delta < -maximum:
            return "improvement"
        return "unchanged"

    def numeric_change(before: float, after: float, tolerance: float) -> str:
        delta = after - before
        if delta < -tolerance:
            return "regression"
        if delta > tolerance:
            return "improvement"
        return "unchanged"

    for case_id in sorted(set(baseline_cases).union(candidate_cases)):
        before = baseline_cases.get(case_id)
        after = candidate_cases.get(case_id)
        if before is not None and after is None:
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric="presence",
                    baseline=True,
                    candidate=False,
                    classification="regression",
                    message="Candidate report is missing a baseline case",
                )
            )
            continue
        if before is None and after is not None:
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric="presence",
                    baseline=False,
                    candidate=True,
                    classification="improvement",
                    message="Candidate report contains a new case",
                )
            )
            continue
        assert before is not None and after is not None
        before_failed = sum(not item.verdict.passed for item in before)
        after_failed = sum(not item.verdict.passed for item in after)
        if before_failed != after_failed:
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric="failed_runs",
                    baseline=before_failed,
                    candidate=after_failed,
                    classification=(
                        "regression"
                        if after_failed - before_failed > thresholds.failed_runs_increase
                        else "improvement"
                        if after_failed < before_failed
                        else "unchanged"
                    ),
                    message="Failed run count changed",
                )
            )
        resource_metrics = [
            (
                "duration_ms",
                mean(before, lambda item: item.execution.duration_ms),
                mean(after, lambda item: item.execution.duration_ms),
                thresholds.duration_increase_ms,
            ),
            (
                "input_tokens",
                mean(before, lambda item: token_count(item, "input_tokens")),
                mean(after, lambda item: token_count(item, "input_tokens")),
                thresholds.input_tokens_increase,
            ),
            (
                "output_tokens",
                mean(before, lambda item: token_count(item, "output_tokens")),
                mean(after, lambda item: token_count(item, "output_tokens")),
                thresholds.output_tokens_increase,
            ),
            (
                "tool_calls",
                mean(before, lambda item: len(item.execution.trajectory)),
                mean(after, lambda item: len(item.execution.trajectory)),
                thresholds.tool_calls_increase,
            ),
            (
                "turns",
                mean(before, lambda item: item.execution.turns),
                mean(after, lambda item: item.execution.turns),
                thresholds.turns_increase,
            ),
        ]
        for metric, before_value, after_value, tolerance in resource_metrics:
            if before_value is None and after_value is None:
                continue
            if before_value is not None and after_value is None:
                classification = "regression"
                message = "Candidate is missing a baseline measurement"
            elif before_value is None:
                classification = "improvement"
                message = "Candidate added a measurement"
            else:
                assert after_value is not None
                classification = increase_change(before_value, after_value, tolerance)
                message = ""
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric=metric,
                    baseline=before_value,
                    candidate=after_value,
                    classification=classification,
                    message=message,
                )
            )
        before_gates = {finding.code for item in before for finding in item.verdict.findings if finding.hard_gate}
        after_gates = {finding.code for item in after for finding in item.verdict.findings if finding.hard_gate}
        for code in sorted(after_gates - before_gates):
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric=f"hard_gate.{code}",
                    baseline=False,
                    candidate=True,
                    classification="regression",
                    message="Candidate introduced a hard-gate failure",
                )
            )

        before_checkpoints = {
            checkpoint.id
            for item in before
            for checkpoint in item.execution.context_checkpoints
        }
        after_checkpoints = {
            checkpoint.id
            for item in after
            for checkpoint in item.execution.context_checkpoints
        }
        for checkpoint_id in sorted(before_checkpoints - after_checkpoints):
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric=f"context_checkpoint.{checkpoint_id}",
                    baseline=True,
                    candidate=False,
                    classification="regression",
                    message="Candidate is missing a baseline context checkpoint",
                )
            )

        def context_mean(items, attribute: str) -> float | None:
            values = [
                float(value)
                for item in items
                if item.execution.context_metrics is not None
                and (value := getattr(item.execution.context_metrics, attribute)) is not None
            ]
            return statistics.fmean(values) if values else None

        context_thresholds = [
            ("retention_rate", thresholds.context_retention_drop, "lower"),
            ("instruction_adherence_rate", thresholds.context_adherence_drop, "lower"),
            ("resume_consistency_rate", thresholds.context_resume_drop, "lower"),
            ("token_error_tokens_mean", thresholds.context_token_error_increase_tokens, "higher"),
            ("reclaimed_tokens_total", thresholds.context_reclaimed_tokens_drop, "lower"),
            ("retained_tokens_max", thresholds.context_retained_tokens_increase, "higher"),
            ("compaction_count", thresholds.context_compaction_count_increase, "higher"),
            ("contamination_count", thresholds.context_contamination_increase, "higher"),
        ]
        for metric, tolerance, direction in context_thresholds:
            if tolerance is None:
                continue
            before_value = context_mean(before, metric)
            after_value = context_mean(after, metric)
            if before_value is None and after_value is None:
                continue
            if before_value is not None and after_value is None:
                classification = "regression"
                message = "Candidate is missing a baseline context metric"
            elif before_value is None:
                classification = "improvement"
                message = "Candidate added a context metric"
            else:
                assert after_value is not None
                delta = after_value - before_value
                if direction == "lower":
                    classification = (
                        "regression"
                        if delta < -float(tolerance)
                        else "improvement"
                        if delta > float(tolerance)
                        else "unchanged"
                    )
                else:
                    classification = (
                        "regression"
                        if delta > float(tolerance)
                        else "improvement"
                        if delta < -float(tolerance)
                        else "unchanged"
                    )
                message = "Context metric changed"
            changes.append(
                ComparisonChange(
                    case_id=case_id,
                    metric=f"context.{metric}",
                    baseline=before_value,
                    candidate=after_value,
                    classification=classification,
                    message=message,
                )
            )
    failed_runs_delta = candidate.failed_runs - baseline.failed_runs
    changes.append(
        ComparisonChange(
            case_id="__suite__",
            metric="failed_runs",
            baseline=baseline.failed_runs,
            candidate=candidate.failed_runs,
            classification=(
                "regression"
                if failed_runs_delta > thresholds.failed_runs_increase
                else "improvement"
                if failed_runs_delta < -thresholds.failed_runs_increase
                else "unchanged"
            ),
        )
    )
    return ComparisonReport(
        baseline_suite_id=baseline.suite_id,
        candidate_suite_id=candidate.suite_id,
        regression=any(change.classification == "regression" for change in changes),
        changes=changes,
    )


def render_comparison_markdown(report: ComparisonReport) -> str:
    lines = [
        "# Evaluation comparison",
        "",
        f"- Baseline: `{report.baseline_suite_id}`",
        f"- Candidate: `{report.candidate_suite_id}`",
        f"- Regression: `{str(report.regression).lower()}`",
        "",
        "| Case | Metric | Baseline | Candidate | Classification | Message |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    lines.extend(
        f"| {change.case_id} | {change.metric} | {change.baseline} | {change.candidate} | {change.classification} | {change.message} |"
        for change in report.changes
    )
    return "\n".join(lines) + "\n"
