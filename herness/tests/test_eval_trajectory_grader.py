from __future__ import annotations

from octocoder.evals.graders.trajectory import grade_trajectory, matches_argument
from octocoder.evals.models import ArgumentConstraint, ToolTrace, TrajectoryExpectation


def trace(tool: str, sequence: int, args=None, *, status="success", signature="") -> ToolTrace:
    return ToolTrace(
        sequence=sequence,
        tool=tool,
        arguments=args or {},
        result_status=status,
        signature=signature or f"{tool}-{sequence}",
    )


def test_required_arguments_and_subsequence_pass() -> None:
    expected = TrajectoryExpectation.model_validate(
        {
            "match": "subsequence",
            "required": [
                {
                    "tool": "write_file",
                    "arguments": [{"path": "path", "operator": "glob", "value": "src/*.py"}],
                }
            ],
            "order": ["read_file", "write_file"],
        }
    )
    result = grade_trajectory(
        expected,
        [trace("read_file", 0), trace("search", 1), trace("write_file", 2, {"path": "src/app.py"})],
    )
    assert result.passed_weight == result.total_weight == 2
    assert result.findings == []


def test_forbidden_and_exact_order_are_hard_failures() -> None:
    expected = TrajectoryExpectation.model_validate(
        {"match": "exact", "forbidden": [{"tool": "bash"}], "order": ["read_file"]}
    )
    result = grade_trajectory(expected, [trace("bash", 0), trace("read_file", 1)])
    assert result.passed_weight == 0
    assert result.total_weight == 2
    assert {finding.code for finding in result.findings} == {
        "forbidden_tool_used",
        "tool_order_mismatch",
    }
    assert all(finding.hard_gate for finding in result.findings)


def test_call_limits_and_repetition_are_scored() -> None:
    expected = TrajectoryExpectation.model_validate(
        {"max_total_calls": 1, "max_failed_calls": 0, "max_repeated_identical_calls": 1}
    )
    result = grade_trajectory(
        expected,
        [trace("read", 0, status="error", signature="same"), trace("read", 1, signature="same")],
    )
    assert result.passed_weight == 0
    assert result.total_weight == 3
    assert len(result.findings) == 3


def test_all_argument_operators_support_dotted_paths() -> None:
    arguments = {"target": {"path": "src/app.py", "flags": ["safe"]}}
    checks = [
        {"path": "target.path", "operator": "equals", "value": "src/app.py"},
        {"path": "target.path", "operator": "contains", "value": "app"},
        {"path": "target.path", "operator": "matches", "value": r"src/.+\.py"},
        {"path": "target.path", "operator": "glob", "value": "src/*.py"},
        {"path": "target.flags.0", "operator": "exists"},
    ]
    assert all(matches_argument(arguments, ArgumentConstraint.model_validate(check)) for check in checks)
