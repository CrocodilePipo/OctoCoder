from __future__ import annotations

import asyncio
from pathlib import Path

from octocoder.evals.models import EvalCase, ExecutionResult, ExecutionStatus, ToolTrace
from octocoder.evals.graders.base import GradeContext, GraderRegistry
from octocoder.evals.models import DimensionScore, Finding
from octocoder.evals.scoring import score_execution


def test_hard_gate_overrides_high_numeric_score(tmp_path: Path) -> None:
    case = EvalCase.model_validate(
        {
            "id": "hard-gate",
            "title": "Hard gate",
            "prompt": "work",
            "fixture": "fixture",
            "script": {"events": [], "effects": []},
            "expected": {"trajectory": {"forbidden": [{"tool": "delete_file"}]}},
        }
    )
    execution = ExecutionResult(
        run_id="run",
        case_id=case.id,
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="2026-01-01T00:00:00Z",
        duration_ms=1,
        trajectory=[ToolTrace(sequence=0, tool="delete_file")],
    )
    verdict = asyncio.run(score_execution(case, execution, tmp_path))
    assert verdict.passed is False
    assert any(finding.code == "forbidden_tool_used" for finding in verdict.findings)


def test_execution_failure_is_a_hard_gate(tmp_path: Path) -> None:
    case = EvalCase.model_validate(
        {
            "id": "failed",
            "title": "Failed",
            "prompt": "work",
            "fixture": "fixture",
            "script": {"events": [], "effects": []},
        }
    )
    execution = ExecutionResult(
        run_id="run",
        case_id=case.id,
        mode="scripted",
        status=ExecutionStatus.AGENT_FAILED,
        started_at="2026-01-01T00:00:00Z",
        duration_ms=1,
    )
    score = asyncio.run(score_execution(case, execution, tmp_path))
    assert score.passed is False
    assert any(finding.code == "execution.agent_failed" for finding in score.findings)


def test_custom_grader_registers_without_runner_changes(tmp_path: Path) -> None:
    class CustomSafetyGrader:
        async def grade(self, context: GradeContext) -> DimensionScore:
            assert context.workspace == tmp_path
            return DimensionScore(
                name="safety",
                checks_passed=0,
                checks_total=1,
                findings=[Finding(code="custom.block", message="blocked", hard_gate=True)],
            )

    case = EvalCase.model_validate(
        {
            "id": "custom",
            "title": "Custom",
            "prompt": "work",
            "fixture": "fixture",
            "script": {"events": [], "effects": []},
        }
    )
    execution = ExecutionResult(
        run_id="run", case_id=case.id, mode="scripted",
        status=ExecutionStatus.COMPLETED, started_at="now", duration_ms=1,
    )
    registry = GraderRegistry()
    registry.register(CustomSafetyGrader())
    score = asyncio.run(score_execution(case, execution, tmp_path, grader_registry=registry))
    assert score.passed is False
    assert any(finding.code == "custom.block" for finding in score.findings)


def test_context_dimension_is_conditional_and_hard_gate_overrides_score(
    tmp_path: Path,
) -> None:
    context_case = EvalCase.model_validate(
        {
            "id": "context-score",
            "title": "Context score",
            "prompt": "run",
            "fixture": "fixture",
            "script": {"events": []},
            "context": {
                "stages": [
                    {"id": "probe", "action": "checkpoint", "checkpoint": "after"}
                ],
                "facts": [
                    {
                        "id": "critical",
                        "value": "present",
                        "required_at": ["after"],
                        "hard_gate": True,
                    }
                ],
            },
        }
    )
    execution = ExecutionResult(
        run_id="run",
        case_id=context_case.id,
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="now",
        duration_ms=1,
    )
    score = asyncio.run(score_execution(context_case, execution, tmp_path))
    assert [dimension.name for dimension in score.dimensions][-1] == "context"
    assert len(score.dimensions) == 6
    assert score.passed is False
    assert any(finding.code == "context.fact_retention" for finding in score.findings)
    assert execution.context_metrics is not None


def test_non_context_score_shape_remains_five_dimensions(tmp_path: Path) -> None:
    regular_case = EvalCase.model_validate(
        {
            "id": "regular-score",
            "title": "Regular score",
            "prompt": "run",
            "fixture": "fixture",
            "script": {"events": []},
        }
    )
    execution = ExecutionResult(
        run_id="run",
        case_id=regular_case.id,
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="now",
        duration_ms=1,
    )
    score = asyncio.run(score_execution(regular_case, execution, tmp_path))
    assert [dimension.name for dimension in score.dimensions] == [
        "outcome",
        "trajectory",
        "efficiency",
        "safety",
        "reliability",
    ]
    assert all(
        dimension.checks_passed == dimension.checks_total
        for dimension in score.dimensions
    )
    assert execution.context_metrics is None
