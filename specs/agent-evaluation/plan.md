# OctoCoder Agent Evaluation MVP Plan

> Metric-model amendment (2026-08-21): numeric 100-point totals, dimension scores,
> pass-rate gates, and `score.json` are superseded by `verdict.json`, passed/total
> check counts, failed-run counts, and absolute duration/token/turn/tool-call
> measurements. Percentages are reserved for semantic similarity metrics. Older
> score terminology below records the original implementation plan.

## Architecture Overview

The evaluation system is a backend-only Python package with a command-line entry point. It uses one shared pipeline for real and deterministic execution:

```text
Case/Suite Loader
       |
       v
Fixture Workspace Manager
       |
       v
Runner (Real or Scripted)
       |
       v
Raw Event Collector -> Secret Redactor -> Event Normalizer
       |                                      |
       v                                      v
Workspace Snapshot/Diff                Tool Trajectory
       |                                      |
       +------------------+-------------------+
                          v
                 Independent Graders
                          |
                          v
             Case Result + Run Artifacts
                          |
                          v
               Suite Aggregation/Compare
                          |
                          v
                  JSON + Markdown
```

Real execution starts the existing non-interactive OctoCoder CLI as a subprocess in the isolated fixture workspace and consumes NDJSON from `stream-json`. Scripted execution replays declared events and applies declarative file effects. Both produce the same `ExecutionResult`, so normalization, grading, reporting, and baseline comparison are shared.

## Core Data Structures

All persisted structures carry `schema_version: 1` and use Pydantic validation.

### EvalCase

```python
class EvalCase(BaseModel):
    schema_version: Literal[1]
    id: str
    title: str
    description: str = ""
    tags: list[str] = []
    prompt: str
    fixture: str
    execution: ExecutionSpec
    limits: LimitSpec
    expected: ExpectedSpec
    script: ScriptSpec | None = None
```

`ExecutionSpec` selects `real` or `scripted`, permission mode, repeat count, and optional environment allow-list. `LimitSpec` contains wall-clock timeout, maximum turns, maximum tool calls, maximum failed calls, and optional token ceilings.

### EvalSuite

```python
class EvalSuite(BaseModel):
    schema_version: Literal[1]
    id: str
    description: str = ""
    cases: list[str] = []
    include_tags: list[str] = []
    exclude_tags: list[str] = []
    repeat: int = 1
    thresholds: ComparisonThresholds
```

A suite may list case IDs, select tags, or combine both. Duplicate selections are removed while preserving deterministic case-ID order.

### ToolExpectation

```python
class ArgumentConstraint(BaseModel):
    path: str
    operator: Literal["equals", "contains", "matches", "glob", "exists"]
    value: Any | None = None

class ToolExpectation(BaseModel):
    tool: str
    arguments: list[ArgumentConstraint] = []
    min_calls: int = 1
    max_calls: int | None = None
```

Argument paths use a small dotted-path convention such as `file_path` or `options.cwd`. The MVP does not introduce a general expression language.

### TrajectoryExpectation

```python
class TrajectoryExpectation(BaseModel):
    match: Literal["constraints", "subsequence", "exact"] = "constraints"
    required: list[ToolExpectation] = []
    forbidden: list[ToolExpectation] = []
    order: list[ToolExpectation] = []
    max_total_calls: int | None = None
    max_failed_calls: int | None = None
    max_repeated_identical_calls: int | None = None
```

`exact` compares the complete normalized tool-call sequence. `subsequence` requires the declared ordered sequence while permitting unrelated calls. `constraints` evaluates required, forbidden, count, and efficiency constraints without requiring one unique path.

### OutcomeCheck

Outcome checks are a discriminated union with common fields `id`, `hard_gate`, and `weight`:

```python
CommandCheck(argv: list[str], cwd: str = ".", expected_exit: int = 0)
FileExistsCheck(path: str)
FileAbsentCheck(path: str)
FileContainsCheck(path: str, text: str | None, pattern: str | None)
DiffContainsCheck(text: str | None, pattern: str | None)
WorkspaceBoundaryCheck()
```

Commands run without a shell, with a timeout and an environment derived from a restricted allow-list.

