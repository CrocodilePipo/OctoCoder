from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from octocoder.evals.models import (
    ContextCheckpoint,
    ContextEvent,
    ContextEventType,
    ContextExpectation,
    EvalEvent,
    Finding,
    ToolTrace,
)
from octocoder.evals.redaction import SecretRedactor


GENERATED_ID = re.compile(
    r"(?i)(?:[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}|(?:toolu|call|trace|run)_[A-Za-z0-9_-]{6,})"
)
MAX_RESULT_SUMMARY = 2000
CHECKPOINT_START = "OCTOCODER_CONTEXT_CHECKPOINT_START"
CHECKPOINT_END = "OCTOCODER_CONTEXT_CHECKPOINT_END"
MAX_CHECKPOINT_JSON = 20_000


@dataclass(frozen=True)
class EventProcessingResult:
    raw_events: list[dict[str, Any]]
    events: list[EvalEvent]
    trajectory: list[ToolTrace]
    findings: list[Finding]
    malformed_count: int
    unpaired_count: int
    context_events: list[ContextEvent] = field(default_factory=list)
    context_checkpoints: list[ContextCheckpoint] = field(default_factory=list)


class EventNormalizer:
    def __init__(self, workspace: Path, redactor: SecretRedactor | None = None) -> None:
        resolved = str(workspace.resolve())
        self._workspace_variants = {
            resolved,
            resolved.replace("\\", "/"),
            resolved.replace("/", "\\"),
        }
        self._redactor = redactor or SecretRedactor()
        self._ids: dict[str, str] = {}

    def text(self, value: str) -> str:
        value = self._redactor.redact_text(value)
        for workspace in sorted(self._workspace_variants, key=len, reverse=True):
            value = re.sub(re.escape(workspace), "$WORKSPACE", value, flags=re.IGNORECASE)
        value = value.replace("\\", "/")

        def stable_id(match: re.Match[str]) -> str:
            raw = match.group(0)
            if raw not in self._ids:
                self._ids[raw] = f"$ID{len(self._ids) + 1}"
            return self._ids[raw]

        return GENERATED_ID.sub(stable_id, value)

    def value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self.value(value[key]) for key in sorted(value, key=str)}
        return value


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "type",
        "sequence",
        "run_id",
        "turn",
        "agent_id",
        "parent_agent_id",
        "trace_id",
        "timestamp_ms",
    }
    return {key: value for key, value in event.items() if key not in metadata}


