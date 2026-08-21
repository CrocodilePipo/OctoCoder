from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from octocoder.evals.models import DimensionScore, EvalCase, ExecutionResult, Finding
from octocoder.evals.redaction import SecretRedactor


@dataclass
class GradeResult:
    findings: list[Finding] = field(default_factory=list)
    passed_weight: float = 0
    total_weight: float = 0

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "error" for finding in self.findings)


@dataclass(frozen=True)
class GradeContext:
    case: EvalCase
    execution: ExecutionResult
    workspace: Path
    redactor: SecretRedactor


class EvalGrader(Protocol):
    async def grade(self, context: GradeContext) -> DimensionScore: ...


class GraderRegistry:
    def __init__(self) -> None:
        self._graders: list[EvalGrader] = []

    def register(self, grader: EvalGrader) -> None:
        self._graders.append(grader)

    @property
    def graders(self) -> tuple[EvalGrader, ...]:
        return tuple(self._graders)
