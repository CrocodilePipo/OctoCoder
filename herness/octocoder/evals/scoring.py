from __future__ import annotations

from pathlib import Path

from octocoder.evals.graders.base import GradeContext, GraderRegistry
from octocoder.evals.graders.context import ContextGrader
from octocoder.evals.graders.outcome import grade_outcomes
from octocoder.evals.graders.trajectory import grade_trajectory
from octocoder.evals.models import (
    CaseScore,
    DimensionScore,
    EvalCase,
    ExecutionResult,
    ExecutionStatus,
    Finding,
)
from octocoder.evals.redaction import SecretRedactor


async def score_execution(
    case: EvalCase,
    execution: ExecutionResult,
    workspace: Path,
    event_findings: list[Finding] | None = None,
    redactor: SecretRedactor | None = None,
    grader_registry: GraderRegistry | None = None,
) -> CaseScore:
    event_findings = event_findings or []
    redactor = redactor or SecretRedactor()
    outcome = await grade_outcomes(case, execution, workspace, redactor)
    trajectory = grade_trajectory(case.expected.trajectory, execution.trajectory)

    efficiency_checks = [
        ("tool_calls", len(execution.trajectory), case.limits.max_tool_calls),
        ("turns", execution.turns, case.limits.max_turns),
        (
            "duration_ms",
            execution.duration_ms,
            int(case.limits.timeout_seconds * 1000),
        ),
    ]
    if case.limits.max_input_tokens:
        efficiency_checks.append(
            ("input_tokens", execution.usage.input_tokens, case.limits.max_input_tokens)
        )
    if case.limits.max_output_tokens:
        efficiency_checks.append(
            ("output_tokens", execution.usage.output_tokens, case.limits.max_output_tokens)
        )
    efficiency_findings = [
        Finding(
            code=f"efficiency.{name}",
            message=f"Execution exceeded the declared {name} limit",
            evidence={"actual": actual, "maximum": maximum},
        )
        for name, actual, maximum in efficiency_checks
        if actual > maximum
    ]
    efficiency_passed = sum(
        actual <= maximum for _, actual, maximum in efficiency_checks
    )

    safety_findings = [
        finding
        for finding in trajectory.findings + outcome.findings
        if finding.code == "forbidden_tool_used"
        or finding.code.startswith("outcome.")
        and finding.hard_gate
    ]

    retries = sum(bool(trace.retry_of) for trace in execution.trajectory)
    reliability_checks = [
        execution.status == ExecutionStatus.COMPLETED,
        execution.malformed_event_count == 0,
        execution.unpaired_event_count == 0,
        retries == 0,
    ]
    reliability_findings = list(event_findings)
    for code, actual in (
        ("malformed_events", execution.malformed_event_count),
        ("unpaired_events", execution.unpaired_event_count),
        ("retries", retries),
    ):
        if actual:
            reliability_findings.append(
                Finding(
                    code=f"reliability.{code}",
                    message=f"Execution observed {actual} {code.replace('_', ' ')}",
                    evidence={"count": actual},
                )
            )
    if execution.status != ExecutionStatus.COMPLETED:
        reliability_findings.append(
            Finding(
                code=f"execution.{execution.status.value}",
                message=f"Execution ended with status {execution.status.value}",
                hard_gate=True,
                evidence={"errors": execution.errors},
            )
        )

    dimensions = [
        DimensionScore(
            name="outcome",
            checks_passed=outcome.passed_weight,
            checks_total=outcome.total_weight,
            findings=outcome.findings,
        ),
        DimensionScore(
            name="trajectory",
            checks_passed=trajectory.passed_weight,
            checks_total=trajectory.total_weight,
            findings=trajectory.findings,
        ),
        DimensionScore(
            name="efficiency",
            checks_passed=efficiency_passed,
            checks_total=len(efficiency_checks),
            findings=efficiency_findings,
        ),
        DimensionScore(
            name="safety",
            checks_passed=0 if safety_findings else 1,
            checks_total=1,
            findings=safety_findings,
        ),
        DimensionScore(
            name="reliability",
            checks_passed=sum(reliability_checks),
            checks_total=len(reliability_checks),
            findings=reliability_findings,
        ),
    ]
    grade_context = GradeContext(case, execution, workspace, redactor)
    if case.context is not None:
        dimensions.append(await ContextGrader().grade(grade_context))
    if grader_registry is not None:
        by_name = {dimension.name: dimension for dimension in dimensions}
        for grader in grader_registry.graders:
            additional = await grader.grade(grade_context)
            if additional.name not in by_name:
                dimensions.append(additional)
                by_name[additional.name] = additional
                continue
            current = by_name[additional.name]
            current.checks_passed += additional.checks_passed
            current.checks_total += additional.checks_total
            current.findings.extend(additional.findings)
    findings = []
    seen: set[tuple[str, str]] = set()
    for dimension in dimensions:
        for finding in dimension.findings:
            identity = (finding.code, finding.message)
            if identity not in seen:
                seen.add(identity)
                findings.append(finding)
    hard_gate_failed = any(finding.hard_gate for finding in findings)
    passed = execution.status == ExecutionStatus.COMPLETED and not hard_gate_failed
    return CaseScore(passed=passed, dimensions=dimensions, findings=findings)
