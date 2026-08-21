from __future__ import annotations

import asyncio
from pathlib import Path

from octocoder.evals.graders.base import GradeContext
from octocoder.evals.graders.context import ContextGrader, build_context_metrics
from octocoder.evals.models import (
    ContextCheckpoint,
    ContextEvent,
    EvalCase,
    EvalEvent,
    ExecutionResult,
    ExecutionStatus,
)
from octocoder.evals.redaction import SecretRedactor


def case() -> EvalCase:
    return EvalCase.model_validate(
        {
            "id": "context-grade",
            "title": "Context grade",
            "prompt": "run",
            "fixture": "fixture",
            "script": {"events": []},
            "context": {
                "stages": [
                    {"id": "probe", "action": "checkpoint", "checkpoint": "after"},
                    {"id": "resume", "action": "resume", "checkpoint": "resumed"},
                ],
                "facts": [
                    {
                        "id": "name",
                        "value": "alpha",
                        "required_at": ["after", "resumed"],
                        "hard_gate": True,
                    },
                    {
                        "id": "old-name",
                        "value": "beta",
                        "forbidden_at": ["after", "resumed"],
                        "hard_gate": True,
                    },
                ],
                "instructions": [
                    {
                        "id": "json",
                        "text": "Use JSON",
                        "priority": "project",
                        "active_at": ["after", "resumed"],
                    },
                    {
                        "id": "plain",
                        "text": "Use plain text",
                        "priority": "user",
                        "superseded_at": ["after", "resumed"],
                    },
                ],
                "states": [
                    {
                        "checkpoint": "after",
                        "required_files": ["src/app.py"],
                        "pending_work": ["add tests"],
                        "known_failures": ["test_old"],
                        "expected_next_action": "run tests",
                        "require_complete_tool_pairs": True,
                    }
                ],
                "resumes": [
                    {
                        "before_checkpoint": "after",
                        "after_checkpoint": "resumed",
                        "equivalent_fact_ids": ["name"],
                        "equivalent_instruction_ids": ["json"],
                        "equivalent_state_fields": ["next_action"],
                    }
                ],
                "token": {
                    "max_absolute_error_tokens": 1000,
                    "trigger_tolerance_tokens": 1000,
                    "require_provider_anchor": True,
                    "hard_gate": True,
                },
                "compression": {
                    "min_reclaimed_tokens": 100000,
                    "max_after_tokens": 100000,
                    "max_retained_tokens": 10000,
                    "min_compactions": 1,
                    "max_compactions": 2,
                    "hard_gate": True,
                },
            },
        }
    )


def checkpoint(identifier: str, stage: str = "probe") -> ContextCheckpoint:
    return ContextCheckpoint(
        id=identifier,
        stage_id=stage,
        facts={"name": "alpha"},
        active_instructions=["json", "Use JSON"],
        task_state={
            "required_files": ["src/app.py"],
            "pending_work": ["add tests"],
            "known_failures": ["test_old"],
            "next_action": "run tests",
        },
        tool_pair_complete=True,
        source="scripted" if identifier == "after" else "resume",
    )


def events() -> list[ContextEvent]:
    return [
        ContextEvent(
            sequence=0,
            stage_id="probe",
            event_type="usage_anchor",
            estimated_tokens=99_000,
            provider_tokens=100_000,
        ),
        ContextEvent(
            sequence=1,
            stage_id="probe",
            event_type="compact_started",
            estimated_tokens=187_500,
            threshold_tokens=187_000,
            context_window=200_000,
        ),
        ContextEvent(
            sequence=2,
            stage_id="probe",
            event_type="compact_completed",
            before_tokens=190_000,
            after_tokens=40_000,
            retained_tokens=9_000,
            spilled_chars=0,
        ),
        ContextEvent(
            sequence=3,
            stage_id="probe",
            event_type="tool_result_spill",
            spilled_results=1,
            spilled_chars=25_000,
        ),
    ]


def execution(checkpoints=None, context_events=None, eval_events=None) -> ExecutionResult:
    return ExecutionResult(
        run_id="run",
        case_id="context-grade",
        mode="scripted",
        status=ExecutionStatus.COMPLETED,
        started_at="now",
        duration_ms=1,
        context_events=context_events if context_events is not None else events(),
        context_checkpoints=checkpoints
        if checkpoints is not None
        else [checkpoint("after"), checkpoint("resumed", "resume")],
        events=eval_events or [],
    )


def test_all_context_subscores_pass_with_complete_evidence(tmp_path: Path) -> None:
    current_case = case()
    current_execution = execution()
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(current_case, current_execution, tmp_path, SecretRedactor())
        )
    )
    assert dimension.checks_passed == dimension.checks_total
    assert dimension.findings == []
    assert current_execution.context_metrics is not None
    assert current_execution.context_metrics.retention_rate == 1
    assert current_execution.context_metrics.reclaimed_tokens_total == 150_000
    assert current_execution.context_metrics.spill_chars_total == 25_000
    assert {subscore.name for subscore in current_execution.context_metrics.subscores} == {
        "retention",
        "instruction_adherence",
        "continuity",
        "resume_consistency",
        "token_accuracy",
        "compression_efficiency",
        "contamination",
    }


