from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from octocoder.evals.models import ExecutionStatus, Usage
from octocoder.evals.runners.base import RunRequest, RunnerOutput


REQUIRED_ENV = {
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "TMP",
    "TEMP",
    "PYTHONPATH",
}


class RealRunner:
    def __init__(self, module: str = "octocoder") -> None:
        self.module = module

    async def run(self, request: RunRequest) -> RunnerOutput:
        env_names = REQUIRED_ENV.union(request.case.execution.env_allowlist)
        env = {name: value for name, value in os.environ.items() if name.upper() in {item.upper() for item in env_names}}
        env.update(request.environment)
        env["OCTOCODER_EVAL_RUN_ID"] = request.run_id
        env.setdefault("OCTOCODER_CONFIG_CWD", str(Path.cwd()))
        command = [
            sys.executable,
            "-m",
            self.module,
            "-p",
            request.case.prompt,
            "--mode",
            request.case.execution.permission_mode,
            "--output-format",
            "stream-json",
        ]
        start = time.monotonic()
        process_options = (
            {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=request.workspace,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **process_options,
            )
        except OSError as exc:
            return RunnerOutput(status=ExecutionStatus.FRAMEWORK_FAILED, errors=[str(exc)])
        assert process.stdout is not None and process.stderr is not None
        stdout_task = asyncio.create_task(process.stdout.read())
        stderr_task = asyncio.create_task(process.stderr.read())
        try:
            await asyncio.wait_for(process.wait(), timeout=request.case.limits.timeout_seconds)
        except asyncio.TimeoutError:
            await self._terminate_process_tree(process)
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
        final: dict = {}
        for line in reversed(lines):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if candidate.get("type") == "result":
                final = candidate
                break
        status = ExecutionStatus.COMPLETED if process.returncode == 0 else ExecutionStatus.AGENT_FAILED
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
            turns=int(final.get("num_turns", 0)),
            errors=[] if process.returncode == 0 else [f"OctoCoder exited with code {process.returncode}"],
        )

    @staticmethod
    async def _terminate_process_tree(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if os.name == "nt":
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await killer.wait()
            if process.returncode is None:
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await process.wait()
