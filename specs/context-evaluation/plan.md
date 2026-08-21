# OctoCoder Context Management Evaluation Plan

> Metric-model amendment (2026-08-21): weighted subscores, relative token error,
> compression-ratio gates, and context-score comparisons below are superseded by
> check counts, semantic similarity, and absolute token/compaction measurements.

## Architecture Overview

The context evaluation feature extends the existing Agent evaluation framework instead of creating a separate harness. It introduces five cooperating layers:

1. **Production context instrumentation** emits bounded lifecycle observations from token anchoring, tool-result persistence, compaction, and resume paths.
2. **Multi-stage scenario execution** runs setup, pressure, probe, checkpoint, and resume stages while preserving one Agent conversation.
3. **Context event normalization** converts production and scripted observations into one stable timeline and checkpoint model.
4. **Context grading** evaluates declared facts, instructions, working state, token accuracy, compression behavior, contamination, and resume consistency.
5. **Artifacts and regression reporting** persist context-specific evidence and compare context metrics without changing non-context case behavior.

Deterministic scripted scenarios remain the mandatory CI path. Real scenarios use the same schema and grader but run through a persistent non-interactive Agent session. Existing single-prompt cases continue through the current runner path unchanged.

## Core Data Structures

### Context Scenario Definition

```python
class ContextStage(BaseModel):
    id: str
    action: Literal["turn", "pressure", "checkpoint", "resume"]
    prompt: str = ""
    repeat: int = 1
    checkpoint: str | None = None

class ContextFactExpectation(BaseModel):
    id: str
    value: Any
    operator: Literal["equals", "contains", "matches", "glob", "exists"]
    source: str = ""
    required_at: list[str]
    forbidden_at: list[str]
    hard_gate: bool = True

class ContextInstructionExpectation(BaseModel):
    id: str
    text: str | None
    pattern: str | None
    priority: Literal["safety", "project", "user", "task"]
    active_at: list[str]
    superseded_at: list[str]
    hard_gate: bool = True

class ContextStateExpectation(BaseModel):
    checkpoint: str
    required_files: list[str]
    pending_work: list[str]
    known_failures: list[str]
    expected_next_action: str | None
    require_complete_tool_pairs: bool = True
    hard_gate: bool = True

class ContextTokenExpectation(BaseModel):
    max_relative_error: float | None
    trigger_tolerance_tokens: int | None
    require_provider_anchor: bool = False
    hard_gate: bool = False

class ContextCompressionExpectation(BaseModel):
    min_reclaimed_tokens: int | None
    min_compression_ratio: float | None
    max_compression_ratio: float | None
    max_retained_tokens: int | None
    min_compactions: int = 0
    max_compactions: int | None
    hard_gate: bool = False

class ContextResumeExpectation(BaseModel):
    before_checkpoint: str
    after_checkpoint: str
    equivalent_fact_ids: list[str]
    equivalent_instruction_ids: list[str]
    equivalent_state_fields: list[str]
    hard_gate: bool = True

class ContextExpectation(BaseModel):
    stages: list[ContextStage]
    facts: list[ContextFactExpectation]
    instructions: list[ContextInstructionExpectation]
    states: list[ContextStateExpectation]
    token: ContextTokenExpectation | None
    compression: ContextCompressionExpectation | None
    resumes: list[ContextResumeExpectation]
```

`EvalCase` gains an optional `context` field. Context stage IDs and checkpoint IDs are unique. All references are validated before execution. Existing cases with `context=None` retain their current behavior and score shape.

### Context Lifecycle Event

```python
class ContextEventType(str, Enum):
    USAGE_ANCHOR = "usage_anchor"
    TOOL_RESULT_SPILL = "tool_result_spill"
    COMPACT_STARTED = "compact_started"
    COMPACT_COMPLETED = "compact_completed"
    COMPACT_SKIPPED = "compact_skipped"
    COMPACT_FAILED = "compact_failed"
    CHECKPOINT = "checkpoint"
    SESSION_RESUMED = "session_resumed"

class ContextEvent(BaseModel):
    sequence: int
    stage_id: str
    checkpoint_id: str | None
    event_type: ContextEventType
    trigger: str = ""
    context_window: int | None
    threshold_tokens: int | None
    estimated_tokens: int | None
    provider_tokens: int | None
    before_tokens: int | None
    after_tokens: int | None
    prefix_messages: int | None
    retained_messages: int | None
    retained_tokens: int | None
    spilled_results: int = 0
    spilled_chars: int = 0
    summary_hash: str = ""
    boundary_id: str = ""
    retry_count: int = 0
    payload: dict[str, Any]
```

