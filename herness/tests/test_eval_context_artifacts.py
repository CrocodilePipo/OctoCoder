from __future__ import annotations

from pathlib import Path

import pytest

from octocoder.evals.artifacts import ArtifactError, ArtifactWriter
from octocoder.evals.models import (
    CaseRunResult,
    CaseScore,
    ContextCheckpoint,
    ContextEvent,
    ContextMetrics,
    DimensionScore,
    EvalCase,
    ExecutionResult,
    ExecutionStatus,
    Finding,
    RunStatus,
)
from octocoder.evals.redaction import SecretRedactor
from octocoder.evals.report import build_suite_report, render_case_markdown, render_suite_markdown


def context_result(secret: str = "") -> tuple[EvalCase, CaseRunResult]:
    case = EvalCase.model_validate(
        {
            "id": "context-artifact",
            "title": "Context artifact",
            "prompt": "run",
            "fixture": "fixture",
            "script": {"events": []},
            "context": {
                "stages": [
                    {"id": "probe", "action": "checkpoint", "checkpoint": "after"}
                ]
            },
        }
    )
    execution = ExecutionResult(
        run_id="context-run",
        case_id=case.id,
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="now",
        duration_ms=1,
        context_events=[
            ContextEvent(
                sequence=0,
                stage_id="probe",
                event_type="checkpoint",
                payload={"bounded": secret or "ok"},
            )
        ],
        context_checkpoints=[
            ContextCheckpoint(
                id="after",
                stage_id="probe",
                facts={"value": secret or "ok"},
                source="scripted",
            )
        ],
        context_metrics=ContextMetrics(retention_rate=1),
    )
    verdict = CaseScore(
        passed=True,
        dimensions=[
            DimensionScore(name=name, checks_passed=1, checks_total=1)
            for name in (
                "outcome",
                "trajectory",
                "efficiency",
                "safety",
                "reliability",
                "context",
            )
        ],
    )
    return case, CaseRunResult(
        status=RunStatus.SUCCESS,
        execution=execution,
        verdict=verdict,
    )


def test_context_artifacts_have_stable_conditional_layout(tmp_path: Path) -> None:
    case, result = context_result()
    directory = ArtifactWriter(tmp_path).write_case(case, result)
    names = {path.name for path in directory.iterdir()}
    assert {
        "context-events.jsonl",
        "context-checkpoints.json",
        "context-metrics.json",
    } <= names
    assert '"event_type": "checkpoint"' in (
        directory / "context-events.jsonl"
    ).read_text(encoding="utf-8")
    assert '"retention_rate": 1.0' in (
        directory / "context-metrics.json"
    ).read_text(encoding="utf-8")


def test_context_artifacts_redact_every_serialized_file(tmp_path: Path) -> None:
    secret = "context-artifact-secret"
    case, result = context_result(secret)
    directory = ArtifactWriter(tmp_path, SecretRedactor([secret])).write_case(case, result)
    for path in directory.iterdir():
        assert secret not in path.read_text(encoding="utf-8")
    assert "[REDACTED]" in (
        directory / "context-checkpoints.json"
    ).read_text(encoding="utf-8")


def test_context_artifacts_reject_overwrite(tmp_path: Path) -> None:
    case, result = context_result()
    writer = ArtifactWriter(tmp_path)
    writer.write_case(case, result)
    with pytest.raises(ArtifactError, match="already exists"):
        writer.write_case(case, result)


def test_context_case_report_links_metrics_and_exact_checkpoint() -> None:
    _, result = context_result()
    result.verdict.findings.append(
        Finding(
            code="context.fact_retention",
            message="critical fact missing",
            hard_gate=True,
            evidence={"stage_id": "probe", "checkpoint_id": "after"},
        )
    )
    markdown = render_case_markdown(result)
    assert "[Context timeline](context-events.jsonl)" in markdown
    assert "| fact_retention_similarity | 100.0% |" in markdown
    assert "| after | probe | scripted |" in markdown
    assert "stage `probe`, checkpoint `after`" in markdown


def test_context_suite_report_aggregates_repetitions_deterministically() -> None:
    _, first = context_result()
    _, second = context_result()
    first.execution.run_id = "first"
    first.artifact_path = "first"
    second.execution.run_id = "second"
    second.artifact_path = "second"
    second.execution.context_metrics.retention_rate = 0.5
    second.execution.context_metrics.compaction_count = 2
    report = build_suite_report("context", [first, second])
    assert report.context_summary["retention_rate"].mean == 0.75
    assert report.context_summary["retention_rate"].p95 == 1.0
    assert report.context_summary["compaction_count"].median == 1
    markdown = render_suite_markdown(report)
    assert "## Context Summary" in markdown
    assert "| retention_rate | 75.0% |" in markdown
