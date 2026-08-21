from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from octocoder.evals.models import EvalCase, EvalSuite


class EvaluationLoadError(ValueError):
    """Raised when an evaluation catalog is malformed."""


@dataclass(frozen=True)
class EvaluationCatalog:
    root: Path
    cases: dict[str, EvalCase]
    suites: dict[str, EvalSuite]
    case_paths: dict[str, Path]
    suite_paths: dict[str, Path]

    @property
    def fixtures_root(self) -> Path:
        return self.root / "fixtures"


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EvaluationLoadError(f"{path}: {exc}") from exc


def load_case(path: Path) -> EvalCase:
    try:
        case = EvalCase.model_validate(_load_yaml(path))
        _validate_context_references(case, path)
        return case
    except ValidationError as exc:
        raise EvaluationLoadError(f"Invalid evaluation case {path}:\n{exc}") from exc


def _validate_context_references(case: EvalCase, source: Path) -> None:
    context = case.context
    if context is None:
        return

    if len(context.stages) > case.limits.max_stages:
        raise EvaluationLoadError(
            f"{source}: context defines {len(context.stages)} stages, "
            f"limit is {case.limits.max_stages}"
        )
    turn_count = sum(
        stage.repeat for stage in context.stages if stage.action in {"turn", "pressure"}
    )
    if turn_count > case.limits.max_turns:
        raise EvaluationLoadError(
            f"{source}: context defines {turn_count} turns, limit is {case.limits.max_turns}"
        )
    if case.script is not None and len(case.script.events) > case.limits.max_context_events:
        raise EvaluationLoadError(
            f"{source}: script defines {len(case.script.events)} events, "
            f"limit is {case.limits.max_context_events}"
        )

    checkpoints = {stage.checkpoint for stage in context.stages if stage.checkpoint}
    if not checkpoints:
        raise EvaluationLoadError(f"{source}: context case requires an observable checkpoint")

    def assert_checkpoints(label: str, references: list[str]) -> None:
        missing = sorted(set(references) - checkpoints)
        if missing:
            raise EvaluationLoadError(
                f"{source}: {label} references unknown checkpoints: {', '.join(missing)}"
            )

    for fact in context.facts:
        assert_checkpoints(f"fact {fact.id!r}", fact.required_at + fact.forbidden_at)
    for instruction in context.instructions:
        assert_checkpoints(
            f"instruction {instruction.id!r}",
            instruction.active_at + instruction.superseded_at,
        )
    for state in context.states:
        assert_checkpoints("state expectation", [state.checkpoint])

    fact_ids = {fact.id for fact in context.facts}
    instruction_ids = {instruction.id for instruction in context.instructions}
    for resume in context.resumes:
        assert_checkpoints(
            "resume expectation", [resume.before_checkpoint, resume.after_checkpoint]
        )
        missing_facts = sorted(set(resume.equivalent_fact_ids) - fact_ids)
        missing_instructions = sorted(
            set(resume.equivalent_instruction_ids) - instruction_ids
        )
        if missing_facts:
            raise EvaluationLoadError(
                f"{source}: resume references unknown facts: {', '.join(missing_facts)}"
            )
        if missing_instructions:
            raise EvaluationLoadError(
                f"{source}: resume references unknown instructions: "
                f"{', '.join(missing_instructions)}"
            )


def load_suite(path: Path) -> EvalSuite:
    try:
        return EvalSuite.model_validate(_load_yaml(path))
    except ValidationError as exc:
        raise EvaluationLoadError(f"Invalid evaluation suite {path}:\n{exc}") from exc


def _assert_fixture(root: Path, case: EvalCase, source: Path) -> None:
    fixtures_root = (root / "fixtures").resolve()
    fixture = (fixtures_root / case.fixture).resolve()
    if not fixture.is_relative_to(fixtures_root):
        raise EvaluationLoadError(f"{source}: fixture escapes fixtures root")
    if not fixture.is_dir():
        raise EvaluationLoadError(f"{source}: fixture does not exist: {case.fixture}")


def load_catalog(root: Path) -> EvaluationCatalog:
    root = root.resolve()
    cases: dict[str, EvalCase] = {}
    suites: dict[str, EvalSuite] = {}
    case_paths: dict[str, Path] = {}
    suite_paths: dict[str, Path] = {}

    for path in sorted((root / "cases").rglob("*.yaml")):
        case = load_case(path)
        if case.id in cases:
            raise EvaluationLoadError(f"Duplicate case ID {case.id!r}: {case_paths[case.id]} and {path}")
        _assert_fixture(root, case, path)
        cases[case.id] = case
        case_paths[case.id] = path

    for path in sorted((root / "suites").rglob("*.yaml")):
        suite = load_suite(path)
        if suite.id in suites:
            raise EvaluationLoadError(f"Duplicate suite ID {suite.id!r}: {suite_paths[suite.id]} and {path}")
        missing = sorted(set(suite.cases) - cases.keys())
        if missing:
            raise EvaluationLoadError(f"{path}: unknown cases: {', '.join(missing)}")
        suites[suite.id] = suite
        suite_paths[suite.id] = path

    return EvaluationCatalog(root, cases, suites, case_paths, suite_paths)


def resolve_suite(catalog: EvaluationCatalog, suite: EvalSuite) -> list[EvalCase]:
    selected = set(suite.cases)
    include = set(suite.include_tags)
    exclude = set(suite.exclude_tags)
    for case in catalog.cases.values():
        tags = set(case.tags)
        if include and include.intersection(tags):
            selected.add(case.id)
    return [
        catalog.cases[case_id]
        for case_id in sorted(selected)
        if not exclude.intersection(catalog.cases[case_id].tags)
    ]


def select_cases(
    catalog: EvaluationCatalog,
    *,
    case_id: str | None = None,
    suite_id: str | None = None,
    all_cases: bool = False,
) -> tuple[list[EvalCase], EvalSuite | None]:
    choices = sum(bool(value) for value in (case_id, suite_id, all_cases))
    if choices != 1:
        raise EvaluationLoadError("select exactly one of case_id, suite_id, or all_cases")
    if case_id:
        if case_id not in catalog.cases:
            raise EvaluationLoadError(f"Unknown case ID: {case_id}")
        return [catalog.cases[case_id]], None
    if suite_id:
        if suite_id not in catalog.suites:
            raise EvaluationLoadError(f"Unknown suite ID: {suite_id}")
        suite = catalog.suites[suite_id]
        return resolve_suite(catalog, suite), suite
    return [catalog.cases[key] for key in sorted(catalog.cases)], None