Raw timestamps and bounded diagnostic text remain in raw events. Normalized context events remove volatile timestamps and generated IDs, normalize paths, and hash summary or content values that are not needed verbatim.

### Context Checkpoint

```python
class ContextCheckpoint(BaseModel):
    id: str
    stage_id: str
    facts: dict[str, Any]
    active_instructions: list[str]
    task_state: dict[str, Any]
    answer: str = ""
    tool_pair_complete: bool = True
    source: Literal["scripted", "agent_probe", "resume"]
```

Deterministic scripted events supply checkpoint payloads directly. Real probes ask the Agent to emit a bounded JSON object inside a fixed marker. Parsing failure is a context reliability finding, not silently converted to an empty checkpoint.

### Context Metrics

```python
class ContextSubscore(BaseModel):
    name: Literal[
        "retention",
        "instruction_adherence",
        "continuity",
        "resume_consistency",
        "token_accuracy",
        "compression_efficiency",
        "contamination",
    ]
    score: float
    findings: list[Finding]

class ContextMetrics(BaseModel):
    retention_rate: float | None
    instruction_adherence_rate: float | None
    continuity_rate: float | None
    resume_consistency_rate: float | None
    token_relative_error_mean: float | None
    token_relative_error_max: float | None
    compression_ratio_mean: float | None
    reclaimed_tokens_total: int
    retained_tokens_max: int
    spill_chars_total: int
    compaction_count: int
    contamination_count: int
    subscores: list[ContextSubscore]
```

`ExecutionResult` gains `context_events`, `context_checkpoints`, and `context_metrics`. For non-context cases these fields remain empty/default and are omitted from context artifact generation.

### Context Dimension

`DimensionScore.name` adds `context`. The context grader computes:

| Subscore | Weight | Evidence |
| --- | ---: | --- |
| Retention | 25% | required facts at checkpoints |
| Instruction adherence | 20% | active and superseded instruction checks |
| Continuity | 15% | task state, next action, files, failures, tool pairs |
| Resume consistency | 15% | before/after checkpoint equivalence |
| Token accuracy | 10% | estimate versus provider-shaped anchors and trigger offset |
| Compression efficiency | 10% | reclaimed tokens, ratio, retained tail, count |
| Contamination | 5% | forbidden stale facts and superseded instructions |

Unavailable optional metrics are excluded from the weighted denominator rather than scored as zero. Any finding declared as a hard gate fails the case regardless of the numeric score.

## Core Interfaces

### Context Observer

```python
class ContextObserver(Protocol):
    def emit(self, event: ContextLifecycleObservation) -> None: ...

class NullContextObserver:
    def emit(self, event: ContextLifecycleObservation) -> None: ...
```

Production context functions accept an optional observer. The default observer is a no-op, preserving normal runtime behavior and existing call sites. Agent-owned observers translate observations into Agent events; evaluation workers attach stage and checkpoint identity.

### Persistent Non-Interactive Session

```python
class NonInteractiveSession:
    async def create(config, permission_mode, hook_engine, event_sink) -> "NonInteractiveSession": ...
    async def run_turn(self, prompt: str, stage_id: str) -> TurnResult: ...
    async def checkpoint(self, checkpoint_id: str) -> ContextCheckpoint: ...
    async def persist_and_resume(self, stage_id: str) -> ResumeResult: ...
    async def close(self) -> None: ...
```

The existing single-prompt CLI delegates to this session for one turn. A context worker uses the same object for multiple stages. This removes duplicated Agent construction while preserving the existing `octocoder -p` output contract.

### Context Scenario Runner

