from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from octocoder.evals import SCHEMA_VERSION


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutionMode(str, Enum):
    SCRIPTED = "scripted"
    REAL = "real"


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    AGENT_FAILED = "agent_failed"
    FRAMEWORK_FAILED = "framework_failed"
    TIMEOUT = "timeout"
    UNSUPPORTED_INSTRUMENTATION = "unsupported_instrumentation"


class RunStatus(str, Enum):
    SUCCESS = "success"
    EXPECTATION_FAILED = "expectation_failed"
    AGENT_FAILED = "agent_failed"
    FRAMEWORK_FAILED = "framework_failed"
    TIMEOUT = "timeout"
    UNSUPPORTED_INSTRUMENTATION = "unsupported_instrumentation"


class MatchMode(str, Enum):
    CONSTRAINTS = "constraints"
    SUBSEQUENCE = "subsequence"
    EXACT = "exact"


class ArgumentOperator(str, Enum):
    EQUALS = "equals"
    CONTAINS = "contains"
    MATCHES = "matches"
    GLOB = "glob"
    EXISTS = "exists"


class FindingSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def _validate_relative_path(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("path must be a non-empty relative path")
    normalized = value.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError("absolute paths are not allowed")
    if ".." in posix.parts:
        raise ValueError("parent traversal is not allowed")
    return normalized


class ArgumentConstraint(StrictModel):
    path: str
    operator: ArgumentOperator = ArgumentOperator.EQUALS
    value: Any = None

    @model_validator(mode="after")
    def validate_value(self) -> "ArgumentConstraint":
        if self.operator != ArgumentOperator.EXISTS and self.value is None:
            raise ValueError(f"operator {self.operator.value} requires a value")
        return self


class ToolExpectation(StrictModel):
    tool: str = Field(min_length=1)
    arguments: list[ArgumentConstraint] = Field(default_factory=list)
    min_calls: int = Field(default=1, ge=0)
    max_calls: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_call_range(self) -> "ToolExpectation":
        if self.max_calls is not None and self.max_calls < self.min_calls:
            raise ValueError("max_calls must be greater than or equal to min_calls")
        return self


class TrajectoryExpectation(StrictModel):
    match: MatchMode = MatchMode.CONSTRAINTS
    required: list[ToolExpectation] = Field(default_factory=list)
    forbidden: list[ToolExpectation] = Field(default_factory=list)
    order: list[str] = Field(default_factory=list)
    max_total_calls: int | None = Field(default=None, ge=0)
    max_failed_calls: int | None = Field(default=None, ge=0)
    max_repeated_identical_calls: int | None = Field(default=None, ge=1)


class OutcomeCheck(StrictModel):
    id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    hard_gate: bool = True
    weight: float = Field(default=1.0, gt=0)


class CommandCheck(OutcomeCheck):
    type: Literal["command"]
    argv: list[str] = Field(min_length=1)
    cwd: str = "."
    expected_exit: int = 0
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    _validate_cwd = field_validator("cwd")(_validate_relative_path)


class FileExistsCheck(OutcomeCheck):
    type: Literal["file_exists"]
    path: str

    _validate_path = field_validator("path")(_validate_relative_path)


class FileAbsentCheck(OutcomeCheck):
    type: Literal["file_absent"]
    path: str

    _validate_path = field_validator("path")(_validate_relative_path)


class FileContainsCheck(OutcomeCheck):
    type: Literal["file_contains"]
    path: str
    text: str | None = None
    pattern: str | None = None

    _validate_path = field_validator("path")(_validate_relative_path)

    @model_validator(mode="after")
    def validate_matcher(self) -> "FileContainsCheck":
        if (self.text is None) == (self.pattern is None):
            raise ValueError("exactly one of text or pattern is required")
        return self


class DiffContainsCheck(OutcomeCheck):
    type: Literal["diff_contains"]
    text: str | None = None
    pattern: str | None = None

    @model_validator(mode="after")
    def validate_matcher(self) -> "DiffContainsCheck":
        if (self.text is None) == (self.pattern is None):
            raise ValueError("exactly one of text or pattern is required")
        return self


class WorkspaceBoundaryCheck(OutcomeCheck):
    type: Literal["workspace_boundary"]


OutcomeCheckType = Annotated[
    CommandCheck
    | FileExistsCheck
    | FileAbsentCheck
    | FileContainsCheck
    | DiffContainsCheck
    | WorkspaceBoundaryCheck,
    Field(discriminator="type"),
]


class ExpectedSpec(StrictModel):
    trajectory: TrajectoryExpectation = Field(default_factory=TrajectoryExpectation)
    outcome: list[OutcomeCheckType] = Field(default_factory=list)

    @field_validator("outcome")
    @classmethod
    def validate_unique_check_ids(cls, value: list[OutcomeCheckType]) -> list[OutcomeCheckType]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("outcome check IDs must be unique")
        return value


class ExecutionSpec(StrictModel):
    mode: ExecutionMode = ExecutionMode.SCRIPTED
    permission_mode: Literal["default", "acceptEdits", "plan", "bypassPermissions"] = "bypassPermissions"
    env_allowlist: list[str] = Field(default_factory=list)


class LimitsSpec(StrictModel):
    timeout_seconds: float = Field(default=300.0, gt=0, le=3600)
    max_turns: int = Field(default=20, gt=0)
    max_tool_calls: int = Field(default=100, gt=0)
    max_failed_calls: int = Field(default=20, ge=0)
    max_input_tokens: int | None = Field(default=None, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)
    max_stages: int = Field(default=50, gt=0, le=500)
    max_context_events: int = Field(default=10_000, gt=0, le=100_000)
    max_provider_tokens: int | None = Field(default=None, gt=0)


class ScriptEffect(StrictModel):
    type: Literal["write", "delete"]
    path: str
    content: str = ""

    _validate_path = field_validator("path")(_validate_relative_path)


class ScriptSpec(StrictModel):
    events: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[ScriptEffect] = Field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.COMPLETED
    stderr: str = ""
    final_response: str = ""
    duration_ms: int = Field(default=0, ge=0)


_CONTEXT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"


class ContextStage(StrictModel):
    id: str = Field(min_length=1, pattern=_CONTEXT_ID_PATTERN)
    action: Literal["turn", "pressure", "checkpoint", "resume"]
    prompt: str = ""
    repeat: int = Field(default=1, gt=0, le=100)
    checkpoint: str | None = Field(default=None, pattern=_CONTEXT_ID_PATTERN)

    @model_validator(mode="after")
    def validate_stage(self) -> "ContextStage":
        if self.action in {"turn", "pressure"} and not self.prompt.strip():
            raise ValueError(f"{self.action} stage requires a prompt")
        if self.action in {"checkpoint", "resume"} and self.checkpoint is None:
            raise ValueError(f"{self.action} stage requires a checkpoint")
        return self


class ContextFactExpectation(StrictModel):
    id: str = Field(min_length=1, pattern=_CONTEXT_ID_PATTERN)
    value: Any = None
    operator: ArgumentOperator = ArgumentOperator.EQUALS
    source: str = ""
    required_at: list[str] = Field(default_factory=list)
    forbidden_at: list[str] = Field(default_factory=list)
    hard_gate: bool = True

    @model_validator(mode="after")
    def validate_fact(self) -> "ContextFactExpectation":
        if self.operator != ArgumentOperator.EXISTS and self.value is None:
            raise ValueError(f"operator {self.operator.value} requires a value")
        if not self.required_at and not self.forbidden_at:
            raise ValueError("fact must be required or forbidden at a checkpoint")
        return self


class ContextInstructionExpectation(StrictModel):
    id: str = Field(min_length=1, pattern=_CONTEXT_ID_PATTERN)
    text: str | None = None
    pattern: str | None = None
    priority: Literal["safety", "project", "user", "task"] = "task"
    active_at: list[str] = Field(default_factory=list)
    superseded_at: list[str] = Field(default_factory=list)
    hard_gate: bool = True

    @model_validator(mode="after")
    def validate_instruction(self) -> "ContextInstructionExpectation":
        if (self.text is None) == (self.pattern is None):
            raise ValueError("exactly one of text or pattern is required")
        if not self.active_at and not self.superseded_at:
            raise ValueError("instruction must be active or superseded at a checkpoint")
        if self.pattern is not None and len(self.pattern) > 2_000:
            raise ValueError("instruction pattern is too large")
        return self


class ContextStateExpectation(StrictModel):
    checkpoint: str = Field(pattern=_CONTEXT_ID_PATTERN)
    required_files: list[str] = Field(default_factory=list)
    pending_work: list[str] = Field(default_factory=list)
    known_failures: list[str] = Field(default_factory=list)
    expected_next_action: str | None = None
    require_complete_tool_pairs: bool = True
    hard_gate: bool = True

    _validate_required_files = field_validator("required_files")(
        lambda values: [_validate_relative_path(value) for value in values]
    )


class ContextTokenExpectation(StrictModel):
    max_absolute_error_tokens: int | None = Field(default=None, ge=0)
    trigger_tolerance_tokens: int | None = Field(default=None, ge=0)
    require_provider_anchor: bool = False
    hard_gate: bool = False


class ContextCompressionExpectation(StrictModel):
    min_reclaimed_tokens: int | None = Field(default=None, ge=0)
    max_after_tokens: int | None = Field(default=None, ge=0)
    max_retained_tokens: int | None = Field(default=None, ge=0)
    min_compactions: int = Field(default=0, ge=0)
    max_compactions: int | None = Field(default=None, ge=0)
    hard_gate: bool = False

    @model_validator(mode="after")
    def validate_compression(self) -> "ContextCompressionExpectation":
        if self.max_compactions is not None and self.max_compactions < self.min_compactions:
            raise ValueError("max_compactions must be >= min_compactions")
        return self


class ContextResumeExpectation(StrictModel):
    before_checkpoint: str = Field(pattern=_CONTEXT_ID_PATTERN)
    after_checkpoint: str = Field(pattern=_CONTEXT_ID_PATTERN)
    equivalent_fact_ids: list[str] = Field(default_factory=list)
    equivalent_instruction_ids: list[str] = Field(default_factory=list)
    equivalent_state_fields: list[str] = Field(default_factory=list)
    before_model: str | None = None
    after_model: str | None = None
    require_model_change: bool = False
    hard_gate: bool = True

    @model_validator(mode="after")
    def validate_model_transition(self) -> "ContextResumeExpectation":
        if self.require_model_change and not (self.before_model and self.after_model):
            raise ValueError(
                "model change checks require before_model and after_model"
            )
        if (
            self.require_model_change
            and self.before_model == self.after_model
        ):
            raise ValueError("model change checks require distinct models")
        return self


class ContextExpectation(StrictModel):
    stages: list[ContextStage] = Field(min_length=1)
    facts: list[ContextFactExpectation] = Field(default_factory=list)
    instructions: list[ContextInstructionExpectation] = Field(default_factory=list)
    states: list[ContextStateExpectation] = Field(default_factory=list)
    token: ContextTokenExpectation | None = None
    compression: ContextCompressionExpectation | None = None
    resumes: list[ContextResumeExpectation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "ContextExpectation":
        for label, values in (
            ("context stage", [item.id for item in self.stages]),
            ("context checkpoint", [item.checkpoint for item in self.stages if item.checkpoint]),
            ("context fact", [item.id for item in self.facts]),
            ("context instruction", [item.id for item in self.instructions]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")
        return self


class EvalCase(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    title: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    prompt: str = Field(min_length=1)
    fixture: str
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    limits: LimitsSpec = Field(default_factory=LimitsSpec)
    expected: ExpectedSpec = Field(default_factory=ExpectedSpec)
    script: ScriptSpec | None = None
    context: ContextExpectation | None = None

    _validate_fixture = field_validator("fixture")(_validate_relative_path)

    @model_validator(mode="after")
    def validate_execution(self) -> "EvalCase":
        if self.execution.mode == ExecutionMode.SCRIPTED and self.script is None:
            raise ValueError("scripted execution requires script")
        if self.execution.mode == ExecutionMode.REAL and self.script is not None:
            raise ValueError("real execution cannot define script")
        return self


class ComparisonThresholds(StrictModel):
    failed_runs_increase: int = Field(default=0, ge=0)
    duration_increase_ms: int = Field(default=30_000, ge=0)
    input_tokens_increase: int = Field(default=10_000, ge=0)
    output_tokens_increase: int = Field(default=2_000, ge=0)
    tool_calls_increase: int = Field(default=5, ge=0)
    turns_increase: int = Field(default=5, ge=0)
    context_retention_drop: float | None = Field(default=None, ge=0, le=1)
    context_adherence_drop: float | None = Field(default=None, ge=0, le=1)
    context_resume_drop: float | None = Field(default=None, ge=0, le=1)
    context_token_error_increase_tokens: int | None = Field(default=None, ge=0)
    context_reclaimed_tokens_drop: int | None = Field(default=None, ge=0)
    context_retained_tokens_increase: int | None = Field(default=None, ge=0)
    context_compaction_count_increase: int | None = Field(default=None, ge=0)
    context_contamination_increase: int | None = Field(default=0, ge=0)


class EvalSuite(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    description: str = ""
    cases: list[str] = Field(default_factory=list)
    include_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)
    repeat: int = Field(default=1, gt=0, le=100)
    thresholds: ComparisonThresholds = Field(default_factory=ComparisonThresholds)

    @model_validator(mode="after")
    def validate_selection(self) -> "EvalSuite":
        if not self.cases and not self.include_tags:
            raise ValueError("suite must select cases or include_tags")
        return self


class EvalEvent(StrictModel):
    sequence: int = Field(ge=0)
    event_type: str
    run_id: str
    turn: int = Field(default=0, ge=0)
    agent_id: str = "lead"
    parent_agent_id: str | None = None
    trace_id: str | None = None
    timestamp_ms: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolTrace(StrictModel):
    sequence: int = Field(ge=0)
    turn: int = Field(default=0, ge=0)
    agent_id: str = "lead"
    parent_agent_id: str | None = None
    trace_id: str | None = None
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result_status: Literal["success", "error", "missing"] = "missing"
    result_summary: str = ""
    result_hash: str = ""
    duration_ms: int = Field(default=0, ge=0)
    permission_decision: str | None = None
    retry_of: str | None = None
    signature: str = ""


class ContextEventType(str, Enum):
    USAGE_ANCHOR = "usage_anchor"
    TOOL_RESULT_SPILL = "tool_result_spill"
    COMPACT_STARTED = "compact_started"
    COMPACT_COMPLETED = "compact_completed"
    COMPACT_SKIPPED = "compact_skipped"
    COMPACT_FAILED = "compact_failed"
    CHECKPOINT = "checkpoint"
    SESSION_RESUMED = "session_resumed"


class ContextEvent(StrictModel):
    sequence: int = Field(ge=0)
    stage_id: str = ""
    checkpoint_id: str | None = None
    event_type: ContextEventType
    trigger: str = ""
    context_window: int | None = Field(default=None, ge=0)
    threshold_tokens: int | None = Field(default=None, ge=0)
    estimated_tokens: int | None = Field(default=None, ge=0)
    provider_tokens: int | None = Field(default=None, ge=0)
    before_tokens: int | None = Field(default=None, ge=0)
    after_tokens: int | None = Field(default=None, ge=0)
    prefix_messages: int | None = Field(default=None, ge=0)
    retained_messages: int | None = Field(default=None, ge=0)
    retained_tokens: int | None = Field(default=None, ge=0)
    spilled_results: int = Field(default=0, ge=0)
    spilled_chars: int = Field(default=0, ge=0)
    summary_hash: str = ""
    boundary_id: str = ""
    retry_count: int = Field(default=0, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class ContextCheckpoint(StrictModel):
    id: str = Field(pattern=_CONTEXT_ID_PATTERN)
    stage_id: str = Field(pattern=_CONTEXT_ID_PATTERN)
    agent_id: str = "lead"
    parent_agent_id: str | None = None
    model: str = ""
    facts: dict[str, Any] = Field(default_factory=dict)
    active_instructions: list[str] = Field(default_factory=list)
    task_state: dict[str, Any] = Field(default_factory=dict)
    answer: str = ""
    tool_pair_complete: bool = True
    source: Literal["scripted", "agent_probe", "resume"]


class Finding(StrictModel):
    code: str
    message: str
    severity: FindingSeverity = FindingSeverity.ERROR
    hard_gate: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)


class Usage(StrictModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)


class WorkspaceSnapshot(StrictModel):
    patch: str = ""
    changed_files: list[str] = Field(default_factory=list)
    before_manifest: dict[str, str] = Field(default_factory=dict)
    after_manifest: dict[str, str] = Field(default_factory=dict)


class ExecutionResult(StrictModel):
    run_id: str
    case_id: str
    mode: ExecutionMode
    status: ExecutionStatus
    started_at: str
    duration_ms: int = Field(ge=0)
    provider: str = ""
    model: str = ""
    final_response: str = ""
    errors: list[str] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    raw_events: list[dict[str, Any]] = Field(default_factory=list)
    events: list[EvalEvent] = Field(default_factory=list)
    trajectory: list[ToolTrace] = Field(default_factory=list)
    workspace_diff: WorkspaceSnapshot = Field(default_factory=WorkspaceSnapshot)
    stderr: str = ""
    turns: int = Field(default=0, ge=0)
    malformed_event_count: int = Field(default=0, ge=0)
    unpaired_event_count: int = Field(default=0, ge=0)
    context_events: list[ContextEvent] = Field(default_factory=list)
    context_checkpoints: list[ContextCheckpoint] = Field(default_factory=list)
    context_metrics: ContextMetrics | None = None


class DimensionScore(StrictModel):
    name: Literal["outcome", "trajectory", "efficiency", "safety", "reliability", "context"]
    checks_passed: float = Field(default=0, ge=0)
    checks_total: float = Field(default=0, ge=0)
    findings: list[Finding] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_check_counts(self) -> "DimensionScore":
        if self.checks_passed > self.checks_total:
            raise ValueError("checks_passed cannot exceed checks_total")
        return self


class ContextSubscore(StrictModel):
    name: Literal[
        "retention",
        "instruction_adherence",
        "continuity",
        "resume_consistency",
        "token_accuracy",
        "compression_efficiency",
        "contamination",
    ]
    checks_passed: int = Field(default=0, ge=0)
    checks_total: int = Field(default=0, ge=0)
    similarity: float | None = Field(default=None, ge=0, le=1)
    findings: list[Finding] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_check_counts(self) -> "ContextSubscore":
        if self.checks_passed > self.checks_total:
            raise ValueError("checks_passed cannot exceed checks_total")
        return self


class ContextMetrics(StrictModel):
    retention_rate: float | None = Field(default=None, ge=0, le=1)
    instruction_adherence_rate: float | None = Field(default=None, ge=0, le=1)
    continuity_rate: float | None = Field(default=None, ge=0, le=1)
    resume_consistency_rate: float | None = Field(default=None, ge=0, le=1)
    token_error_tokens_mean: float | None = Field(default=None, ge=0)
    token_error_tokens_max: int | None = Field(default=None, ge=0)
    compaction_before_tokens_total: int = Field(default=0, ge=0)
    compaction_after_tokens_total: int = Field(default=0, ge=0)
    reclaimed_tokens_total: int = Field(default=0, ge=0)
    retained_tokens_max: int = Field(default=0, ge=0)
    spill_chars_total: int = Field(default=0, ge=0)
    compaction_count: int = Field(default=0, ge=0)
    contamination_count: int = Field(default=0, ge=0)
    subscores: list[ContextSubscore] = Field(default_factory=list)


class CaseScore(StrictModel):
    passed: bool
    dimensions: list[DimensionScore]
    findings: list[Finding] = Field(default_factory=list)


class CaseRunResult(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    status: RunStatus
    execution: ExecutionResult
    verdict: CaseScore
    artifact_path: str = ""


class MetricSummary(StrictModel):
    samples: int = Field(default=0, ge=0)
    mean: float = 0
    median: float = 0
    minimum: float = 0
    maximum: float = 0
    p95: float | None = None


class SuiteReport(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    suite_id: str
    passed: bool
    total_runs: int = Field(default=0, ge=0)
    passed_runs: int = Field(default=0, ge=0)
    failed_runs: int = Field(default=0, ge=0)
    results: list[CaseRunResult]
    thresholds: ComparisonThresholds = Field(default_factory=ComparisonThresholds)
    duration_summary: MetricSummary = Field(default_factory=MetricSummary)
    input_tokens_summary: MetricSummary = Field(default_factory=MetricSummary)
    output_tokens_summary: MetricSummary = Field(default_factory=MetricSummary)
    turns_summary: MetricSummary = Field(default_factory=MetricSummary)
    tool_calls_summary: MetricSummary = Field(default_factory=MetricSummary)
    context_summary: dict[str, MetricSummary] = Field(default_factory=dict)


class ComparisonChange(StrictModel):
    case_id: str
    metric: str
    baseline: float | bool | None = None
    candidate: float | bool | None = None
    classification: Literal["improvement", "regression", "unchanged"]
    message: str = ""


class ComparisonReport(StrictModel):
    schema_version: Literal[SCHEMA_VERSION] = SCHEMA_VERSION
    baseline_suite_id: str
    candidate_suite_id: str
    regression: bool
    changes: list[ComparisonChange] = Field(default_factory=list)