### EvalEvent And ToolTrace

```python
class EvalEvent(BaseModel):
    sequence: int
    event_type: str
    run_id: str
    turn: int | None = None
    agent_id: str | None = None
    parent_agent_id: str | None = None
    trace_id: str | None = None
    timestamp_ms: int | None = None
    payload: dict[str, Any]

class ToolTrace(BaseModel):
    sequence: int
    turn: int | None
    agent_id: str | None
    parent_agent_id: str | None
    trace_id: str | None
    tool: str
    arguments: dict[str, Any]
    result_status: Literal["success", "error", "timeout", "cancelled", "unknown"]
    result_summary: str
    result_hash: str
    duration_ms: int | None
    permission_decision: str | None
    retry_of: int | None
```

Tool-use and tool-result events are paired by tool ID. Unpaired events remain visible and lower reliability rather than being discarded.

### ExecutionResult

```python
class ExecutionResult(BaseModel):
    run_id: str
    case_id: str
    mode: Literal["real", "scripted"]
    status: Literal["completed", "agent_failed", "framework_failed", "timeout"]
    started_at: str
    duration_ms: int
    provider: str | None
    model: str | None
    final_response: str
    errors: list[str]
    usage: UsageSummary
    raw_events: list[dict[str, Any]]
    events: list[EvalEvent]
    trajectory: list[ToolTrace]
    workspace_diff: str
```

### Scores And Reports

```python
class DimensionScore(BaseModel):
    score: float
    passed: bool
    findings: list[Finding]

class CaseScore(BaseModel):
    passed: bool
    hard_gate_failures: list[Finding]
    outcome: DimensionScore
    trajectory: DimensionScore
    efficiency: DimensionScore
    safety: DimensionScore
    reliability: DimensionScore

class CaseRunResult(BaseModel):
    execution: ExecutionResult
    score: CaseScore
    artifact_dir: str

class SuiteReport(BaseModel):
    schema_version: Literal[1]
    suite_id: str
    runs: list[CaseRunResult]
    aggregates: dict[str, MetricAggregate]
```

Scores remain separate. `passed` is derived from completion, hard gates, and required checks; no weighted total can override a safety failure.

## Module Design

### `octocoder.evals.models`

**Responsibility:** Define and validate all versioned case, suite, event, trajectory, score, and report structures.

**Public Interface:** Pydantic model classes and enums listed above.

**Dependencies:** Pydantic only.

### `octocoder.evals.loader`

**Responsibility:** Discover YAML files, validate cases and suites, resolve suite selectors, reject duplicate IDs, and resolve fixture paths beneath the configured evaluation root.

**Public Interface:**

```python
load_case(path: Path) -> EvalCase
load_suite(path: Path) -> EvalSuite
discover_cases(root: Path) -> dict[str, LoadedCase]
resolve_suite(root: Path, suite: EvalSuite) -> list[LoadedCase]
```

**Dependencies:** `models`, PyYAML.

### `octocoder.evals.workspace`

**Responsibility:** Create evaluation-owned temporary workspaces, copy fixtures without source Git metadata, initialize an ephemeral Git baseline, capture a binary-safe Git diff, produce file manifests, and clean up only verified owned paths.

**Public Interface:**

```python
prepare_workspace(fixture: Path, run_root: Path, run_id: str) -> PreparedWorkspace
capture_workspace(workspace: PreparedWorkspace) -> WorkspaceArtifact
cleanup_workspace(workspace: PreparedWorkspace) -> None
```

**Dependencies:** Standard library and Git executable.

An ownership marker containing the run ID is written before any cleanup is permitted. Cleanup verifies the resolved path is below the run root and that the marker matches.

### `octocoder.evals.redaction`

**Responsibility:** Redact known credentials from raw events, stderr, tool results, diffs, JSON, and Markdown before persistence.

**Public Interface:**

```python
class SecretRedactor:
    @classmethod
    def from_runtime(cls) -> SecretRedactor: ...
    def redact_text(self, value: str) -> str: ...
    def redact_value(self, value: Any) -> Any: ...
```

**Dependencies:** Configuration metadata and environment-variable names with credential semantics. Secret values remain in memory only.

