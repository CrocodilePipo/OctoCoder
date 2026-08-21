# OctoCoder Context Management Evaluation Tasks

> Metric-model amendment (2026-08-21): tasks referring to weighted context scores,
> relative token error, or compression ratios were implemented using check counts,
> semantic similarity, and absolute token/compaction measurements.

## File List

| Action | File | Responsibility |
| --- | --- | --- |
| Modify | `herness/octocoder/evals/models.py` | Context stages, expectations, events, checkpoints, metrics, thresholds, and optional execution fields |
| Modify | `herness/octocoder/evals/loader.py` | Context stage/reference validation and deterministic selection |
| Modify | `herness/octocoder/conversation.py` | Usage-anchor context observations |
| Modify | `herness/octocoder/context/manager.py` | Spill and compaction lifecycle observations |
| Modify | `herness/octocoder/memory/session.py` | Resume lifecycle observations and boundary identity |
| Modify | `herness/octocoder/agent.py` | Context Agent events and observer ownership |
| Create | `herness/octocoder/noninteractive.py` | Persistent reusable non-interactive Agent session |
| Modify | `herness/octocoder/__main__.py` | Delegate single prompts and emit enriched context events |
| Modify | `herness/octocoder/evals/events.py` | Context event normalization, transition checks, and checkpoint extraction |
| Create | `herness/octocoder/evals/context_worker.py` | Multi-stage real scenario subprocess worker |
| Create | `herness/octocoder/evals/runners/context_scripted.py` | Offline deterministic multi-stage context replay |
| Create | `herness/octocoder/evals/runners/context_real.py` | Persistent real context scenario runner |
| Modify | `herness/octocoder/evals/runners/__init__.py` | Context runner exports |
| Modify | `herness/octocoder/evals/orchestration.py` | Conditional context runner selection and lifecycle |
| Create | `herness/octocoder/evals/graders/matching.py` | Shared deterministic typed-value matching |
| Modify | `herness/octocoder/evals/graders/trajectory.py` | Consume shared matching helpers |
| Create | `herness/octocoder/evals/graders/context.py` | Context subscores, metrics, findings, and hard gates |
| Modify | `herness/octocoder/evals/graders/__init__.py` | Context grader exports |
| Modify | `herness/octocoder/evals/scoring.py` | Conditional sixth context dimension |
| Modify | `herness/octocoder/evals/artifacts.py` | Context timeline, checkpoint, and metrics artifacts |
| Modify | `herness/octocoder/evals/report.py` | Context report sections and suite aggregates |
| Modify | `herness/octocoder/evals/compare.py` | Context regression thresholds and classifications |
| Modify | `herness/octocoder/evals/cli.py` | Context validation/run options and statuses |
| Create | `herness/tests/test_context_observer.py` | Production observation tests |
| Create | `herness/tests/test_noninteractive_session.py` | Persistent turn and compatibility tests |
| Create | `herness/tests/test_eval_context_models.py` | Context schema and reference tests |
| Create | `herness/tests/test_eval_context_events.py` | Context normalization and transition tests |
| Create | `herness/tests/test_eval_context_scripted_runner.py` | Deterministic multi-stage runner tests |
| Create | `herness/tests/test_eval_context_real_runner.py` | Local fake-Agent multi-stage subprocess tests |
| Create | `herness/tests/test_eval_context_grader.py` | All context subscore and hard-gate tests |
| Create | `herness/tests/test_eval_context_artifacts.py` | Context artifact and redaction tests |
| Create | `herness/tests/test_eval_context_compare.py` | Context baseline comparison tests |
| Create | `herness/tests/test_eval_context_cli.py` | Context CLI and exit-code tests |
| Create | `evals/fixtures/context-project/*` | Immutable context evaluation fixture |
| Create | `evals/cases/context/*.yaml` | Passing and failure-reference context cases |
| Create | `evals/suites/context-smoke.yaml` | Mandatory offline context gate |
| Create | `evals/suites/context-nightly.yaml` | Repeated optional real-model probes |
| Modify | `.github/workflows/evals.yml` | Context smoke CI and opt-in real suite |
| Modify | `README.md` | Chinese context EDD documentation |
| Modify | `README.en.md` | English context EDD documentation |
| Modify | `README.zh-CN.md` | Chinese locale context EDD documentation |