```python
class ContextScenarioRunner(Protocol):
    async def run(self, request: RunRequest) -> RunnerOutput: ...

class ScriptedContextRunner:
    async def run(self, request: RunRequest) -> RunnerOutput: ...

class RealContextRunner:
    async def run(self, request: RunRequest) -> RunnerOutput: ...
```

The orchestrator selects a context runner only when `case.context` exists. Scripted context stages replay declared stage-tagged events and effects. Real context stages launch a dedicated subprocess worker, keep one Agent session alive across turns, and use the existing safe process-tree timeout handling.

### Context Grader

```python
class ContextGrader:
    async def grade(self, context: GradeContext) -> DimensionScore: ...

def build_context_metrics(
    expected: ContextExpectation,
    events: list[ContextEvent],
    checkpoints: list[ContextCheckpoint],
) -> ContextMetrics: ...
```

The grader is registered through the existing grader boundary. Shared dotted-path and typed matching helpers are extracted from trajectory grading so fact and state assertions use the same operators.

## Module Design

### Production Context Instrumentation

**Responsibility:** Emit bounded observations without changing context decisions.

**Changes:**

- token anchoring emits estimated/provider counts and anchor message count;
- tool-result budgeting emits pre/post character totals and replacement counts;
- compaction emits started, skipped, completed, and failed observations;
- completed compaction includes threshold, before/after estimates, prefix/retained counts, retained tokens, summary hash, and boundary ID;
- session reconstruction emits resume identity and restored counts.

No full summary, credential, or unbounded tool result is placed in lifecycle payloads.

### Non-Interactive Runtime

**Responsibility:** Factor current non-interactive Agent construction and event handling into a reusable persistent session.

**Compatibility:** `octocoder -p` still accepts the same arguments and emits the same event fields plus optional context events. Text mode remains unchanged.

### Context Event Processing

**Responsibility:** Parse `type=context` events, normalize stage IDs and paths, validate monotonic lifecycle order, build checkpoints, and report malformed transitions.

Lifecycle invariants include:

- each completed or failed compaction follows a started event;
- after tokens do not exceed before tokens for a successful compaction unless explicitly explained;
- resumed boundary IDs refer to a previously completed boundary;
- checkpoint stage IDs exist in the case definition;
- tool-use/tool-result pairs remain complete across retained tails.

### Context Grading

**Responsibility:** Produce one context dimension and `ContextMetrics`.

Matching is deterministic. Facts and state use typed exact/contains/regex/glob/existence checks. Instructions use normalized literal or bounded regex matching. Real-model answer prose is evaluated only through declared structured probe fields; no LLM judge is required.

### Artifacts And Reports

**Responsibility:** Persist and render context evidence.

Additional case artifacts:

```text
context-events.jsonl
context-checkpoints.json
context-metrics.json
```

Markdown adds a context section with checkpoint table, subscore table, token/compression metrics, first failed stage, and hard-gate evidence. Existing artifacts remain unchanged.

### Baseline Comparison

**Responsibility:** Compare context quality and resource behavior.

`ComparisonThresholds` adds optional context thresholds:

- context score drop;
- retention/adherence/resume rate drop;
- token error increase;
- compression ratio decrease;
- compaction count increase.

Pass-to-fail and new context hard gates remain unconditional regressions.

## Module Interactions

```text
YAML case
  -> schema/loader validates stages and references
  -> orchestrator selects normal or context runner
  -> scripted replay OR persistent real Agent session
  -> production observer emits stage-tagged context lifecycle events
  -> event processor normalizes context timeline/checkpoints
  -> existing outcome/trajectory graders run
  -> context grader builds metrics and context dimension
  -> hard-gate composition determines case result
  -> artifact writer persists standard + context artifacts
  -> suite report aggregates repetitions
  -> baseline comparison applies context thresholds
```

Resume-stage ownership:

1. The active session persists its compact boundary and replacement records through existing session APIs.
2. The worker closes the active Agent session.
3. A new session instance reconstructs conversation and replacement state.
4. A resume checkpoint is emitted before the next probe turn.
5. The context grader compares declared before/after checkpoint fields.

## File Organization