### `octocoder.evals.events`

**Responsibility:** Parse NDJSON, assign missing run/sequence/turn metadata, pair tool calls with results, normalize volatile values, hash long results, and build `ToolTrace` records.

**Public Interface:**

```python
parse_event_line(line: str, context: EventContext) -> EvalEvent
normalize_events(events: list[EvalEvent], context: NormalizationContext) -> list[EvalEvent]
build_trajectory(events: list[EvalEvent], context: NormalizationContext) -> list[ToolTrace]
```

**Dependencies:** `models`, `redaction`.

Normalization replaces the resolved workspace with `$WORKSPACE`, uses `/` separators, replaces recognized generated IDs with stable indexed placeholders, sorts object keys, and excludes wall-clock fields from equality comparison. Raw redacted events are retained separately.

### `octocoder.evals.runners.base`

**Responsibility:** Define the runner boundary shared by real and scripted execution.

**Public Interface:**

```python
class EvalRunner(Protocol):
    async def run(self, request: RunRequest) -> RunnerOutput: ...
```

`RunnerOutput` contains process status, stdout events, stderr, final response, usage, provider/model identity, and errors before normalization.

### `octocoder.evals.runners.real`

**Responsibility:** Launch the current Python interpreter with `-m octocoder`, task prompt, permission mode, and `stream-json`; consume stdout/stderr concurrently; enforce timeout; terminate the process tree; and preserve a result for unsuccessful runs.

**Public Interface:**

```python
class RealRunner:
    async def run(self, request: RunRequest) -> RunnerOutput: ...
```

**Dependencies:** Existing OctoCoder CLI protocol, `base`, `models`.

Only an explicit environment allow-list plus required runtime variables is inherited. API credentials continue to be resolved by existing OctoCoder configuration; they are never copied into run artifacts.

### `octocoder.evals.runners.scripted`

**Responsibility:** Replay validated fixture events, apply declarative file writes/deletes beneath the workspace, simulate completion/failure/timeout, and return a normal `RunnerOutput` without network access.

**Public Interface:**

```python
class ScriptedRunner:
    async def run(self, request: RunRequest) -> RunnerOutput: ...
```

Scripted file effects reject absolute paths and parent traversal. They exist only to validate the framework and sample cases, not to emulate model reasoning.

### `octocoder.evals.graders.base`

**Responsibility:** Define a pluggable grader interface and shared finding format.

**Public Interface:**

```python
class Grader(Protocol):
    async def grade(self, context: GradeContext) -> DimensionScore: ...
```

### `octocoder.evals.graders.trajectory`

**Responsibility:** Evaluate required/forbidden calls, argument constraints, exact/subsequence order, total calls, failed calls, and identical-repeat limits. Produce a compact expected-versus-actual trajectory diff.

**Public Interface:**

```python
grade_trajectory(expected: TrajectoryExpectation, actual: list[ToolTrace]) -> DimensionScore
```

Tool matching is case-sensitive by default. Argument `glob` operates on normalized `/` paths, `matches` uses bounded regular expressions, and omitted argument constraints mean any arguments are accepted.

### `octocoder.evals.graders.outcome`

**Responsibility:** Execute declared checks after Agent completion and collect command output, file evidence, diff evidence, and workspace-boundary findings.

**Public Interface:**

```python
async def grade_outcomes(checks: list[OutcomeCheck], context: GradeContext) -> DimensionScore
```

### `octocoder.evals.scoring`

**Responsibility:** Run graders, derive efficiency/reliability/safety dimensions, apply hard-gate semantics, and produce the final `CaseScore`.

**Public Interface:**

```python
async def score_case(case: EvalCase, execution: ExecutionResult, workspace: WorkspaceArtifact) -> CaseScore
```

Efficiency uses declared call, turn, token, and duration ceilings. Reliability considers execution completion, malformed/unpaired events, tool failures, retries, and timeouts. Safety includes forbidden calls, path constraints, and workspace-boundary evidence.

### `octocoder.evals.artifacts`

**Responsibility:** Persist one immutable run directory and stable filenames after redaction.

**Public Interface:**

```python
write_run_artifacts(result: CaseRunResult, root: Path) -> Path
```

