from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Iterable

from octocoder.evals.models import (
    CaseRunResult,
    ComparisonThresholds,
    ExecutionMode,
    MetricSummary,
    SuiteReport,
)


def summarize(values: Iterable[float | None]) -> MetricSummary:
    data = sorted(float(value) for value in values if value is not None)
    if not data:
        return MetricSummary()
    p95 = None
    if len(data) >= 2:
        index = max(0, math.ceil(0.95 * len(data)) - 1)
        p95 = data[index]
    return MetricSummary(
        samples=len(data),
        mean=statistics.fmean(data),
        median=statistics.median(data),
        minimum=data[0],
        maximum=data[-1],
        p95=p95,
    )


def _token_count(result: CaseRunResult, field: str) -> int | None:
    usage = result.execution.usage
    if (
        result.execution.mode == ExecutionMode.REAL
        and usage.input_tokens == 0
        and usage.output_tokens == 0
    ):
        return None
    return int(getattr(usage, field))


def build_suite_report(
    suite_id: str,
    results: list[CaseRunResult],
    thresholds: ComparisonThresholds | None = None,
) -> SuiteReport:
    passed = sum(result.verdict.passed for result in results)
    context_values: dict[str, list[float]] = defaultdict(list)
    for result in results:
        metrics = result.execution.context_metrics
        if metrics is None:
            continue
        for name in (
            "retention_rate",
            "instruction_adherence_rate",
            "continuity_rate",
            "resume_consistency_rate",
            "token_error_tokens_mean",
        ):
            value = getattr(metrics, name)
            if value is not None:
                context_values[name].append(float(value))
        context_values["compaction_count"].append(float(metrics.compaction_count))
        context_values["reclaimed_tokens_total"].append(
            float(metrics.reclaimed_tokens_total)
        )
        for name in (
            "compaction_before_tokens_total",
            "compaction_after_tokens_total",
            "retained_tokens_max",
            "spill_chars_total",
            "contamination_count",
        ):
            context_values[name].append(float(getattr(metrics, name)))
    return SuiteReport(
        suite_id=suite_id,
        passed=passed == len(results) and bool(results),
        total_runs=len(results),
        passed_runs=passed,
        failed_runs=len(results) - passed,
        results=results,
        thresholds=thresholds or ComparisonThresholds(),
        duration_summary=summarize(result.execution.duration_ms for result in results),
        input_tokens_summary=summarize(
            _token_count(result, "input_tokens") for result in results
        ),
        output_tokens_summary=summarize(
            _token_count(result, "output_tokens") for result in results
        ),
        turns_summary=summarize(result.execution.turns for result in results),
        tool_calls_summary=summarize(
            len(result.execution.trajectory) for result in results
        ),
        context_summary={
            name: summarize(values) for name, values in sorted(context_values.items())
        },
    )