## T1: Define Context Evaluation Schemas

**Files:** `herness/octocoder/evals/models.py`, `herness/tests/test_eval_context_models.py`

**Dependencies:** None

**Steps:**
1. Add context stage, fact, instruction, state, token, compression, resume, and top-level expectation models.
2. Add lifecycle event, checkpoint, subscore, and metrics models.
3. Add optional context fields to case and execution result models.
4. Add `context` to dimension names while preserving non-context case defaults.
5. Extend comparison thresholds with optional context regression thresholds.
6. Validate IDs, stage actions, prompt requirements, checkpoint references, unique identifiers, ranges, and mutually exclusive literal/regex fields.

**Verification:** Run `uv run pytest tests/test_eval_context_models.py tests/test_eval_models.py -q` and expect valid schemas plus unsupported references and malformed fields to be covered.

## T2: Validate Context Catalog References

**Files:** `herness/octocoder/evals/loader.py`, `herness/tests/test_eval_context_models.py`

**Dependencies:** T1

**Steps:**
1. Validate every required/forbidden checkpoint reference against declared stages.
2. Validate resume before/after checkpoints and fact/instruction IDs.
3. Reject context cases with no observable checkpoint or probe stage.
4. Preserve deterministic discovery and compatibility for non-context cases.

**Verification:** Run `uv run pytest tests/test_eval_context_models.py tests/test_eval_loader.py -q` and expect invalid catalogs to fail before runner selection.

## T3: Define The Production Context Observation Boundary

**Files:** `herness/octocoder/context/manager.py`, `herness/octocoder/conversation.py`, `herness/tests/test_context_observer.py`

**Dependencies:** T1

**Steps:**
1. Define lifecycle observation records and a no-op observer protocol.
2. Add optional observer arguments to token anchoring, tool-result budgeting, and compaction paths.
3. Emit usage-anchor observations with estimate/provider/message-count data.
4. Emit spill observations with bounded pre/post sizes, counts, and replacement IDs or hashes.
5. Emit compaction started/skipped/completed/failed observations with thresholds and bounded metrics.
6. Ensure no full summary, secret, or unbounded tool output is included.

**Verification:** Run `uv run pytest tests/test_context_observer.py tests/test_context.py tests/test_replacement_state.py -q` and expect existing behavior plus complete event evidence.

## T4: Instrument Session Resume

**Files:** `herness/octocoder/memory/session.py`, `herness/tests/test_context_observer.py`, `herness/tests/test_memory.py`

**Dependencies:** T3

**Steps:**
1. Derive a stable non-secret boundary identity from persisted compact boundaries.
2. Emit restored message, replacement, summary, and retained-tail counts.
3. Distinguish successful resume, degraded malformed-boundary recovery, and missing session.
4. Preserve existing session record compatibility.

**Verification:** Run `uv run pytest tests/test_context_observer.py tests/test_memory.py -q` and expect all compact-boundary round trips to remain valid.

## T5: Emit Context Agent Events

**Files:** `herness/octocoder/agent.py`, `herness/octocoder/__main__.py`, `herness/tests/test_context_observer.py`, `herness/tests/test_stream_json_metadata.py`

**Dependencies:** T3, T4

**Steps:**
1. Let each Agent own an observer that translates lifecycle observations into Agent events.
2. Attach run, stage, turn, Agent, trace, and checkpoint metadata when available.
3. Emit backward-compatible `type=context` NDJSON events in structured mode.
4. Preserve current `compact` notification and text output behavior.
5. Redact and bound all payloads before writing stdout.

**Verification:** Run `uv run pytest tests/test_context_observer.py tests/test_stream_json_metadata.py tests/test_agent.py -q` and expect ordered metadata and text-mode compatibility.

## T6: Extract A Persistent Non-Interactive Session

**Files:** `herness/octocoder/noninteractive.py`, `herness/octocoder/__main__.py`, `herness/tests/test_noninteractive_session.py`, `herness/tests/test_stream_json_metadata.py`

**Dependencies:** T5