```text
herness/octocoder/
  __main__.py                         - delegate single prompt to persistent runtime
  agent.py                            - emit context Agent events
  conversation.py                     - usage-anchor observations
  context/manager.py                  - compaction and spill observations
  memory/session.py                   - resume observations
  noninteractive.py                   - reusable persistent non-interactive session
  evals/
    models.py                         - context schemas, events, checkpoints, metrics
    events.py                         - context event parsing and normalization
    orchestration.py                  - context runner selection and lifecycle
    scoring.py                        - optional context dimension composition
    artifacts.py                      - context artifact persistence
    report.py                         - context Markdown and aggregates
    compare.py                        - context regression metrics
    context_worker.py                 - subprocess multi-stage real execution
    runners/
      context_scripted.py             - deterministic multi-stage replay
      context_real.py                 - persistent real scenario subprocess
    graders/
      matching.py                     - shared typed value matching
      context.py                      - context metrics and hard gates
herness/tests/
  test_context_observer.py
  test_noninteractive_session.py
  test_eval_context_models.py
  test_eval_context_events.py
  test_eval_context_scripted_runner.py
  test_eval_context_real_runner.py
  test_eval_context_grader.py
  test_eval_context_artifacts.py
  test_eval_context_compare.py
  test_eval_context_cli.py
evals/
  cases/context/
    retention-success.yaml
    critical-fact-loss.yaml
    stale-contamination.yaml
    instruction-priority.yaml
    resume-divergence.yaml
    token-drift.yaml
    ineffective-compaction.yaml
  fixtures/context-project/
  suites/context-smoke.yaml
  suites/context-nightly.yaml
.github/workflows/evals.yml            - context smoke PR gate and optional real probes
README.md
README.en.md
README.zh-CN.md
```

## Technical Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Evaluation mode | Hybrid | Deterministic CI catches regressions; real probes expose model-dependent quality |
| Context integration | Optional field on existing case | Preserves current CLI, suites, artifacts, and runner ownership |
| Runtime shape | Persistent non-interactive session | Real context tests require multiple turns in one actual Agent conversation |
| Instrumentation | Optional no-op observer | Keeps production behavior unchanged and makes white-box evidence explicit |
| Semantic oracle | Structured deterministic checkpoints | Avoids a mandatory LLM judge and enables reproducible CI |
| Score shape | Add context dimension only for context cases | Existing five-dimension baselines remain comparable |
| Critical failures | Per-expectation hard gates | Context loss cannot be hidden by compression or efficiency scores |
| Summary evidence | Hash and bounded metadata | Supports diagnosis without persisting full sensitive context |
| Resume evaluation | Restart session through existing persistence APIs | Tests the real restore boundary instead of copying in-memory state |
| Real probes | Opt-in repeated suite | Controls cost and accounts for model variability |
| Backward compatibility | Context artifacts generated only for context cases | Existing reports and consumers remain valid |

## Compatibility And Migration

- Evaluation schema version remains readable for current cases; context fields are optional.
- Persisted report models use defaults for new context fields so previous report JSON can still be loaded.
- Existing five dimensions remain unchanged for cases without context expectations.
- Structured event consumers may ignore the new `context` event type.
- Text-mode CLI output and desktop/remote protocols do not display lifecycle payloads unless a UI later opts in.
- Existing context function callers require no observer argument changes because observers default to no-op.

## Requirement Coverage

| Requirements | Design Coverage |
| --- | --- |
| F1-F4 | context stages and scripted/real context runners |
| F5-F6 | observer, bounded context events, redaction |
| F7-F10 | facts, instructions, state, and resume expectations |
| F11-F12 | token and compression metrics |
| F13-F16 | context dimension, subscores, hard gates, checkpoint findings |
| F17-F18 | context artifacts, reports, and comparison thresholds |
| F19-F20 | deterministic reference cases and opt-in real suites |
| F21 | optional schema fields and conditional scoring/artifacts |
| N1-N4 | deterministic normalization, offline scripted mode, repetition, versioned bounded models |
| N5-N9 | no-op observer, grader boundary, explicit limits/status, Python/platform compatibility |
