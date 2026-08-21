from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from octocoder.evals.models import ExecutionStatus, Usage
from octocoder.evals.runners.base import RunRequest, RunnerOutput
from octocoder.evals.runners.real import REQUIRED_ENV, RealRunner


class RealContextRunner:
    def __init__(self, module: str = "octocoder.evals.context_worker") -> None:
        self.module = module

    async def run(self, request: RunRequest) -> RunnerOutput:
        if request.case.context is None:
            return RunnerOutput(
                status=ExecutionStatus.FRAMEWORK_FAILED,
                errors=["Real context runner requires a context case"],
            )
        env_names = REQUIRED_ENV.union(request.case.execution.env_allowlist)
        allowed = {item.upper() for item in env_names}
        env = {
            name: value
            for name, value in os.environ.items()
            if name.upper() in allowed
        }
        env.update(request.environment)
        env["OCTOCODER_EVAL_RUN_ID"] = request.run_id
        env.setdefault("OCTOCODER_CONFIG_CWD", str(Path.cwd()))
        payload = json.dumps(
            {
                "run_id": request.run_id,
                "work_dir": str(request.workspace),
                "case": request.case.model_dump(mode="json"),
            },
            ensure_ascii=False,
        ).encode("utf-8")
        process_options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                self.module,
                cwd=request.workspace,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **process_options,
            )
        except OSError as exc:
            return RunnerOutput(
                status=ExecutionStatus.FRAMEWORK_FAILED,
                errors=[str(exc)],
            )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.write(payload)
        await process.stdin.drain()
        process.stdin.close()
        stdout_task = asyncio.create_task(process.stdout.read())
        stderr_task = asyncio.create_task(process.stderr.read())
        try:
            await asyncio.wait_for(
                process.wait(), timeout=request.case.limits.timeout_seconds
            )
        except asyncio.TimeoutError:
            await RealRunner._terminate_process_tree(process)
            stdout_bytes, stderr_bytes = await asyncio.gather(stdout_task, stderr_task)
            return RunnerOutput(
                status=ExecutionStatus.TIMEOUT,
                raw_events=stdout_bytes.decode("utf-8", errors="replace").splitlines(),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=int((time.monotonic() - start) * 1000),
                errors=["Evaluation timed out"],
            )

        stdout_bytes, stderr_bytes = await asyncio.gather(stdout_task, stderr_task)
        lines = stdout_bytes.decode("utf-8", errors="replace").splitlines()
        context_event_count = 0
        total_turns = 0
        final: dict[str, object] = {}
        for line in lines:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "context":
                context_event_count += 1
            if event.get("type") == "result":
                final = event
                total_turns += int(event.get("num_turns", 0) or 0)
        if context_event_count > request.case.limits.max_context_events:
            return RunnerOutput(
                status=ExecutionStatus.FRAMEWORK_FAILED,
                raw_events=lines[: request.case.limits.max_context_events],
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                duration_ms=int((time.monotonic() - start) * 1000),
                errors=["Context event limit exceeded"],
            )
        if process.returncode == 0:
            status = ExecutionStatus.COMPLETED
        elif process.returncode == 1:
            status = ExecutionStatus.AGENT_FAILED
        else:
            status = ExecutionStatus.FRAMEWORK_FAILED
        usage = final.get("usage", {})
        return RunnerOutput(
            status=status,
            raw_events=lines,
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            final_response=str(final.get("result", "")),
            duration_ms=int((time.monotonic() - start) * 1000),
            provider=str(final.get("provider", "")),
            model=str(final.get("model", "")),
            usage=Usage.model_validate(usage or {}),
            turns=total_turns,
            errors=(
                []
                if process.returncode == 0
                else [f"Context worker exited with code {process.returncode}"]
            ),
        )
