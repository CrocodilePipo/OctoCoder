from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from octocoder.evals.models import EvalCase, ExecutionStatus, Usage


@dataclass(frozen=True)
class RunRequest:
    run_id: str
    case: EvalCase
    workspace: Path
    environment: dict[str, str] = field(default_factory=dict)


@dataclass
class RunnerOutput:
    status: ExecutionStatus
    raw_events: list[dict[str, Any] | str] = field(default_factory=list)
    stderr: str = ""
    final_response: str = ""
    duration_ms: int = 0
    provider: str = ""
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    turns: int = 0
    errors: list[str] = field(default_factory=list)


class EvalRunner(Protocol):
    async def run(self, request: RunRequest) -> RunnerOutput: ...