Each run directory contains:

```text
case.yaml
raw-events.jsonl
events.jsonl
trajectory.json
workspace.patch
stderr.txt
score.json
report.md
```

### `octocoder.evals.report`

**Responsibility:** Aggregate repeated runs and render schema-versioned JSON plus concise Markdown reports with evidence and artifact paths.

**Public Interface:**

```python
build_suite_report(suite: EvalSuite, runs: list[CaseRunResult]) -> SuiteReport
render_markdown(report: SuiteReport) -> str
```

### `octocoder.evals.compare`

**Responsibility:** Compare baseline and candidate suite reports, align cases and metrics, apply configured thresholds, and classify regression/improvement/unchanged results.

**Public Interface:**

```python
compare_reports(baseline: SuiteReport, candidate: SuiteReport, thresholds: ComparisonThresholds) -> ComparisonReport
```

Pass-to-fail and new hard-gate failures are unconditional regressions. Numeric metrics use absolute thresholds declared by the suite.

### `octocoder.evals.cli`

**Responsibility:** Provide `validate`, `run`, and `compare` subcommands, render progress, select runners, write reports, and return stable CI exit codes.

**Public Interface:**

```text
octocoder-eval validate [--case PATH | --suite NAME | --all]
octocoder-eval run [--case ID | --suite NAME | --all] [--repeat N]
                    [--execution real|scripted] [--output PATH]
                    [--keep-workspaces]
octocoder-eval compare --baseline REPORT --candidate REPORT
```

Exit codes are `0` for pass, `1` for evaluation failure, `2` for validation/framework failure, and `3` for threshold-breaking regression.

### Existing OctoCoder Stream Instrumentation

**Responsibility:** Enrich existing `stream-json` output without changing text-mode behavior.

The non-interactive entry point will attach monotonic sequence, current turn, run ID from `OCTOCODER_RUN_ID`, lead Agent ID, tool ID, permission request/decision, retry information, provider/model identity, and a final Multi-Agent trace summary when available. Thinking events remain observable raw events but are excluded from trajectory scoring.

## Module Interactions

### Validation Flow

1. CLI resolves an evaluation root.
2. Loader parses every selected YAML document into Pydantic models.
3. Loader verifies unique IDs, fixture containment, suite references, and compatible scripted/real fields.
4. Validation completes before any workspace or model process is created.

### Case Run Flow

1. Orchestrator creates a run ID and evaluation-owned run directory.
2. Workspace manager copies the fixture and creates an ephemeral Git baseline.
3. Runner receives the validated case, isolated workspace, run ID, and limits.
4. Real runner consumes OctoCoder NDJSON; scripted runner emits equivalent declared events.
5. Redactor sanitizes raw output before it is retained.
6. Event processor assigns stable metadata, normalizes values, and constructs tool trajectories.
7. Workspace manager captures final manifest and Git patch.
8. Outcome and trajectory graders run independently.
9. Scoring derives efficiency, safety, reliability, hard gates, and pass state.
10. Artifact writer persists the case result before optional workspace cleanup.

### Suite And Repetition Flow

1. Suite selector resolves a deterministic ordered case list.
2. Every repetition receives a separate workspace and run ID.
3. Individual results remain intact.
4. Reporter calculates count, pass rate, mean, median, minimum, maximum, and p95 where enough samples exist.
5. CLI writes `suite-result.json` and `report.md` and derives its exit status.

### Baseline Comparison Flow

1. Comparator validates schema compatibility.
2. Cases align by case ID and repetitions remain available as distributions.
3. Pass/fail transitions and hard-gate changes are checked first.
4. Dimension, usage, duration, turn, and call metrics are compared against suite thresholds.
5. Markdown includes changed metrics and normalized trajectory diffs for regressed cases.

## File Organization