def render_case_markdown(result: CaseRunResult) -> str:
    input_tokens = _token_count(result, "input_tokens")
    output_tokens = _token_count(result, "output_tokens")
    lines = [
        f"# {result.execution.case_id}",
        "",
        f"- Status: `{result.status.value}`",
        f"- Passed: `{str(result.verdict.passed).lower()}`",
        f"- Duration: `{result.execution.duration_ms} ms`",
        f"- Turns: `{result.execution.turns}`",
        f"- Tool calls: `{len(result.execution.trajectory)}`",
        f"- Input tokens: `{'n/a' if input_tokens is None else input_tokens}`",
        f"- Output tokens: `{'n/a' if output_tokens is None else output_tokens}`",
        "",
        "## Artifacts",
        "",
        "- [Raw events](raw-events.jsonl)",
        "- [Normalized events](events.jsonl)",
        "- [Tool trajectory](trajectory.json)",
        "- [Workspace patch](workspace.patch)",
        "- [Verdict and grader evidence](verdict.json)",
        "- [Standard error](stderr.txt)",
        "",
        "## Checks",
        "",
        "| Dimension | Passed | Total | Failed | Findings |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        f"| {dimension.name} | {dimension.checks_passed:g} | "
        f"{dimension.checks_total:g} | "
        f"{dimension.checks_total - dimension.checks_passed:g} | "
        f"{len(dimension.findings)} |"
        for dimension in result.verdict.dimensions
    )
    metrics = result.execution.context_metrics
    if metrics is not None:
        lines.extend(
            [
                "",
                "## Context Artifacts",
                "",
                "- [Context timeline](context-events.jsonl)",
                "- [Context checkpoints](context-checkpoints.json)",
                "- [Context metrics](context-metrics.json)",
                "",
                "## Context Metrics",
                "",
                "| Metric | Value |",
                "| --- | ---: |",
            ]
        )
        similarity_rows = {
            "fact_retention_similarity": metrics.retention_rate,
            "instruction_adherence_similarity": metrics.instruction_adherence_rate,
            "task_continuity_similarity": metrics.continuity_rate,
            "resume_similarity": metrics.resume_consistency_rate,
        }
        for name, value in similarity_rows.items():
            rendered = "n/a" if value is None else f"{value:.1%}"
            lines.append(f"| {name} | {rendered} |")
        measurement_rows = {
            "duration_ms": result.execution.duration_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "token_error_tokens_mean": metrics.token_error_tokens_mean,
            "token_error_tokens_max": metrics.token_error_tokens_max,
            "compaction_before_tokens_total": metrics.compaction_before_tokens_total,
            "compaction_after_tokens_total": metrics.compaction_after_tokens_total,
            "reclaimed_tokens_total": metrics.reclaimed_tokens_total,
            "retained_tokens_max": metrics.retained_tokens_max,
            "spill_chars_total": metrics.spill_chars_total,
            "compaction_count": metrics.compaction_count,
            "contamination_count": metrics.contamination_count,
        }
        for name, value in measurement_rows.items():
            rendered = "n/a" if value is None else f"{value:.1f}" if isinstance(value, float) else str(value)
            lines.append(f"| {name} | {rendered} |")
        lines.extend(
            [
                "",
                "### Context Checks",
                "",
                "| Check group | Passed | Total | Similarity | Findings |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for subscore in metrics.subscores:
            lines.append(
                f"| {subscore.name} | {subscore.checks_passed} | "
                f"{subscore.checks_total} | "
                f"{'n/a' if subscore.similarity is None else f'{subscore.similarity:.1%}'} | "
                f"{len(subscore.findings)} |"
            )
        lines.extend(
            [
                "",
                "### Context Checkpoints",
                "",
                "| Checkpoint | Stage | Source | Facts | Instructions | Tool pairs |",
                "| --- | --- | --- | ---: | ---: | --- |",
            ]
        )
        for checkpoint in result.execution.context_checkpoints:
            lines.append(
                f"| {checkpoint.id} | {checkpoint.stage_id} | {checkpoint.source} | "
                f"{len(checkpoint.facts)} | {len(checkpoint.active_instructions)} | "
                f"{'complete' if checkpoint.tool_pair_complete else 'broken'} |"
            )
    if result.verdict.findings:
        lines.extend(["", "## Findings", ""])
        for finding in result.verdict.findings:
            gate = " hard gate" if finding.hard_gate else ""
            location = ""
            checkpoint_id = finding.evidence.get("checkpoint_id")
            stage_id = finding.evidence.get("stage_id")
            if checkpoint_id or stage_id:
                location = f" (stage `{stage_id or '-'}`, checkpoint `{checkpoint_id or '-'}`)"
            lines.append(f"- `{finding.code}`{gate}{location}: {finding.message}")
    return "\n".join(lines) + "\n"


def render_suite_markdown(report: SuiteReport) -> str:
    grouped: dict[str, list[CaseRunResult]] = defaultdict(list)
    for result in report.results:
        grouped[result.execution.case_id].append(result)
    lines = [
        f"# Evaluation suite: {report.suite_id}",
        "",
        f"- Passed: `{str(report.passed).lower()}`",
        f"- Runs: `{report.total_runs}`",
        f"- Passed runs: `{report.passed_runs}`",
        f"- Failed runs: `{report.failed_runs}`",
        "",
        "| Case | Runs | Passed | Failed | Mean duration | Mean input tokens | Mean output tokens | Mean turns | Mean tool calls | Artifacts |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for case_id in sorted(grouped):
        results = grouped[case_id]
        durations = summarize(item.execution.duration_ms for item in results)
        input_tokens = summarize(_token_count(item, "input_tokens") for item in results)
        output_tokens = summarize(_token_count(item, "output_tokens") for item in results)
        turns = summarize(item.execution.turns for item in results)
        tool_calls = summarize(len(item.execution.trajectory) for item in results)
        passed = sum(item.verdict.passed for item in results)
        artifacts = ", ".join(item.artifact_path or "-" for item in results)
        lines.append(
            f"| {case_id} | {len(results)} | {passed} | {len(results) - passed} | "
            f"{durations.mean:.0f} ms | "
            f"{'n/a' if input_tokens.samples == 0 else f'{input_tokens.mean:.0f}'} | "
            f"{'n/a' if output_tokens.samples == 0 else f'{output_tokens.mean:.0f}'} | "
            f"{turns.mean:.1f} | {tool_calls.mean:.1f} | {artifacts} |"
        )
    lines.extend(
        [
            "",
            "## Execution Measurements",
            "",
            "| Metric | Mean | Median | Min | Max | p95 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    measurement_summaries = (
        ("duration_ms", report.duration_summary, " ms"),
        ("input_tokens", report.input_tokens_summary, ""),
        ("output_tokens", report.output_tokens_summary, ""),
        ("turns", report.turns_summary, ""),
        ("tool_calls", report.tool_calls_summary, ""),
    )
    for name, summary, unit in measurement_summaries:
        if summary.samples == 0:
            lines.append(f"| {name} | n/a | n/a | n/a | n/a | n/a |")
        else:
            p95 = "n/a" if summary.p95 is None else f"{summary.p95:.1f}{unit}"
            lines.append(
                f"| {name} | {summary.mean:.1f}{unit} | {summary.median:.1f}{unit} | "
                f"{summary.minimum:.1f}{unit} | {summary.maximum:.1f}{unit} | {p95} |"
            )
    failures = [
        (result.execution.case_id, finding)
        for result in report.results
        for finding in result.verdict.findings
        if finding.hard_gate
    ]
    if failures:
        lines.extend(["", "## Hard-gate failures", ""])
        lines.extend(f"- `{case_id}` / `{finding.code}`: {finding.message}" for case_id, finding in failures)
    if report.context_summary:
        lines.extend(
            [
                "",
                "## Context Summary",
                "",
                "| Metric | Mean | Median | Min | Max | p95 |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        similarity_names = {
            "retention_rate",
            "instruction_adherence_rate",
            "continuity_rate",
            "resume_consistency_rate",
        }
        for name, summary in sorted(report.context_summary.items()):
            formatter = (lambda value: f"{value:.1%}") if name in similarity_names else (lambda value: f"{value:.1f}")
            p95 = "n/a" if summary.p95 is None else formatter(summary.p95)
            lines.append(
                f"| {name} | {formatter(summary.mean)} | {formatter(summary.median)} | "
                f"{formatter(summary.minimum)} | {formatter(summary.maximum)} | {p95} |"
            )
    return "\n".join(lines) + "\n"