**Steps:**
1. Move non-interactive Agent, registry, task, trace, team, worktree, and conversation construction into a reusable session object.
2. Implement repeated `run_turn` calls over one conversation.
3. Keep cumulative usage, tool events, and stage-aware event emission.
4. Implement checkpoint capture and controlled persist/recreate/resume.
5. Make the existing `-p` path delegate to one session and one turn.
6. Keep team completion handling and process cleanup behavior.

**Verification:** Run `uv run pytest tests/test_noninteractive_session.py tests/test_stream_json_metadata.py tests/test_agent.py tests/test_teams.py -q` and expect single-turn output compatibility plus multi-turn continuity.

## T7: Parse And Normalize Context Events

**Files:** `herness/octocoder/evals/events.py`, `herness/tests/test_eval_context_events.py`

**Dependencies:** T1, T5

**Steps:**
1. Extract context lifecycle events from the shared raw stream.
2. Normalize paths, generated IDs, boundary identities, timestamps, hashes, and key order.
3. Validate started/completed/failed transition pairing.
4. Validate stage/checkpoint references and resumed boundary identities.
5. Build structured checkpoints from scripted payloads and real probe markers.
6. Preserve malformed transitions as reliability findings.

**Verification:** Run `uv run pytest tests/test_eval_context_events.py tests/test_eval_events.py -q` and expect cross-platform equivalent streams to normalize identically.

## T8: Implement Shared Typed Matching

**Files:** `herness/octocoder/evals/graders/matching.py`, `herness/octocoder/evals/graders/trajectory.py`, `herness/tests/test_eval_context_grader.py`, `herness/tests/test_eval_trajectory_grader.py`

**Dependencies:** T1

**Steps:**
1. Extract dotted-path lookup and equals/contains/regex/glob/exists operators.
2. Bound regex size and evidence rendering.
3. Preserve existing trajectory matching behavior.
4. Reuse the helpers for fact and state checkpoint assertions.

**Verification:** Run `uv run pytest tests/test_eval_trajectory_grader.py tests/test_eval_context_grader.py -q` and expect the shared operator matrix to pass.

## T9: Implement The Scripted Context Runner

**Files:** `herness/octocoder/evals/runners/context_scripted.py`, `herness/octocoder/evals/runners/__init__.py`, `herness/tests/test_eval_context_scripted_runner.py`

**Dependencies:** T1, T2, T7

**Steps:**
1. Replay stage-tagged lifecycle events, probe checkpoints, tool events, and file effects in declared stage order.
2. Enforce stage, turn, event, and timeout limits.
3. Simulate resume, compaction failure, malformed probe, and timeout outcomes.
4. Reuse safe workspace path validation and redaction.
5. Produce the existing `RunnerOutput` contract with context evidence included in raw events.

**Verification:** Run `uv run pytest tests/test_eval_context_scripted_runner.py -q` twice without credentials and expect equivalent normalized outputs.

## T10: Implement The Real Context Worker And Runner

**Files:** `herness/octocoder/evals/context_worker.py`, `herness/octocoder/evals/runners/context_real.py`, `herness/octocoder/evals/runners/__init__.py`, `herness/tests/test_eval_context_real_runner.py`

**Dependencies:** T6, T7

**Steps:**
1. Launch a subprocess worker using the existing restricted environment and process-tree timeout controls.
2. Keep one persistent non-interactive session across setup, pressure, checkpoint, and probe stages.
3. Restart through session persistence for resume stages.
4. Parse structured probe markers without an LLM judge.
5. Stream stdout/stderr concurrently and retain partial context evidence on failure.
6. Test against a controlled local fake Agent/provider with no network.

**Verification:** Run `uv run pytest tests/test_eval_context_real_runner.py -q` and expect multi-stage continuity, resume, malformed probe, failure, and timeout scenarios to pass offline.

## T11: Select Context Runners In Orchestration

**Files:** `herness/octocoder/evals/orchestration.py`, `herness/tests/test_eval_context_scripted_runner.py`, `herness/tests/test_eval_context_real_runner.py`

**Dependencies:** T9, T10