```text
herness/
  octocoder/
    evals/
      __init__.py                 - package exports and schema version
      models.py                   - case, event, score, and report models
      loader.py                   - YAML discovery and validation
      workspace.py                - fixture isolation and Git diff capture
      redaction.py                - runtime secret redaction
      events.py                   - NDJSON parsing and trajectory normalization
      orchestration.py            - case and suite execution lifecycle
      scoring.py                  - dimension and hard-gate composition
      artifacts.py                - immutable run artifact persistence
      report.py                   - JSON aggregation and Markdown rendering
      compare.py                  - baseline/candidate comparison
      cli.py                      - octocoder-eval command entry
      runners/
        __init__.py
        base.py                   - shared runner protocol
        real.py                   - real OctoCoder subprocess runner
        scripted.py               - deterministic event/effect runner
      graders/
        __init__.py
        base.py                   - grader protocol and findings
        trajectory.py             - tool trajectory constraints and diffs
        outcome.py                - command/file/diff/boundary checks
  tests/
    test_eval_models.py
    test_eval_loader.py
    test_eval_workspace.py
    test_eval_events.py
    test_eval_scripted_runner.py
    test_eval_real_runner.py
    test_eval_trajectory_grader.py
    test_eval_outcome_grader.py
    test_eval_scoring.py
    test_eval_compare.py
    test_eval_cli.py
  pyproject.toml                  - octocoder-eval console entry point

evals/
  cases/
    smoke/
      successful-edit.yaml
      forbidden-tool.yaml
      order-violation.yaml
      outcome-failure.yaml
      execution-failure.yaml
  fixtures/
    successful-edit/
    safety-case/
  suites/
    smoke.yaml
    nightly.yaml
    release.yaml
  baselines/
    .gitkeep
  runs/
    .gitignore

specs/agent-evaluation/
  spec.md
  plan.md
  task.md
  checklist.md
```

## Technical Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| Execution architecture | Subprocess for real runs, in-process scripted runner | Real runs exercise the shipped CLI boundary; deterministic tests stay fast and network-free. |
| Shared evaluation pipeline | Both runners return one `RunnerOutput` | Prevents scripted tests from validating a different scorer than real runs use. |
| Definition format | YAML validated by Pydantic | Matches existing project dependencies and provides readable field-level errors. |
| Workspace isolation | Copied fixture plus ephemeral Git baseline | Cross-platform, protects source fixtures, and gives deterministic patch evidence without mutating the original repository. |
| Trajectory default | Constraint-based with optional subsequence/exact modes | Real Agents can take multiple valid paths; strict matching remains available for protocol and safety cases. |
| Argument matching | Small typed operator set over dotted paths | Covers practical checks without introducing an unsafe or opaque expression language. |
| Outcome priority | Deterministic artifact and command checks | Final behavior is more authoritative than prose or model self-reporting. |
| Safety scoring | Hard gates plus separate safety dimension | A weighted aggregate must never hide a severe violation. |
| Reasoning data | Do not score Thinking text | Avoids unstable chain-of-thought coupling; only observable behavior is evaluated. |
| Secret handling | Redact before persistence, retain known values only in memory | Allows useful diagnostics without writing credentials to artifacts. |
| Reports | Versioned JSON and generated Markdown | JSON supports CI and future dashboards; Markdown is reviewable immediately. |
| Baseline storage | Store complete suite reports; preserve repeated real runs | Enables future variance analysis and prevents averages from hiding instability. |
| CI integration | Stable exit codes, no dashboard dependency | Keeps the MVP useful in local development and GitHub Actions. |
| External benchmarks | Deferred | Internal capabilities such as MCP, permissions, memory, Multi-Agent, and voice need product-specific cases first. |

## Requirements Coverage

| Requirements | Design Coverage |
| --- | --- |
| F1-F2, N1, N5 | `models`, `loader`, versioned YAML cases and suites |
| F3, N4 | `workspace` ownership markers, fixture copy, Git baseline |
| F4-F5, F14, N3, N6 | shared runner protocol, `real`, `scripted`, orchestration |
| F6-F8, N2, N8-N10 | stream instrumentation, `events`, `redaction`, run artifacts |
| F9-F10, F16 | typed trajectory expectations and trajectory grader |
| F11-F13 | outcome graders, scoring dimensions, hard gates |
| F15 | baseline comparator and thresholds |
| F17-F18 | artifact writer, report renderer, CLI exit codes |
| F19-F20 | deterministic smoke cases and framework test suite |
