from __future__ import annotations

from collections import Counter

from octocoder.evals.graders.base import GradeResult
from octocoder.evals.graders.matching import matches_argument
from octocoder.evals.models import (
    Finding,
    MatchMode,
    ToolExpectation,
    ToolTrace,
    TrajectoryExpectation,
)


def matches_tool(trace: ToolTrace, expected: ToolExpectation) -> bool:
    return trace.tool == expected.tool and all(
        matches_argument(trace.arguments, constraint) for constraint in expected.arguments
    )


def _order_is_subsequence(actual: list[str], expected: list[str]) -> bool:
    if not expected:
        return True
    position = 0
    for tool in actual:
        if tool == expected[position]:
            position += 1
            if position == len(expected):
                return True
    return False


def grade_trajectory(expectation: TrajectoryExpectation, trajectory: list[ToolTrace]) -> GradeResult:
    findings: list[Finding] = []
    checks = 0
    passed = 0
    for expected in expectation.required:
        checks += 1
        count = sum(matches_tool(trace, expected) for trace in trajectory)
        valid = count >= expected.min_calls and (
            expected.max_calls is None or count <= expected.max_calls
        )
        if valid:
            passed += 1
        else:
            findings.append(
                Finding(
                    code="required_tool_mismatch",
                    message=f"Required tool {expected.tool} expected {expected.min_calls}..{expected.max_calls or 'any'} calls, observed {count}",
                    hard_gate=True,
                    evidence={"tool": expected.tool, "actual_calls": count},
                )
            )
    for expected in expectation.forbidden:
        checks += 1
        matching = [trace for trace in trajectory if matches_tool(trace, expected)]
        if not matching:
            passed += 1
        else:
            findings.append(
                Finding(
                    code="forbidden_tool_used",
                    message=f"Forbidden tool {expected.tool} was used {len(matching)} time(s)",
                    hard_gate=True,
                    evidence={"tool": expected.tool, "sequences": [trace.sequence for trace in matching]},
                )
            )

    names = [trace.tool for trace in trajectory]
    if expectation.order:
        checks += 1
        valid_order = (
            names == expectation.order
            if expectation.match == MatchMode.EXACT
            else _order_is_subsequence(names, expectation.order)
        )
        if valid_order:
            passed += 1
        else:
            findings.append(
                Finding(
                    code="tool_order_mismatch",
                    message=f"Tool order did not match {expectation.match.value} expectation",
                    hard_gate=True,
                    evidence={"expected": expectation.order, "actual": names},
                )
            )
    elif expectation.match == MatchMode.EXACT and (expectation.required or expectation.forbidden):
        expected_names = [item.tool for item in expectation.required]
        checks += 1
        if names == expected_names:
            passed += 1
        else:
            findings.append(
                Finding(
                    code="tool_order_mismatch",
                    message="Exact trajectory did not match required tool list",
                    hard_gate=True,
                    evidence={"expected": expected_names, "actual": names},
                )
            )

    limits = [
        ("max_total_calls", expectation.max_total_calls, len(trajectory)),
        ("max_failed_calls", expectation.max_failed_calls, sum(t.result_status == "error" for t in trajectory)),
    ]
    for code, maximum, actual in limits:
        if maximum is None:
            continue
        checks += 1
        if actual <= maximum:
            passed += 1
        else:
            findings.append(
                Finding(
                    code=code,
                    message=f"{code} exceeded: maximum {maximum}, observed {actual}",
                    evidence={"maximum": maximum, "actual": actual},
                )
            )
    if expectation.max_repeated_identical_calls is not None:
        checks += 1
        repeated = max(Counter(trace.signature for trace in trajectory).values(), default=0)
        if repeated <= expectation.max_repeated_identical_calls:
            passed += 1
        else:
            findings.append(
                Finding(
                    code="max_repeated_identical_calls",
                    message=f"Identical tool call repeated {repeated} times",
                    evidence={"maximum": expectation.max_repeated_identical_calls, "actual": repeated},
                )
            )
    return GradeResult(findings=findings, passed_weight=passed, total_weight=checks)
