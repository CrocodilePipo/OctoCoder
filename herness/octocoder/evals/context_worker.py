from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, Awaitable, Callable

from octocoder.config import load_config
from octocoder.evals.events import CHECKPOINT_END, CHECKPOINT_START
from octocoder.evals.models import EvalCase
from octocoder.hooks import HookEngine, load_hooks
from octocoder.noninteractive import NonInteractiveSession
from octocoder.permissions import PermissionMode


SessionFactory = Callable[..., Awaitable[NonInteractiveSession]]


def build_probe_prompt(case: EvalCase, checkpoint_id: str) -> str:
    assert case.context is not None
    fact_ids = [
        fact.id for fact in case.context.facts if checkpoint_id in fact.required_at
    ]
    forbidden_fact_ids = [
        fact.id for fact in case.context.facts if checkpoint_id in fact.forbidden_at
    ]
    instruction_ids = [
        instruction.id
        for instruction in case.context.instructions
        if checkpoint_id in instruction.active_at
    ]
    superseded_instruction_ids = [
        instruction.id
        for instruction in case.context.instructions
        if checkpoint_id in instruction.superseded_at
    ]
    return (
        "Return a bounded JSON context checkpoint only. Do not call tools. "
        f"Wrap it between {CHECKPOINT_START} and {CHECKPOINT_END}. "
        f"Use id={checkpoint_id!r}. Include stage_id, facts for these IDs: "
        f"{fact_ids}; omit stale or injected fact IDs: {forbidden_fact_ids}; "
        f"active_instructions using these IDs: {instruction_ids}; omit superseded "
        f"instruction IDs: {superseded_instruction_ids}; "
        "task_state with required_files, pending_work, known_failures, and next_action; "
        "and tool_pair_complete. Use null or omit unknown facts rather than guessing."
    )


async def run_request(
    request: dict[str, Any],
    *,
    config: Any | None = None,
    hook_engine: HookEngine | None = None,
    session_factory: SessionFactory = NonInteractiveSession.create,
    sink: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    case = EvalCase.model_validate(request["case"])
    if case.context is None:
        raise ValueError("context worker requires a context case")
    config = config or load_config()
    if hook_engine is None:
        hooks = load_hooks(config.raw_hooks)
        hook_engine = HookEngine(hooks) if hooks else None
    sink = sink or (lambda event: None)
    session = await session_factory(
        config,
        PermissionMode(case.execution.permission_mode),
        hook_engine,
        event_sink=sink,
        work_dir=request.get("work_dir"),
    )
    failed = False
    try:
        for stage in case.context.stages:
            for _ in range(stage.repeat):
                if stage.action in {"turn", "pressure"}:
                    result = await session.run_turn(stage.prompt, stage.id)
                    failed = failed or bool(result.errors)
                elif stage.action == "checkpoint":
                    prompt = stage.prompt or build_probe_prompt(case, stage.checkpoint or stage.id)
                    result = await session.run_turn(prompt, stage.id, stage.checkpoint)
                    failed = failed or bool(result.errors)
                elif stage.action == "resume":
                    await session.persist_and_resume(stage.id)
                    prompt = stage.prompt or build_probe_prompt(case, stage.checkpoint or stage.id)
                    result = await session.run_turn(prompt, stage.id, stage.checkpoint)
                    failed = failed or bool(result.errors)
    finally:
        await session.close()
    return 1 if failed else 0


async def _main() -> int:
    request = json.loads(sys.stdin.read())
    run_id = str(request.get("run_id", "context-run"))
    sequence = 0
    started = time.monotonic()

    def emit(event: dict[str, Any]) -> None:
        nonlocal sequence
        payload = dict(event)
        payload.setdefault("sequence", sequence)
        payload.setdefault("run_id", run_id)
        payload.setdefault("timestamp_ms", int((time.monotonic() - started) * 1000))
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        sequence += 1

    try:
        return await run_request(request, sink=emit)
    except Exception as exc:
        emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        emit(
            {
                "type": "result",
                "result": "",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "stop_reason": "framework_error",
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