def _summary(value: Any, normalizer: EventNormalizer) -> tuple[str, str]:
    if isinstance(value, str):
        text = normalizer.text(value)
    else:
        text = json.dumps(normalizer.value(value), ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if len(text) > MAX_RESULT_SUMMARY:
        text = f"{text[:MAX_RESULT_SUMMARY]}... [sha256:{digest}]"
    return text, digest


def _bounded_value(value: Any, normalizer: EventNormalizer) -> Any:
    normalized = normalizer.value(value)
    if isinstance(normalized, str) and len(normalized) > MAX_RESULT_SUMMARY:
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"{normalized[:MAX_RESULT_SUMMARY]}... [sha256:{digest}]"
    if isinstance(normalized, list):
        return [_bounded_value(item, normalizer) for item in normalized[:500]]
    if isinstance(normalized, dict):
        return {
            str(key): _bounded_value(item, normalizer)
            for key, item in list(normalized.items())[:500]
        }
    return normalized


_CONTEXT_FIELDS = {
    "trigger",
    "context_window",
    "threshold_tokens",
    "estimated_tokens",
    "provider_tokens",
    "before_tokens",
    "after_tokens",
    "prefix_messages",
    "retained_messages",
    "retained_tokens",
    "spilled_results",
    "spilled_chars",
    "summary_hash",
    "boundary_id",
    "retry_count",
}


def _context_event_from_raw(
    parsed: dict[str, Any],
    sequence: int,
    normalizer: EventNormalizer,
) -> ContextEvent:
    raw_type = str(parsed.get("event_type", ""))
    event_type = ContextEventType(raw_type)
    kwargs = {
        key: parsed.get(key)
        for key in _CONTEXT_FIELDS
        if parsed.get(key) is not None
    }
    payload = {
        key: value
        for key, value in parsed.items()
        if key
        not in {
            "type",
            "event_type",
            "sequence",
            "run_id",
            "turn",
            "timestamp_ms",
            "stage_id",
            "checkpoint_id",
            "agent_id",
            "parent_agent_id",
            "trace_id",
            *_CONTEXT_FIELDS,
        }
    }
    return ContextEvent(
        sequence=sequence,
        stage_id=normalizer.text(str(parsed.get("stage_id", ""))),
        checkpoint_id=(
            normalizer.text(str(parsed["checkpoint_id"]))
            if parsed.get("checkpoint_id")
            else None
        ),
        event_type=event_type,
        payload=_bounded_value(payload, normalizer),
        **kwargs,
    )


def _checkpoint_from_payload(
    payload: dict[str, Any],
    normalizer: EventNormalizer,
    *,
    default_stage: str,
    source: str,
    agent_id: str = "lead",
    parent_agent_id: str | None = None,
    model: str = "",
) -> ContextCheckpoint:
    normalized = _bounded_value(payload, normalizer)
    raw_instructions = normalized.get("active_instructions", [])
    if isinstance(raw_instructions, dict):
        active_instructions = [
            str(item)
            for key, value in raw_instructions.items()
            for item in (key, value)
            if item is not None
        ]
    elif isinstance(raw_instructions, list):
        active_instructions = [str(item) for item in raw_instructions]
    elif raw_instructions is None:
        active_instructions = []
    else:
        active_instructions = [str(raw_instructions)]
    stage_id = (
        default_stage
        if source == "agent_probe"
        else str(normalized.get("stage_id") or default_stage)
    )
    return ContextCheckpoint(
        id=str(normalized.get("id", normalized.get("checkpoint_id", ""))),
        stage_id=stage_id,
        agent_id=normalizer.text(str(normalized.get("agent_id", agent_id))),
        parent_agent_id=normalizer.value(
            normalized.get("parent_agent_id", parent_agent_id)
        ),
        model=normalizer.text(str(normalized.get("model", model))),
        facts=normalized.get("facts", {}) if isinstance(normalized.get("facts", {}), dict) else {},
        active_instructions=active_instructions,
        task_state=(
            normalized.get("task_state", {})
            if isinstance(normalized.get("task_state", {}), dict)
            else {}
        ),
        answer=str(normalized.get("answer", "")),
        tool_pair_complete=bool(normalized.get("tool_pair_complete", True)),
        source=source,
    )


def _probe_checkpoints(
    events: list[EvalEvent],
    normalizer: EventNormalizer,
    findings: list[Finding],
) -> list[ContextCheckpoint]:
    by_stage: dict[tuple[str, str, str | None], list[str]] = {}
    for event in events:
        if event.event_type == "assistant" and isinstance(event.payload.get("text"), str):
            stage = str(event.payload.get("stage_id", ""))
            key = (stage, event.agent_id, event.parent_agent_id)
            by_stage.setdefault(key, []).append(str(event.payload["text"]))

    checkpoints: list[ContextCheckpoint] = []
    pattern = re.compile(
        re.escape(CHECKPOINT_START) + r"\s*(.*?)\s*" + re.escape(CHECKPOINT_END),
        re.DOTALL,
    )
    for (stage, agent_id, parent_agent_id), chunks in by_stage.items():
        text = "".join(chunks)
        if CHECKPOINT_START not in text:
            continue
        matches = list(pattern.finditer(text))
        if not matches:
            findings.append(
                Finding(
                    code="malformed_context_checkpoint",
                    message=f"Context checkpoint marker in stage {stage!r} is incomplete",
                    evidence={"stage_id": stage},
                )
            )
            continue
        for match in matches:
            encoded = match.group(1).strip()
            if encoded.startswith("```"):
                first_newline = encoded.find("\n")
                if first_newline < 0 or not encoded.endswith("```"):
                    encoded = ""
                else:
                    encoded = encoded[first_newline + 1 : -3].strip()
            if len(encoded) > MAX_CHECKPOINT_JSON:
                findings.append(
                    Finding(
                        code="oversized_context_checkpoint",
                        message=f"Context checkpoint in stage {stage!r} exceeds the size limit",
                        evidence={"stage_id": stage, "chars": len(encoded)},
                    )
                )
                continue
            try:
                payload = json.loads(encoded)
                if not isinstance(payload, dict):
                    raise TypeError("checkpoint must be an object")
                checkpoints.append(
                    _checkpoint_from_payload(
                        payload,
                        normalizer,
                        default_stage=stage,
                        source="agent_probe",
                        agent_id=agent_id,
                        parent_agent_id=parent_agent_id,
                    )
                )
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                findings.append(
                    Finding(
                        code="malformed_context_checkpoint",
                        message=f"Invalid context checkpoint in stage {stage!r}: {exc}",
                        evidence={"stage_id": stage},
                    )
                )
    return checkpoints


def process_events(
    lines: Iterable[str | dict[str, Any]],
    *,
    workspace: Path,
    run_id: str,
    redactor: SecretRedactor | None = None,
    context: ContextExpectation | None = None,
) -> EventProcessingResult:
    normalizer = EventNormalizer(workspace, redactor)
    raw_events: list[dict[str, Any]] = []
    events: list[EvalEvent] = []
    findings: list[Finding] = []
    malformed = 0
    context_events: list[ContextEvent] = []
    context_checkpoints: list[ContextCheckpoint] = []

    for index, line in enumerate(lines):
        try:
            parsed = json.loads(line) if isinstance(line, str) else dict(line)
            if not isinstance(parsed, dict):
                raise TypeError("event must be a JSON object")
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            malformed += 1
            raw_events.append({"_malformed": normalizer.text(str(line))})
            findings.append(
                Finding(
                    code="malformed_event",
                    message=f"Malformed NDJSON event at line {index + 1}: {exc}",
                    hard_gate=True,
                    evidence={"line": normalizer.text(str(line))[:500]},
                )
            )
            continue
        raw_events.append(normalizer.value(parsed))
        event_type = str(parsed.get("type", "unknown"))
        events.append(
            EvalEvent(
                sequence=int(parsed.get("sequence", index)),
                event_type=event_type,
                run_id=normalizer.text(str(parsed.get("run_id", run_id))),
                turn=max(0, int(parsed.get("turn", 0) or 0)),
                agent_id=normalizer.text(str(parsed.get("agent_id", "lead"))),
                parent_agent_id=normalizer.value(parsed.get("parent_agent_id")),
                trace_id=normalizer.value(parsed.get("trace_id")),
                # Wall-clock timing remains in raw_events. Canonical events use zero so
                # deterministic runs can be compared byte-for-byte.
                timestamp_ms=0,
                payload=normalizer.value(_payload(parsed)),
            )
        )
        if event_type == "context":
            try:
                context_event = _context_event_from_raw(
                    parsed, int(parsed.get("sequence", index)), normalizer
                )
                context_events.append(context_event)
                if context_event.event_type == ContextEventType.CHECKPOINT:
                    checkpoint_payload = parsed.get("checkpoint", parsed)
                    if not isinstance(checkpoint_payload, dict):
                        raise TypeError("checkpoint payload must be an object")
                    context_checkpoints.append(
                        _checkpoint_from_payload(
                            checkpoint_payload,
                            normalizer,
                            default_stage=context_event.stage_id,
                            source=str(parsed.get("source", "scripted")),
                            agent_id=str(parsed.get("agent_id", "lead")),
                            parent_agent_id=parsed.get("parent_agent_id"),
                            model=str(parsed.get("model", "")),
                        )
                    )
            except (TypeError, ValueError) as exc:
                findings.append(
                    Finding(
                        code="malformed_context_event",
                        message=f"Malformed context event at line {index + 1}: {exc}",
                        evidence={"sequence": int(parsed.get("sequence", index))},
                    )
                )

    uses: dict[str, tuple[EvalEvent, dict[str, Any]]] = {}
    results: dict[str, EvalEvent] = {}
    decisions: dict[str, str] = {}
    retries: dict[str, str] = {}
    for event in events:
        tool_id = str(event.payload.get("tool_id", ""))
        if event.event_type == "tool_use":
            uses[tool_id or f"sequence:{event.sequence}"] = (event, event.payload)
        elif event.event_type == "tool_result" and tool_id:
            results[tool_id] = event
        elif event.event_type == "permission_decision" and tool_id:
            decisions[tool_id] = str(event.payload.get("decision", ""))
        elif event.event_type == "retry" and tool_id:
            retries[tool_id] = str(event.payload.get("retry_of", ""))

    trajectory: list[ToolTrace] = []
    unpaired = 0
    for tool_id, (use, payload) in sorted(uses.items(), key=lambda item: item[1][0].sequence):
        result = results.pop(tool_id, None)
        if result is None:
            unpaired += 1
            findings.append(
                Finding(
                    code="missing_tool_result",
                    message=f"Tool call {payload.get('tool_name', 'unknown')} has no result",
                    evidence={"tool_id": tool_id},
                )
            )
            result_status = "missing"
            result_summary = ""
            result_hash = ""
            duration_ms = 0
        else:
            result_status = "error" if result.payload.get("is_error") else "success"
            result_summary, result_hash = _summary(result.payload.get("output", ""), normalizer)
            elapsed = result.payload.get("elapsed_ms", result.payload.get("elapsed", 0))
            duration_ms = int(float(elapsed) * 1000) if "elapsed_ms" not in result.payload else int(elapsed)
        arguments = normalizer.value(payload.get("args", payload.get("arguments", {})))
        signature_source = json.dumps(
            {"tool": payload.get("tool_name", payload.get("name", "")), "arguments": arguments},
            ensure_ascii=False,
            sort_keys=True,
        )
        trajectory.append(
            ToolTrace(
                sequence=use.sequence,
                turn=use.turn,
                agent_id=use.agent_id,
                parent_agent_id=use.parent_agent_id,
                trace_id=use.trace_id,
                tool=str(payload.get("tool_name", payload.get("name", "unknown"))),
                arguments=arguments if isinstance(arguments, dict) else {"value": arguments},
                result_status=result_status,
                result_summary=result_summary,
                result_hash=result_hash,
                duration_ms=max(0, duration_ms),
                permission_decision=decisions.get(tool_id),
                retry_of=retries.get(tool_id),
                signature=hashlib.sha256(signature_source.encode("utf-8")).hexdigest(),
            )
        )
    for tool_id, result in results.items():
        unpaired += 1
        findings.append(
            Finding(
                code="missing_tool_use",
                message="Tool result has no matching tool use",
                evidence={"tool_id": tool_id, "sequence": result.sequence},
            )
        )

    open_compactions: list[ContextEvent] = []
    completed_boundaries: set[str] = set()
    for event in context_events:
        if event.event_type == ContextEventType.COMPACT_STARTED:
            open_compactions.append(event)
        elif event.event_type in {
            ContextEventType.COMPACT_COMPLETED,
            ContextEventType.COMPACT_FAILED,
            ContextEventType.COMPACT_SKIPPED,
        }:
            if not open_compactions and event.event_type != ContextEventType.COMPACT_SKIPPED:
                findings.append(
                    Finding(
                        code="invalid_context_transition",
                        message=f"{event.event_type.value} has no preceding compact_started",
                        evidence={"sequence": event.sequence, "stage_id": event.stage_id},
                    )
                )
            elif open_compactions:
                open_compactions.pop(0)
            if (
                event.event_type == ContextEventType.COMPACT_COMPLETED
                and event.before_tokens is not None
                and event.after_tokens is not None
                and event.after_tokens > event.before_tokens
            ):
                findings.append(
                    Finding(
                        code="compaction_increased_context",
                        message="Successful compaction increased the estimated context size",
                        evidence={
                            "sequence": event.sequence,
                            "before_tokens": event.before_tokens,
                            "after_tokens": event.after_tokens,
                        },
                    )
                )
            if event.event_type == ContextEventType.COMPACT_COMPLETED and event.boundary_id:
                completed_boundaries.add(event.boundary_id)
        elif event.event_type == ContextEventType.SESSION_RESUMED:
            if event.boundary_id and event.boundary_id not in completed_boundaries:
                findings.append(
                    Finding(
                        code="unknown_resume_boundary",
                        message="Session resume references an unknown compact boundary",
                        evidence={"sequence": event.sequence, "boundary_id": event.boundary_id},
                    )
                )
    for event in open_compactions:
        findings.append(
            Finding(
                code="unfinished_compaction",
                message="compact_started has no terminal event",
                evidence={"sequence": event.sequence, "stage_id": event.stage_id},
            )
        )

    probe_checkpoints = _probe_checkpoints(events, normalizer, findings)
    for checkpoint in probe_checkpoints:
        checkpoint.tool_pair_complete = unpaired == 0
    context_checkpoints.extend(probe_checkpoints)
    if context is not None:
        stage_ids = {stage.id for stage in context.stages}
        checkpoint_ids = {stage.checkpoint for stage in context.stages if stage.checkpoint}
        for event in context_events:
            if event.stage_id and event.stage_id not in stage_ids:
                findings.append(
                    Finding(
                        code="unknown_context_stage",
                        message=f"Context event references unknown stage {event.stage_id!r}",
                        evidence={"sequence": event.sequence},
                    )
                )
        for checkpoint in context_checkpoints:
            if checkpoint.id not in checkpoint_ids or checkpoint.stage_id not in stage_ids:
                findings.append(
                    Finding(
                        code="unknown_context_checkpoint",
                        message=f"Context checkpoint {checkpoint.id!r} has an unknown reference",
                        evidence={"checkpoint_id": checkpoint.id, "stage_id": checkpoint.stage_id},
                    )
                )

    return EventProcessingResult(
        raw_events,
        events,
        trajectory,
        findings,
        malformed,
        unpaired,
        context_events,
        context_checkpoints,
    )
