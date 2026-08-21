from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from octocoder.evals.artifacts import ArtifactWriter
from octocoder.evals.events import process_events
from octocoder.evals.loader import EvaluationCatalog
from octocoder.evals.models import (
    CaseRunResult,
    CaseScore,
    ComparisonThresholds,
    DimensionScore,
    EvalCase,
    ExecutionMode,
    ExecutionResult,
    ExecutionStatus,
    Finding,
    RunStatus,
    SuiteReport,
)
from octocoder.evals.redaction import SecretRedactor
from octocoder.evals.report import build_suite_report
from octocoder.evals.runners.base import EvalRunner, RunRequest
from octocoder.evals.runners.real import RealRunner
from octocoder.evals.runners.scripted import ScriptedRunner
from octocoder.evals.runners.context_real import RealContextRunner
from octocoder.evals.runners.context_scripted import ScriptedContextRunner
from octocoder.evals.scoring import score_execution
from octocoder.evals.workspace import (
    PreparedWorkspace,
    capture_workspace,
    cleanup_workspace,
    prepare_workspace,
)


@dataclass(frozen=True)
class EvaluationRun:
    report: SuiteReport
    output_directory: Path
    report_json: Path
    report_markdown: Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_status(execution: ExecutionStatus, passed: bool) -> RunStatus:
    if execution == ExecutionStatus.COMPLETED:
        return RunStatus.SUCCESS if passed else RunStatus.EXPECTATION_FAILED
    return RunStatus(execution.value)


def _framework_score(message: str, *, include_context: bool = False) -> CaseScore:
    finding = Finding(code="framework_error", message=message, hard_gate=True)
    dimensions = [
        DimensionScore(name="outcome", findings=[finding]),
        DimensionScore(name="trajectory"),
        DimensionScore(name="efficiency"),
        DimensionScore(name="safety"),
        DimensionScore(name="reliability", findings=[finding]),
    ]
    if include_context:
        dimensions.append(DimensionScore(name="context", findings=[finding]))
    return CaseScore(
        passed=False,
        dimensions=dimensions,
        findings=[finding],
    )


class EvaluationOrchestrator:
    def __init__(
        self,
        catalog: EvaluationCatalog,
        output_root: Path,
        redactor: SecretRedactor | None = None,
        scripted_runner: EvalRunner | None = None,
        real_runner: EvalRunner | None = None,
        context_scripted_runner: EvalRunner | None = None,
        context_real_runner: EvalRunner | None = None,
    ) -> None:
        self.catalog = catalog
        self.output_root = output_root.resolve()
        self.redactor = redactor or SecretRedactor()
        self.scripted_runner = scripted_runner or ScriptedRunner()
        self.real_runner = real_runner or RealRunner()
        self.context_scripted_runner = context_scripted_runner or ScriptedContextRunner()
        self.context_real_runner = context_real_runner or RealContextRunner()

    def _select_runner(self, case: EvalCase) -> EvalRunner:
        if case.context is not None:
            return (
                self.context_scripted_runner
                if case.execution.mode == ExecutionMode.SCRIPTED
                else self.context_real_runner
            )
        return (
            self.scripted_runner
            if case.execution.mode == ExecutionMode.SCRIPTED
            else self.real_runner
        )

    async def run(
        self,
        cases: list[EvalCase],
        *,
        suite_id: str,
        repeat: int = 1,
        thresholds: ComparisonThresholds | None = None,
        execution_override: ExecutionMode | None = None,
        keep_workspace: bool = False,
    ) -> EvaluationRun:
        batch_id = f"{suite_id}-{_utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        batch_directory = self.output_root / batch_id
        batch_directory.mkdir(parents=True, exist_ok=False)
        writer = ArtifactWriter(batch_directory, self.redactor)
        workspace_root = batch_directory / ".workspaces"
        results: list[CaseRunResult] = []
        for repetition in range(repeat):
            for case in cases:
                selected_case = self._override_execution(case, execution_override)
                result = await self._run_case(
                    selected_case,
                    repetition=repetition,
                    workspace_root=workspace_root,
                    writer=writer,
                    keep_workspace=keep_workspace,
                )
                results.append(result)
        report = build_suite_report(suite_id, results, thresholds)
        report_json, report_markdown = writer.write_suite(batch_directory, report)
        if workspace_root.exists() and not any(workspace_root.iterdir()):
            workspace_root.rmdir()
        return EvaluationRun(report, batch_directory, report_json, report_markdown)

    @staticmethod
    def _override_execution(case: EvalCase, mode: ExecutionMode | None) -> EvalCase:
        if mode is None or mode == case.execution.mode:
            return case
        data = case.model_dump(mode="json")
        data["execution"]["mode"] = mode.value
        if mode == ExecutionMode.REAL:
            data["script"] = None
        return EvalCase.model_validate(data)

    async def _run_case(
        self,
        case: EvalCase,
        *,
        repetition: int,
        workspace_root: Path,
        writer: ArtifactWriter,
        keep_workspace: bool,
    ) -> CaseRunResult:
        run_id = f"{case.id}-r{repetition + 1}-{uuid.uuid4().hex[:8]}"
        started = _utc_now()
        prepared: PreparedWorkspace | None = None
        try:
            prepared = prepare_workspace(
                self.catalog.fixtures_root / case.fixture, workspace_root, run_id
            )
            runner = self._select_runner(case)
            output = await runner.run(RunRequest(run_id, case, prepared.path))
            processed = process_events(
                output.raw_events,
                workspace=prepared.path,
                run_id=run_id,
                redactor=self.redactor,
                context=case.context,
            )
            snapshot = capture_workspace(prepared)
            execution = ExecutionResult(
                run_id=run_id,
                case_id=case.id,
                mode=case.execution.mode,
                status=output.status,
                started_at=started.isoformat(),
                duration_ms=output.duration_ms,
                provider=output.provider,
                model=output.model,
                final_response=output.final_response,
                errors=output.errors,
                usage=output.usage,
                raw_events=processed.raw_events,
                events=processed.events,
                trajectory=processed.trajectory,
                workspace_diff=snapshot,
                stderr=output.stderr,
                turns=output.turns,
                malformed_event_count=processed.malformed_count,
                unpaired_event_count=processed.unpaired_count,
                context_events=processed.context_events,
                context_checkpoints=processed.context_checkpoints,
            )
            verdict = await score_execution(
                case, execution, prepared.path, processed.findings, self.redactor
            )
            result = CaseRunResult(
                status=_run_status(execution.status, verdict.passed),
                execution=execution,
                verdict=verdict,
                artifact_path=run_id,
            )
        except Exception as exc:
            message = self.redactor.redact_text(str(exc))
            execution = ExecutionResult(
                run_id=run_id,
                case_id=case.id,
                mode=case.execution.mode,
                status=ExecutionStatus.FRAMEWORK_FAILED,
                started_at=started.isoformat(),
                duration_ms=max(0, int((_utc_now() - started).total_seconds() * 1000)),
                errors=[message],
            )
            result = CaseRunResult(
                status=RunStatus.FRAMEWORK_FAILED,
                execution=execution,
                verdict=_framework_score(message, include_context=case.context is not None),
                artifact_path=run_id,
            )
        writer.write_case(case, result)
        if prepared is not None and not keep_workspace:
            cleanup_workspace(prepared)
        return result
