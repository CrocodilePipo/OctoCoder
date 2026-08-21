from __future__ import annotations

import fnmatch
import re
from typing import Any

from octocoder.evals.models import ArgumentConstraint, ArgumentOperator


MAX_REGEX_LENGTH = 500
MAX_EVIDENCE_CHARS = 500


def get_dotted(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    if not path:
        return True, current
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def matches_value(
    actual: Any,
    operator: ArgumentOperator,
    expected: Any = None,
    *,
    exists: bool = True,
) -> bool:
    if operator == ArgumentOperator.EXISTS:
        expected_exists = True if expected is None else bool(expected)
        return exists == expected_exists
    if not exists:
        return False
    if operator == ArgumentOperator.EQUALS:
        return actual == expected
    if operator == ArgumentOperator.CONTAINS:
        if isinstance(actual, (list, tuple, set, dict)):
            return expected in actual
        return str(expected) in str(actual)
    if operator == ArgumentOperator.GLOB:
        return fnmatch.fnmatchcase(str(actual), str(expected))
    pattern = str(expected)
    if len(pattern) > MAX_REGEX_LENGTH:
        return False
    try:
        return re.search(pattern, str(actual)) is not None
    except re.error:
        return False


def matches_argument(arguments: dict[str, Any], constraint: ArgumentConstraint) -> bool:
    exists, actual = get_dotted(arguments, constraint.path)
    return matches_value(
        actual,
        constraint.operator,
        constraint.value,
        exists=exists,
    )


def bounded_evidence(value: Any) -> Any:
    if isinstance(value, str):
        return value[:MAX_EVIDENCE_CHARS]
    if isinstance(value, list):
        return [bounded_evidence(item) for item in value[:50]]
    if isinstance(value, dict):
        return {
            str(key): bounded_evidence(item)
            for key, item in list(value.items())[:50]
        }
    return value
