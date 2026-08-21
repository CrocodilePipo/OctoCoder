from __future__ import annotations

from octocoder.evals.models import ContextEventType, ExecutionStatus
from octocoder.evals.runners.base import RunRequest, RunnerOutput
from octocoder.evals.runners.scripted import ScriptedRunner


class ScriptedContextRunner:
    async def run(self, request: RunRequest) -> RunnerOutput:
        context = request.case.context
        script = request.case.script
        if context is None or script is None:
            return RunnerOutput(
                status=ExecutionStatus.FRAMEWORK_FAILED,
                errors=["Scripted context runner requires context and script definitions"],
            )

        by_stage: dict[str, list[dict]] = {}
        unscoped: list[dict] = []
        for event in script.events:
            copy = dict(event)
            stage_id = str(copy.get("stage_id", ""))
            if stage_id:
                by_stage.setdefault(stage_id, []).append(copy)
            else:
                unscoped.append(copy)

        raw_events: list[dict] = []
        last_boundary = ""
        turn = 0
        for stage in context.stages:
            for iteration in range(stage.repeat):
                if stage.action in {"turn", "pressure"}:
                    turn += 1
                stage_events = by_stage.get(stage.id, [])
                for source in stage_events:
                    event = dict(source)
                    event["stage_id"] = stage.id
                    event.setdefault("checkpoint_id", stage.checkpoint)
                    event["stage_iteration"] = iteration + 1
                    event.setdefault("turn", turn)
                    event["sequence"] = len(raw_events)
                    raw_events.append(event)
                    if (
                        event.get("type") == "context"
                        and event.get("event_type")
                        == ContextEventType.COMPACT_COMPLETED.value
                    ):
                        last_boundary = str(event.get("boundary_id", ""))
                    if len(raw_events) > request.case.limits.max_context_events:
                        return RunnerOutput(
                            status=ExecutionStatus.FRAMEWORK_FAILED,
                            raw_events=raw_events,
                            errors=["Context event limit exceeded"],
                            turns=turn,
                        )
                if stage.action == "resume" and not any(
                    event.get("type") == "context"
                    and event.get("event_type") == ContextEventType.SESSION_RESUMED.value
                    for event in stage_events
                ):
                    raw_events.append(
                        {
                            "type": "context",
                            "event_type": ContextEventType.SESSION_RESUMED.value,
                            "stage_id": stage.id,
                            "checkpoint_id": stage.checkpoint,
                            "boundary_id": last_boundary,
                            "status": "completed",
                            "turn": turn,
                            "sequence": len(raw_events),
                        }
                    )

        for source in unscoped:
            event = dict(source)
            event.setdefault("turn", turn)
            event["sequence"] = len(raw_events)
            raw_events.append(event)

        base = await ScriptedRunner().run(request)
        base.raw_events = raw_events
        base.turns = max(base.turns, turn)
        if script.duration_ms > int(request.case.limits.timeout_seconds * 1000):
            base.status = ExecutionStatus.TIMEOUT
            base.errors = ["Evaluation timed out"]
        return base
