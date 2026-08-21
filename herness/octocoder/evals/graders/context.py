from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from octocoder.evals.graders.base import GradeContext
from octocoder.evals.graders.matching import bounded_evidence, get_dotted, matches_value
from octocoder.evals.models import (
    ContextCheckpoint,
    ContextEvent,
    ContextEventType,
    ContextExpectation,
    ContextMetrics,
    ContextSubscore,
    DimensionScore,
    EvalEvent,
    Finding,
)


SIMILARITY_CHECKS = {
    "retention",
    "instruction_adherence",
    "continuity",
    "resume_consistency",
}


@dataclass
class _Checks:
    name: str
    passed: int = 0
    total: int = 0
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        valid: bool,
        *,
        code: str,
        message: str,
        hard_gate: bool,
        evidence: dict[str, Any],
    ) -> None:
        self.total += 1
        if valid:
            self.passed += 1
            return
        self.findings.append(
            Finding(
                code=code,
                message=message,
                hard_gate=hard_gate,
                evidence=bounded_evidence(evidence),
            )
        )

    @property
    def rate(self) -> float | None:
        return None if self.total == 0 else self.passed / self.total

    def subscore(self) -> ContextSubscore | None:
        rate = self.rate
        if rate is None:
            return None
        return ContextSubscore(
            name=self.name,
            checks_passed=self.passed,
            checks_total=self.total,
            similarity=rate if self.name in SIMILARITY_CHECKS else None,
            findings=self.findings,
        )


def _checkpoint_map(
    checkpoints: list[ContextCheckpoint],
) -> dict[str, ContextCheckpoint]:
    return {checkpoint.id: checkpoint for checkpoint in checkpoints}


def _instruction_present(instruction: Any, checkpoint: ContextCheckpoint) -> bool:
    values = checkpoint.active_instructions
    if instruction.id in values:
        return True
    if instruction.text is not None:
        return any(
            instruction.text == value or instruction.text in value for value in values
        )
    pattern = str(instruction.pattern)
    if len(pattern) > 500:
        return False
    try:
        return any(re.search(pattern, value) is not None for value in values)
    except re.error:
        return False


def _contains_expected(actual: Any, expected: str) -> bool:
    if isinstance(actual, (list, tuple, set)):
        return expected in actual
    return expected in str(actual)


def _event_contains_value(
    events: list[EvalEvent], stage_id: str, value: Any
) -> bool:
    if value is None:
        return False
    needle = str(value)
    for event in events:
        if event.event_type != "tool_use":
            continue
        if stage_id and str(event.payload.get("stage_id", "")) != stage_id:
            continue
        rendered = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
        if needle in rendered:
            return True
    return False


