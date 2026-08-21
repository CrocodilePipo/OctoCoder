from __future__ import annotations

import pytest
from pydantic import ValidationError

from octocoder.evals.models import EvalCase, EvalSuite


def valid_case(**overrides):
    data = {
        "id": "edit-readme",
        "title": "Edit README",
        "prompt": "Add a heading",
        "fixture": "tiny-project",
        "execution": {"mode": "scripted"},
        "script": {"events": [], "effects": []},
        "expected": {
            "outcome": [{"id": "readme", "type": "file_exists", "path": "README.md"}]
        },
    }
    data.update(overrides)
    return data


def test_case_schema_accepts_scripted_case() -> None:
    case = EvalCase.model_validate(valid_case())
    assert case.schema_version == 1
    assert case.expected.outcome[0].hard_gate is True


def test_case_schema_rejects_unsupported_version() -> None:
    with pytest.raises(ValidationError, match="schema_version"):
        EvalCase.model_validate(valid_case(schema_version=2))


@pytest.mark.parametrize("fixture", ["../outside", "C:\\outside", "/outside"])
def test_case_schema_rejects_unsafe_fixture(fixture: str) -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate(valid_case(fixture=fixture))


def test_case_schema_rejects_real_script() -> None:
    with pytest.raises(ValidationError, match="real execution cannot define script"):
        EvalCase.model_validate(valid_case(execution={"mode": "real"}))


def test_case_schema_rejects_duplicate_check_ids() -> None:
    data = valid_case()
    data["expected"]["outcome"].append(
        {"id": "readme", "type": "file_absent", "path": "secret.txt"}
    )
    with pytest.raises(ValidationError, match="unique"):
        EvalCase.model_validate(data)


def test_script_effect_rejects_parent_traversal() -> None:
    data = valid_case()
    data["script"]["effects"] = [{"type": "write", "path": "../outside", "content": "bad"}]
    with pytest.raises(ValidationError, match="traversal"):
        EvalCase.model_validate(data)


def test_suite_requires_a_selection() -> None:
    with pytest.raises(ValidationError, match="select"):
        EvalSuite.model_validate({"id": "empty"})