def test_critical_fact_loss_and_stale_contamination_are_hard_gates(tmp_path: Path) -> None:
    after = checkpoint("after")
    after.facts = {"old-name": "beta"}
    after.answer = "The old value is beta"
    current_execution = execution([after, checkpoint("resumed", "resume")])
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(case(), current_execution, tmp_path, SecretRedactor())
        )
    )
    codes = {finding.code for finding in dimension.findings}
    assert "context.fact_retention" in codes
    assert "context.stale_fact" in codes
    assert all(
        finding.hard_gate
        for finding in dimension.findings
        if finding.code in {"context.fact_retention", "context.stale_fact"}
    )
    assert current_execution.context_metrics.contamination_count > 0


def test_stale_fact_in_subsequent_tool_action_is_detected(tmp_path: Path) -> None:
    tool_event = EvalEvent(
        sequence=5,
        event_type="tool_use",
        run_id="run",
        payload={"stage_id": "probe", "tool_name": "write", "args": {"value": "beta"}},
    )
    current_execution = execution(eval_events=[tool_event])
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(case(), current_execution, tmp_path, SecretRedactor())
        )
    )
    assert any(finding.code == "context.stale_fact" for finding in dimension.findings)


def test_instruction_priority_and_continuity_fail_at_exact_checkpoint(tmp_path: Path) -> None:
    after = checkpoint("after")
    after.active_instructions = ["plain", "Use plain text"]
    after.task_state = {
        "required_files": [],
        "pending_work": [],
        "known_failures": [],
        "next_action": "ship",
    }
    after.tool_pair_complete = False
    current_execution = execution([after, checkpoint("resumed", "resume")])
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(case(), current_execution, tmp_path, SecretRedactor())
        )
    )
    codes = {finding.code for finding in dimension.findings}
    assert {
        "context.active_instruction",
        "context.superseded_instruction",
        "context.required_file",
        "context.pending_work",
        "context.known_failures",
        "context.next_action",
        "context.tool_pair",
    } <= codes
    assert all(
        finding.evidence.get("checkpoint_id") == "after"
        for finding in dimension.findings
        if finding.code.startswith("context.")
        and finding.code not in {"context.resume_instruction"}
        and "checkpoint_id" in finding.evidence
    )


def test_resume_divergence_is_separate_hard_gate(tmp_path: Path) -> None:
    resumed = checkpoint("resumed", "resume")
    resumed.facts["name"] = "changed"
    resumed.active_instructions = []
    resumed.task_state["next_action"] = "different"
    current_execution = execution([checkpoint("after"), resumed])
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(case(), current_execution, tmp_path, SecretRedactor())
        )
    )
    codes = {finding.code for finding in dimension.findings}
    assert {"context.resume_fact", "context.resume_instruction", "context.resume_state"} <= codes
    assert current_execution.context_metrics.resume_consistency_rate == 0


def test_token_drift_overflow_and_ineffective_compression_are_measured(tmp_path: Path) -> None:
    bad_events = [
        ContextEvent(
            sequence=0,
            stage_id="probe",
            event_type="usage_anchor",
            estimated_tokens=60_000,
            provider_tokens=100_000,
        ),
        ContextEvent(
            sequence=1,
            stage_id="probe",
            event_type="compact_started",
            estimated_tokens=210_000,
            threshold_tokens=187_000,
            context_window=200_000,
        ),
        ContextEvent(
            sequence=2,
            stage_id="probe",
            event_type="compact_completed",
            before_tokens=210_000,
            after_tokens=205_000,
            retained_tokens=50_000,
            context_window=200_000,
        ),
    ]
    current_execution = execution(context_events=bad_events)
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(case(), current_execution, tmp_path, SecretRedactor())
        )
    )
    codes = {finding.code for finding in dimension.findings}
    assert {
        "context.token_estimate",
        "context.compaction_trigger_drift",
        "context.overflow",
        "context.reclaimed_tokens",
        "context.after_tokens",
        "context.retained_tokens",
    } <= codes
    metrics = current_execution.context_metrics
    assert metrics.token_error_tokens_max == 40_000
    assert metrics.reclaimed_tokens_total == 5_000


def test_typed_fact_matching_supports_all_operators() -> None:
    expectation = case().context.model_copy(
        update={
            "facts": [
                type(case().context.facts[0]).model_validate(item)
                for item in [
                    {"id": "equals", "value": 3, "operator": "equals", "required_at": ["after"]},
                    {"id": "contains", "value": "bc", "operator": "contains", "required_at": ["after"]},
                    {"id": "matches", "value": r"^a.+z$", "operator": "matches", "required_at": ["after"]},
                    {"id": "glob", "value": "src/*.py", "operator": "glob", "required_at": ["after"]},
                    {"id": "exists", "operator": "exists", "required_at": ["after"]},
                ]
            ],
            "instructions": [],
            "states": [],
            "resumes": [],
            "token": None,
            "compression": None,
        }
    )
    cp = ContextCheckpoint(
        id="after",
        stage_id="probe",
        facts={
            "equals": 3,
            "contains": "abcd",
            "matches": "abcz",
            "glob": "src/app.py",
            "exists": False,
        },
        source="scripted",
    )
    metrics = build_context_metrics(expectation, [], [cp])
    assert metrics.retention_rate == 1


def test_optional_metrics_are_excluded_instead_of_scored_zero(tmp_path: Path) -> None:
    current_case = case()
    current_case.context.token = None
    current_case.context.compression = None
    current_execution = execution(context_events=[])
    dimension = asyncio.run(
        ContextGrader().grade(
            GradeContext(current_case, current_execution, tmp_path, SecretRedactor())
        )
    )
    names = {subscore.name for subscore in current_execution.context_metrics.subscores}
    assert "token_accuracy" not in names
    assert "compression_efficiency" not in names
    assert dimension.checks_passed == dimension.checks_total
