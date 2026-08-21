from __future__ import annotations

import asyncio
from pathlib import Path

from octocoder.evals.models import ExecutionStatus, Usage
from octocoder.evals.runners.base import RunRequest, RunnerOutput
from octocoder.evals.workspace import WorkspaceError, resolve_workspace_path


class ScriptedRunner:
    async def run(self, request: RunRequest) -> RunnerOutput:
        script = request.case.script
        if script is None:
            return RunnerOutput(
                status=ExecutionStatus.FRAMEWORK_FAILED,
                errors=["Scripted runner requires a script"],
            )
        for effect in script.effects:
            path = resolve_workspace_path(request.workspace, effect.path)
            if effect.type == "write":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(effect.content, encoding="utf-8")
            elif path.exists():
                if path.is_dir():
                    raise WorkspaceError(f"Scripted delete only supports files: {effect.path}")
                path.unlink()
        if script.status == ExecutionStatus.TIMEOUT:
            await asyncio.sleep(0)
        result_event = next(
            (event for event in reversed(script.events) if event.get("type") == "result"),
            {},
        )
        usage = result_event.get("usage", {})
        return RunnerOutput(
            status=script.status,
            raw_events=[dict(event) for event in script.events],
            stderr=script.stderr,
            final_response=script.final_response or str(result_event.get("result", "")),
            duration_ms=script.duration_ms,
            provider=str(result_event.get("provider", "scripted")),
            model=str(result_event.get("model", "scripted")),
            usage=Usage.model_validate(usage or {}),
            turns=int(result_event.get("num_turns", 0)),
            errors=[] if script.status == ExecutionStatus.COMPLETED else [script.stderr or script.status.value],
        )