**Steps:**
1. Select context runners only when a case declares context expectations.
2. Preserve existing runner selection for all current cases.
3. Pass stage limits and context identity through `RunRequest`.
4. Ensure context evidence is normalized before grading and persisted before cleanup.
5. Convert worker/protocol failures into explicit framework or Agent statuses.

**Verification:** Run both context runner tests plus `tests/test_eval_cli.py` and confirm existing smoke remains unchanged.

## T12: Implement Retention And Instruction Grading

**Files:** `herness/octocoder/evals/graders/context.py`, `herness/tests/test_eval_context_grader.py`

**Dependencies:** T7, T8

**Steps:**
1. Match required facts at declared checkpoints.
2. Detect forbidden stale facts and superseded instructions.
3. Grade active instruction presence and priority.
4. Calculate retention, instruction-adherence, and contamination rates.
5. Attach the first failing stage/checkpoint and concise expected/actual evidence.

**Verification:** Run `uv run pytest tests/test_eval_context_grader.py -q` and expect pass/fail coverage for facts, corrections, priorities, and contamination.

## T13: Implement Continuity And Resume Grading

**Files:** `herness/octocoder/evals/graders/context.py`, `herness/tests/test_eval_context_grader.py`

**Dependencies:** T12

**Steps:**
1. Grade required files, pending work, known failures, and next action.
2. Verify complete retained tool-use/tool-result pairs.
3. Compare declared before/after resume fields.
4. Calculate continuity and resume-consistency rates.
5. Apply hard gates to broken pairings and declared resume divergence.

**Verification:** Run context grader tests and expect the complete state/resume matrix to pass.

## T14: Implement Token And Compression Grading

**Files:** `herness/octocoder/evals/graders/context.py`, `herness/tests/test_eval_context_grader.py`

**Dependencies:** T7, T12

**Steps:**
1. Calculate absolute/relative estimate error at provider-shaped anchors.
2. Detect early, late, missing, and repeated compaction triggers.
3. Calculate reclaimed tokens, compression ratio, retained-tail maximum, spill savings, and compaction count.
4. Enforce declared safety margins and compression limits.
5. Exclude unavailable optional metrics from the denominator.

**Verification:** Run context grader tests and expect token boundary, missing-anchor, ineffective-compaction, and excessive-compaction examples.

## T15: Compose The Conditional Context Dimension

**Files:** `herness/octocoder/evals/scoring.py`, `herness/octocoder/evals/graders/__init__.py`, `herness/tests/test_eval_context_grader.py`, `herness/tests/test_eval_scoring.py`

**Dependencies:** T12-T14

**Steps:**
1. Register the context grader through the existing grader boundary.
2. Add the weighted context dimension only for context cases.
3. Preserve five dimensions and identical scores for non-context cases.
4. Apply context hard gates independently of the weighted score.
5. Distinguish context expectation failure from execution and framework failures in findings.

**Verification:** Run `uv run pytest tests/test_eval_context_grader.py tests/test_eval_scoring.py -q` and expect hard-gate override plus non-context score snapshots.

## T16: Persist Context Artifacts

**Files:** `herness/octocoder/evals/artifacts.py`, `herness/tests/test_eval_context_artifacts.py`, `herness/tests/test_eval_artifacts.py`

**Dependencies:** T7, T15

**Steps:**
1. Write normalized context events, checkpoints, and metrics using stable filenames.
2. Generate context files only for context cases.
3. Redact secrets and bound probe/summary evidence before atomic writes.
4. Reject overwrite and scan every new serialized artifact for test secrets.

**Verification:** Run both artifact test modules and expect the context layout, backward-compatible standard layout, and zero secret leakage.

## T17: Render Context Reports

**Files:** `herness/octocoder/evals/report.py`, `herness/tests/test_eval_context_artifacts.py`, `herness/tests/test_eval_report.py`

**Dependencies:** T15, T16

**Steps:**
1. Add checkpoint, subscore, token, compression, and hard-gate tables.
2. Identify the first stage where each context failure appears.
3. Link all context artifacts from case Markdown.
4. Aggregate repetition means, medians, ranges, and p95 where applicable.
5. Keep volatile IDs out of deterministic report sections.