def build_context_metrics(
    expected: ContextExpectation,
    events: list[ContextEvent],
    checkpoints: list[ContextCheckpoint],
    execution_events: list[EvalEvent] | None = None,
) -> ContextMetrics:
    execution_events = execution_events or []
    by_checkpoint = _checkpoint_map(checkpoints)
    retention = _Checks("retention")
    adherence = _Checks("instruction_adherence")
    continuity = _Checks("continuity")
    resume = _Checks("resume_consistency")
    token = _Checks("token_accuracy")
    compression = _Checks("compression_efficiency")
    contamination = _Checks("contamination")

    for fact in expected.facts:
        for checkpoint_id in fact.required_at:
            checkpoint = by_checkpoint.get(checkpoint_id)
            exists = checkpoint is not None and fact.id in checkpoint.facts
            actual = checkpoint.facts.get(fact.id) if checkpoint is not None else None
            valid = matches_value(actual, fact.operator, fact.value, exists=exists)
            retention.add(
                valid,
                code="context.fact_retention",
                message=f"Fact {fact.id!r} was not retained at {checkpoint_id!r}",
                hard_gate=fact.hard_gate,
                evidence={
                    "checkpoint_id": checkpoint_id,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                    "fact_id": fact.id,
                    "source": fact.source,
                    "expected": fact.value,
                    "actual": actual,
                },
            )
        for checkpoint_id in fact.forbidden_at:
            checkpoint = by_checkpoint.get(checkpoint_id)
            exists = checkpoint is not None and fact.id in checkpoint.facts
            actual = checkpoint.facts.get(fact.id) if checkpoint is not None else None
            present = matches_value(actual, fact.operator, fact.value, exists=exists)
            if checkpoint is not None:
                present = present or (
                    fact.value is not None and str(fact.value) in checkpoint.answer
                )
                present = present or _event_contains_value(
                    execution_events, checkpoint.stage_id, fact.value
                )
            contamination.add(
                not present,
                code="context.stale_fact",
                message=f"Forbidden fact {fact.id!r} survived at {checkpoint_id!r}",
                hard_gate=fact.hard_gate,
                evidence={
                    "checkpoint_id": checkpoint_id,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                    "fact_id": fact.id,
                    "forbidden": fact.value,
                    "actual": actual,
                },
            )

    for instruction in expected.instructions:
        for checkpoint_id in instruction.active_at:
            checkpoint = by_checkpoint.get(checkpoint_id)
            valid = checkpoint is not None and _instruction_present(instruction, checkpoint)
            adherence.add(
                valid,
                code="context.active_instruction",
                message=f"Active instruction {instruction.id!r} is missing at {checkpoint_id!r}",
                hard_gate=instruction.hard_gate,
                evidence={
                    "checkpoint_id": checkpoint_id,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                    "instruction_id": instruction.id,
                    "priority": instruction.priority,
                    "actual": checkpoint.active_instructions if checkpoint else [],
                },
            )
        for checkpoint_id in instruction.superseded_at:
            checkpoint = by_checkpoint.get(checkpoint_id)
            present = checkpoint is not None and _instruction_present(instruction, checkpoint)
            adherence.add(
                not present,
                code="context.superseded_instruction",
                message=f"Superseded instruction {instruction.id!r} remained active at {checkpoint_id!r}",
                hard_gate=instruction.hard_gate,
                evidence={
                    "checkpoint_id": checkpoint_id,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                    "instruction_id": instruction.id,
                    "priority": instruction.priority,
                },
            )
            contamination.add(
                not present,
                code="context.instruction_contamination",
                message=f"Superseded instruction {instruction.id!r} contaminated {checkpoint_id!r}",
                hard_gate=instruction.hard_gate,
                evidence={"checkpoint_id": checkpoint_id, "instruction_id": instruction.id},
            )

    for state in expected.states:
        checkpoint = by_checkpoint.get(state.checkpoint)
        task_state = checkpoint.task_state if checkpoint is not None else {}
        actual_files = task_state.get(
            "required_files", task_state.get("target_files", task_state.get("files", []))
        )
        normalized_files = {
            str(path).replace("\\", "/") for path in actual_files
        } if isinstance(actual_files, list) else set()
        for required_file in state.required_files:
            continuity.add(
                required_file.replace("\\", "/") in normalized_files,
                code="context.required_file",
                message=f"Required file {required_file!r} is missing at {state.checkpoint!r}",
                hard_gate=state.hard_gate,
                evidence={
                    "checkpoint_id": state.checkpoint,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                    "expected": required_file,
                    "actual": sorted(normalized_files),
                },
            )
        for key, expected_values in (
            ("pending_work", state.pending_work),
            ("known_failures", state.known_failures),
        ):
            actual = task_state.get(key, [])
            for expected_value in expected_values:
                continuity.add(
                    _contains_expected(actual, expected_value),
                    code=f"context.{key}",
                    message=f"{key} item {expected_value!r} is missing at {state.checkpoint!r}",
                    hard_gate=state.hard_gate,
                    evidence={
                        "checkpoint_id": state.checkpoint,
                        "stage_id": checkpoint.stage_id if checkpoint else "",
                        "expected": expected_value,
                        "actual": actual,
                    },
                )
        if state.expected_next_action is not None:
            actual = task_state.get("next_action", "")
            continuity.add(
                state.expected_next_action == actual,
                code="context.next_action",
                message=f"Next action diverged at {state.checkpoint!r}",
                hard_gate=state.hard_gate,
                evidence={
                    "checkpoint_id": state.checkpoint,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                    "expected": state.expected_next_action,
                    "actual": actual,
                },
            )
        if state.require_complete_tool_pairs:
            continuity.add(
                checkpoint is not None and checkpoint.tool_pair_complete,
                code="context.tool_pair",
                message=f"Tool-use/tool-result pairing is incomplete at {state.checkpoint!r}",
                hard_gate=state.hard_gate,
                evidence={
                    "checkpoint_id": state.checkpoint,
                    "stage_id": checkpoint.stage_id if checkpoint else "",
                },
            )

    instructions_by_id = {instruction.id: instruction for instruction in expected.instructions}
    for expectation in expected.resumes:
        before = by_checkpoint.get(expectation.before_checkpoint)
        after = by_checkpoint.get(expectation.after_checkpoint)
        if before is None or after is None:
            resume.add(
                False,
                code="context.resume_checkpoint",
                message="Resume comparison checkpoint is missing",
                hard_gate=expectation.hard_gate,
                evidence={
                    "before_checkpoint": expectation.before_checkpoint,
                    "after_checkpoint": expectation.after_checkpoint,
                },
            )
            continue
        for fact_id in expectation.equivalent_fact_ids:
            before_exists = fact_id in before.facts
            after_exists = fact_id in after.facts
            resume.add(
                before_exists and after_exists and before.facts[fact_id] == after.facts[fact_id],
                code="context.resume_fact",
                message=f"Fact {fact_id!r} diverged across resume",
                hard_gate=expectation.hard_gate,
                evidence={
                    "before_checkpoint": before.id,
                    "after_checkpoint": after.id,
                    "fact_id": fact_id,
                    "before": before.facts.get(fact_id),
                    "after": after.facts.get(fact_id),
                },
            )
        for instruction_id in expectation.equivalent_instruction_ids:
            instruction = instructions_by_id[instruction_id]
            resume.add(
                _instruction_present(instruction, before)
                == _instruction_present(instruction, after),
                code="context.resume_instruction",
                message=f"Instruction {instruction_id!r} diverged across resume",
                hard_gate=expectation.hard_gate,
                evidence={
                    "before_checkpoint": before.id,
                    "after_checkpoint": after.id,
                    "instruction_id": instruction_id,
                },
            )
        for path in expectation.equivalent_state_fields:
            before_exists, before_value = get_dotted(before.task_state, path)
            after_exists, after_value = get_dotted(after.task_state, path)
            resume.add(
                before_exists and after_exists and before_value == after_value,
                code="context.resume_state",
                message=f"Task-state field {path!r} diverged across resume",
                hard_gate=expectation.hard_gate,
                evidence={
                    "before_checkpoint": before.id,
                    "after_checkpoint": after.id,
                    "field": path,
                    "before": before_value,
                    "after": after_value,
                },
            )
        if expectation.before_model is not None:
            resume.add(
                before.model == expectation.before_model,
                code="context.resume_before_model",
                message="Model before restart did not match the declared model",
                hard_gate=expectation.hard_gate,
                evidence={
                    "checkpoint_id": before.id,
                    "expected": expectation.before_model,
                    "actual": before.model,
                },
            )
        if expectation.after_model is not None:
            resume.add(
                after.model == expectation.after_model,
                code="context.resume_after_model",
                message="Model after restart did not match the declared model",
                hard_gate=expectation.hard_gate,
                evidence={
                    "checkpoint_id": after.id,
                    "expected": expectation.after_model,
                    "actual": after.model,
                },
            )
        if expectation.require_model_change:
            resume.add(
                bool(before.model and after.model and before.model != after.model),
                code="context.resume_model_change",
                message="Restart did not switch to a different model",
                hard_gate=expectation.hard_gate,
                evidence={
                    "before_checkpoint": before.id,
                    "after_checkpoint": after.id,
                    "before_model": before.model,
                    "after_model": after.model,
                },
            )

    anchors = [
        event
        for event in events
        if event.event_type == ContextEventType.USAGE_ANCHOR
        and event.estimated_tokens is not None
        and event.provider_tokens is not None
        and event.provider_tokens > 0
    ]
    token_errors = [
        abs(event.estimated_tokens - event.provider_tokens)
        for event in anchors
    ]
    if expected.token is not None:
        if expected.token.require_provider_anchor:
            token.add(
                bool(anchors),
                code="context.provider_anchor",
                message="Required provider usage anchor is missing",
                hard_gate=expected.token.hard_gate,
                evidence={"anchor_count": len(anchors)},
            )
        if expected.token.max_absolute_error_tokens is not None:
            for index, error in enumerate(token_errors):
                token.add(
                    error <= expected.token.max_absolute_error_tokens,
                    code="context.token_estimate",
                    message="Token estimate exceeded the declared absolute-error tolerance",
                    hard_gate=expected.token.hard_gate,
                    evidence={
                        "anchor_index": index,
                        "maximum_error_tokens": expected.token.max_absolute_error_tokens,
                        "actual_error_tokens": error,
                    },
                )
        if expected.token.trigger_tolerance_tokens is not None:
            starts = [
                event
                for event in events
                if event.event_type == ContextEventType.COMPACT_STARTED
                and event.estimated_tokens is not None
                and event.threshold_tokens is not None
            ]
            token.add(
                bool(starts),
                code="context.compaction_trigger_missing",
                message="No measurable compaction trigger was observed",
                hard_gate=expected.token.hard_gate,
                evidence={},
            )
            for event in starts:
                offset = event.estimated_tokens - event.threshold_tokens
                token.add(
                    abs(offset) <= expected.token.trigger_tolerance_tokens,
                    code="context.compaction_trigger_drift",
                    message="Compaction trigger occurred outside the declared tolerance",
                    hard_gate=expected.token.hard_gate,
                    evidence={
                        "stage_id": event.stage_id,
                        "sequence": event.sequence,
                        "offset_tokens": offset,
                        "tolerance_tokens": expected.token.trigger_tolerance_tokens,
                    },
                )
        for event in events:
            if event.context_window is None:
                continue
            observed = max(
                value or 0
                for value in (
                    event.estimated_tokens,
                    event.before_tokens,
                    event.after_tokens,
                )
            )
            if observed > event.context_window:
                token.add(
                    False,
                    code="context.overflow",
                    message="Observed context exceeded the declared context window",
                    hard_gate=expected.token.hard_gate,
                    evidence={
                        "stage_id": event.stage_id,
                        "observed_tokens": observed,
                        "context_window": event.context_window,
                    },
                )

    completed = [
        event for event in events if event.event_type == ContextEventType.COMPACT_COMPLETED
    ]
    reclaimed = [
        max(0, (event.before_tokens or 0) - (event.after_tokens or 0))
        for event in completed
        if event.before_tokens is not None and event.after_tokens is not None
    ]
    if expected.compression is not None:
        config = expected.compression
        compression.add(
            len(completed) >= config.min_compactions,
            code="context.compaction_count_min",
            message="Too few compactions were observed",
            hard_gate=config.hard_gate,
            evidence={"minimum": config.min_compactions, "actual": len(completed)},
        )
        if config.max_compactions is not None:
            compression.add(
                len(completed) <= config.max_compactions,
                code="context.compaction_count_max",
                message="Too many compactions were observed",
                hard_gate=config.hard_gate,
                evidence={"maximum": config.max_compactions, "actual": len(completed)},
            )
        reclaimed_total = sum(reclaimed)
        if config.min_reclaimed_tokens is not None:
            compression.add(
                reclaimed_total >= config.min_reclaimed_tokens,
                code="context.reclaimed_tokens",
                message="Compaction reclaimed too few tokens",
                hard_gate=config.hard_gate,
                evidence={"minimum": config.min_reclaimed_tokens, "actual": reclaimed_total},
            )
        after_max = max((event.after_tokens or 0 for event in completed), default=0)
        if config.max_after_tokens is not None:
            compression.add(
                after_max <= config.max_after_tokens,
                code="context.after_tokens",
                message="Compacted context exceeds the declared token limit",
                hard_gate=config.hard_gate,
                evidence={"maximum_tokens": config.max_after_tokens, "actual_tokens": after_max},
            )
        retained_max = max((event.retained_tokens or 0 for event in completed), default=0)
        if config.max_retained_tokens is not None:
            compression.add(
                retained_max <= config.max_retained_tokens,
                code="context.retained_tokens",
                message="Retained tail exceeds the declared token limit",
                hard_gate=config.hard_gate,
                evidence={"maximum": config.max_retained_tokens, "actual": retained_max},
            )

    checks = [
        retention,
        adherence,
        continuity,
        resume,
        token,
        compression,
        contamination,
    ]
    subscores = [subscore for check in checks if (subscore := check.subscore()) is not None]
    return ContextMetrics(
        retention_rate=retention.rate,
        instruction_adherence_rate=adherence.rate,
        continuity_rate=continuity.rate,
        resume_consistency_rate=resume.rate,
        token_error_tokens_mean=mean(token_errors) if token_errors else None,
        token_error_tokens_max=max(token_errors) if token_errors else None,
        compaction_before_tokens_total=sum(event.before_tokens or 0 for event in completed),
        compaction_after_tokens_total=sum(event.after_tokens or 0 for event in completed),
        reclaimed_tokens_total=sum(reclaimed),
        retained_tokens_max=max((event.retained_tokens or 0 for event in completed), default=0),
        spill_chars_total=sum(
            event.spilled_chars
            for event in events
            if event.event_type == ContextEventType.TOOL_RESULT_SPILL
        ),
        compaction_count=len(completed),
        contamination_count=len(contamination.findings),
        subscores=subscores,
    )


class ContextGrader:
    async def grade(self, context: GradeContext) -> DimensionScore:
        if context.case.context is None:
            raise ValueError("ContextGrader requires context expectations")
        metrics = build_context_metrics(
            context.case.context,
            context.execution.context_events,
            context.execution.context_checkpoints,
            context.execution.events,
        )
        context.execution.context_metrics = metrics
        findings = [
            finding
            for subscore in metrics.subscores
            for finding in subscore.findings
        ]
        return DimensionScore(
            name="context",
            checks_passed=sum(item.checks_passed for item in metrics.subscores),
            checks_total=sum(item.checks_total for item in metrics.subscores),
            findings=findings,
        )