**Verification:** Run context artifact/report tests and expect deterministic Markdown for identical scripted cases.

## T18: Compare Context Baselines

**Files:** `herness/octocoder/evals/compare.py`, `herness/tests/test_eval_context_compare.py`, `herness/tests/test_eval_compare.py`

**Dependencies:** T15, T17

**Steps:**
1. Compare context score and every declared context threshold.
2. Treat pass-to-fail, missing checkpoints, and new context hard gates as unconditional regressions.
3. Classify retention, resume, token, compression, and count changes.
4. Render changed checkpoints and concise evidence.
5. Preserve comparison behavior for reports without context metrics.

**Verification:** Run both comparison test modules and expect improvement, regression, unchanged, and compatibility cases.

## T19: Extend Context CLI Behavior

**Files:** `herness/octocoder/evals/cli.py`, `herness/tests/test_eval_context_cli.py`

**Dependencies:** T11, T17, T18

**Steps:**
1. Validate context cases and references through existing commands.
2. Run context cases through normal case/suite/all selection.
3. Keep real context execution opt-in through case tags/suite selection and existing execution override.
4. Preserve exit codes `0`, `1`, `2`, and `3`.
5. Print context artifact locations without mixing progress into JSON.

**Verification:** Run `uv run pytest tests/test_eval_context_cli.py tests/test_eval_cli.py -q` and exercise help, validation, smoke, failure, framework, and regression paths.

## T20: Add Deterministic Context Fixtures And Cases

**Files:** `evals/fixtures/context-project/*`, `evals/cases/context/*.yaml`, `evals/suites/context-smoke.yaml`, `evals/suites/context-nightly.yaml`

**Dependencies:** T19

**Steps:**
1. Add a passing retention/instruction/continuity/resume scripted case.
2. Add failure references for critical fact loss, stale contamination, instruction priority, resume divergence, token drift, and ineffective compaction.
3. Keep failure references directly runnable but outside passing smoke selection.
4. Define deterministic context smoke thresholds.
5. Define repeated nightly selection with real probes opt-in by configuration.

**Verification:** Run `uv run octocoder-eval validate --all`, run `context-smoke`, and directly run every failure reference with expected exit `1`.

## T21: Add CI And Documentation

**Files:** `.github/workflows/evals.yml`, `README.md`, `README.en.md`, `README.zh-CN.md`

**Dependencies:** T20

**Steps:**
1. Add context smoke to the deterministic PR job.
2. Add manual/scheduled real context entry guarded by repository configuration.
3. Document multi-stage authoring, facts, instructions, checkpoints, metrics, artifacts, thresholds, and exit codes.
4. Document the rule that context behavior fixes add a reproducing context case first.
5. Explain that real probes may incur provider cost and are not mandatory locally.

**Verification:** Parse workflow YAML, run documented commands, and compare all options with CLI help.

## T22: Run Full Acceptance

**Files:** All files above

**Dependencies:** T1-T21

**Steps:**
1. Run all context-evaluation tests without provider credentials or network.
2. Run the complete existing backend suite.
3. Run context smoke twice and compare normalized timelines, checkpoints, metrics, scores, and deterministic report sections.
4. Run all failure references and verify expected hard-gate evidence.
5. Run simulated context baseline comparison and verify regression exit `3`.
6. Scan generated artifacts for configured and fake secrets.
7. Run one local fake-Agent real scenario end to end.
8. Run a configured real-provider probe only when explicitly opted in; otherwise record it as optional and unexecuted.

**Verification:** Run `uv run pytest -q`, `uv run octocoder-eval run --suite context-smoke`, the comparison command, compilation, YAML parsing, secret scan, and `git diff --check`; expect all mandatory checks to pass.

## Execution Order

```text
T1 -> T2
T1 -> T3 -> T4 -> T5 -> T6
T1 + T5 -> T7
T1 -> T8
T2 + T7 -> T9
T6 + T7 -> T10
T9 + T10 -> T11
T7 + T8 -> T12 -> T13 -> T14 -> T15
T7 + T15 -> T16 -> T17 -> T18
T11 + T17 + T18 -> T19 -> T20 -> T21 -> T22
```
