# OctoCoder Agent Evaluation MVP Tasks

> Metric-model amendment (2026-08-21): tasks referring to numeric scores,
> pass rates, or `score.json` were implemented using verdicts, check counts,
> failed-run counts, and absolute resource measurements instead. Percentages are
> used only for semantic similarity.

## File List

| Action | File | Responsibility |
| --- | --- | --- |
| Create | `herness/octocoder/evals/__init__.py` | Evaluation package exports and schema version |
| Create | `herness/octocoder/evals/models.py` | Case, suite, event, trajectory, score, and report schemas |
| Create | `herness/octocoder/evals/loader.py` | YAML discovery, validation, and suite selection |
| Create | `herness/octocoder/evals/workspace.py` | Fixture isolation, ownership validation, manifests, and Git patches |
| Create | `herness/octocoder/evals/redaction.py` | Secret discovery and recursive artifact redaction |
| Create | `herness/octocoder/evals/events.py` | NDJSON parsing, event normalization, tool-result pairing, trajectory creation |
| Create | `herness/octocoder/evals/orchestration.py` | Case/suite execution lifecycle and cleanup ownership |
| Create | `herness/octocoder/evals/scoring.py` | Dimension scoring and hard-gate composition |
| Create | `herness/octocoder/evals/artifacts.py` | Run artifact persistence |
| Create | `herness/octocoder/evals/report.py` | Suite aggregation and Markdown generation |
| Create | `herness/octocoder/evals/compare.py` | Baseline/candidate comparison |
| Create | `herness/octocoder/evals/cli.py` | Validate, run, and compare commands with CI exit codes |
| Create | `herness/octocoder/evals/runners/__init__.py` | Runner exports |
| Create | `herness/octocoder/evals/runners/base.py` | Shared runner protocol and request/output structures |
| Create | `herness/octocoder/evals/runners/scripted.py` | Deterministic events and workspace effects |
| Create | `herness/octocoder/evals/runners/real.py` | Real OctoCoder subprocess execution |
| Create | `herness/octocoder/evals/graders/__init__.py` | Grader exports |
| Create | `herness/octocoder/evals/graders/base.py` | Shared grader interface and findings |
| Create | `herness/octocoder/evals/graders/trajectory.py` | Tool constraint and order grading |
| Create | `herness/octocoder/evals/graders/outcome.py` | Command, file, diff, and boundary grading |
| Modify | `herness/octocoder/__main__.py` | Enrich non-interactive structured events |
| Modify | `herness/pyproject.toml` | Register `octocoder-eval` console command |
| Create | `herness/tests/test_eval_models.py` | Schema and malformed-input tests |
| Create | `herness/tests/test_eval_loader.py` | Discovery and suite-resolution tests |
| Create | `herness/tests/test_eval_workspace.py` | Isolation, patch, and safe-cleanup tests |
| Create | `herness/tests/test_eval_redaction.py` | Credential-redaction tests |
| Create | `herness/tests/test_eval_events.py` | Event normalization and trajectory tests |
| Create | `herness/tests/test_eval_scripted_runner.py` | Deterministic runner tests |
| Create | `herness/tests/test_eval_real_runner.py` | Subprocess protocol and failure-capture tests |
| Create | `herness/tests/test_eval_trajectory_grader.py` | Every trajectory constraint pass/fail test |
| Create | `herness/tests/test_eval_outcome_grader.py` | Every outcome checker pass/fail test |
| Create | `herness/tests/test_eval_scoring.py` | Dimension and hard-gate tests |
| Create | `herness/tests/test_eval_artifacts.py` | Artifact layout and secret-free persistence tests |
| Create | `herness/tests/test_eval_report.py` | Aggregate and Markdown tests |
| Create | `herness/tests/test_eval_compare.py` | Regression/improvement/unchanged tests |
| Create | `herness/tests/test_eval_cli.py` | CLI selection and exit-code tests |
| Create | `herness/tests/test_stream_json_metadata.py` | Structured-event compatibility tests |
| Create | `evals/cases/smoke/*.yaml` | Deterministic reference and failure cases |
| Create | `evals/fixtures/*` | Immutable evaluation fixture projects |
| Create | `evals/suites/{smoke,nightly,release}.yaml` | Initial suite definitions |
| Create | `evals/baselines/.gitkeep` | Baseline directory ownership |
| Create | `evals/runs/.gitignore` | Ignore generated run artifacts |
| Create | `.github/workflows/evals.yml` | Deterministic PR gate and scheduled/manual evaluation entry |
| Modify | `README.zh-CN.md` | Chinese EDD usage documentation |
| Modify | `README.md` | English EDD usage documentation |

## T1: Define Versioned Evaluation Schemas

**Files:** `herness/octocoder/evals/__init__.py`, `herness/octocoder/evals/models.py`, `herness/tests/test_eval_models.py`

**Dependencies:** None

**Steps:**
1. Define enums and Pydantic models for cases, suites, limits, scripted effects, expectations, events, trajectories, findings, scores, execution results, suite reports, and comparisons.
2. Add field validation for IDs, relative paths, positive limits, scripted/real compatibility, argument operators, and unique check identifiers.
3. Expose schema version `1` from the package.
4. Add valid and invalid schema tests, including traversal and incompatible execution definitions.

**Verification:** Run `uv run pytest tests/test_eval_models.py -q` from `herness` and expect all schema tests to pass.

## T2: Implement Case And Suite Loading

**Files:** `herness/octocoder/evals/loader.py`, `herness/tests/test_eval_loader.py`

**Dependencies:** T1

**Steps:**
1. Load one case or suite from YAML with field-level validation errors.
2. Discover cases recursively under the evaluation root and reject duplicate IDs.
3. Resolve suites by explicit case IDs and tags with deterministic ordering and deduplication.
4. Verify referenced fixtures remain beneath `evals/fixtures` and referenced cases exist.

**Verification:** Run `uv run pytest tests/test_eval_loader.py -q` and expect discovery, selection, and malformed-input tests to pass.

## T3: Build Safe Isolated Workspaces

**Files:** `herness/octocoder/evals/workspace.py`, `herness/tests/test_eval_workspace.py`

**Dependencies:** T1

**Steps:**
1. Copy a fixture into a run-owned workspace without copying source Git metadata.
2. Write a run-ID ownership marker and initialize an ephemeral Git baseline with local commit identity.
3. Capture before/after manifests and a binary-safe Git patch including new files.
4. Reject fixture traversal, symlink escape, mismatched markers, and cleanup outside the configured run root.
5. Support retaining the workspace for debugging or verified cleanup after artifacts are written.

**Verification:** Run `uv run pytest tests/test_eval_workspace.py -q` and expect fixture immutability, patch capture, and destructive-operation guards to pass.

## T4: Implement Secret Redaction

**Files:** `herness/octocoder/evals/redaction.py`, `herness/tests/test_eval_redaction.py`

**Dependencies:** T1

**Steps:**
1. Discover known credential values from resolved provider configuration and credential-named environment variables without persisting the source values.
2. Redact secrets recursively in strings, mappings, lists, raw stderr, events, diffs, and reports.
3. Ignore empty and trivially short values to avoid destructive over-redaction.
4. Add tests using known model, voice, token, and password-shaped test secrets.

**Verification:** Run `uv run pytest tests/test_eval_redaction.py -q` and verify no test secret appears in persisted-shaped values.

## T5: Enrich The Existing Stream-JSON Protocol

**Files:** `herness/octocoder/__main__.py`, `herness/tests/test_stream_json_metadata.py`

**Dependencies:** T1

**Steps:**
1. Add a reusable emitter that assigns event sequence, run ID, elapsed timestamp, current turn, and lead Agent identity.
2. Preserve existing event types and fields while adding metadata so current consumers remain compatible.
3. Emit permission request and non-interactive decision events.
4. Add provider/model identity and final Multi-Agent trace summary to the result event without exposing credentials.
5. Test ordering, metadata, permission visibility, and text-mode non-regression with a scripted Agent stream.

**Verification:** Run `uv run pytest tests/test_stream_json_metadata.py tests/test_agent.py -q` and expect protocol and Agent tests to pass.

## T6: Parse And Normalize Events

**Files:** `herness/octocoder/evals/events.py`, `herness/tests/test_eval_events.py`

**Dependencies:** T1, T4, T5

**Steps:**
1. Parse NDJSON while preserving malformed lines as framework findings instead of crashing silently.
2. Fill missing run, sequence, turn, and Agent metadata for compatible older events.
3. Normalize workspace paths, separators, generated IDs, object-key order, timestamps, and long tool results.
4. Pair tool-use and tool-result events by ID and report missing halves.
5. Build canonical `ToolTrace` entries and stable identical-call signatures.

**Verification:** Run `uv run pytest tests/test_eval_events.py -q` and expect equivalent Windows/Linux paths and differing generated IDs to normalize identically.

## T7: Define The Runner Boundary

**Files:** `herness/octocoder/evals/runners/__init__.py`, `herness/octocoder/evals/runners/base.py`

**Dependencies:** T1

**Steps:**
1. Define `RunRequest`, `RunnerOutput`, and the asynchronous runner protocol.
2. Include limits, workspace, prompt, permission mode, environment, run ID, and execution identity.
3. Define common status mapping for completion, Agent failure, framework failure, and timeout.

**Verification:** Run `uv run pytest tests/test_eval_models.py -q` and type/import smoke checks through the test module.

## T8: Implement The Deterministic Scripted Runner

**Files:** `herness/octocoder/evals/runners/scripted.py`, `herness/tests/test_eval_scripted_runner.py`

**Dependencies:** T1, T3, T7

**Steps:**
1. Replay declared events in source order using the shared runner output contract.
2. Apply validated write/delete effects only beneath the isolated workspace.
3. Simulate completed, failed, and timeout outcomes without network access.
4. Reject absolute, parent-traversal, and symlink-escape file effects.
5. Verify repeated execution produces equivalent runner output apart from excluded metadata.

**Verification:** Run `uv run pytest tests/test_eval_scripted_runner.py -q` and expect all tests to pass without credentials or network.

## T9: Implement The Real OctoCoder Runner

**Files:** `herness/octocoder/evals/runners/real.py`, `herness/tests/test_eval_real_runner.py`

**Dependencies:** T3, T4, T5, T7

**Steps:**
1. Launch `sys.executable -m octocoder` with prompt, permission mode, and `stream-json` in the isolated workspace.
2. Pass the run ID and a restricted environment while preserving required runtime and provider configuration discovery.
3. Consume stdout and stderr concurrently to avoid pipe deadlocks.
4. Enforce timeout and terminate the process tree using platform-appropriate non-shell APIs.
5. Return partial events and diagnostics for non-zero exits, malformed output, and timeout.
6. Test with a local fake Python module/process rather than a model provider.

**Verification:** Run `uv run pytest tests/test_eval_real_runner.py -q` and expect subprocess success, failure, malformed-stream, and timeout cases to pass offline.

## T10: Implement Trajectory Matching And Diffs

**Files:** `herness/octocoder/evals/graders/__init__.py`, `herness/octocoder/evals/graders/base.py`, `herness/octocoder/evals/graders/trajectory.py`, `herness/tests/test_eval_trajectory_grader.py`

**Dependencies:** T1, T6

**Steps:**
1. Implement tool-name and dotted-argument matching for equals, contains, bounded regex, glob, and exists operators.
2. Grade required, forbidden, minimum, maximum, total-call, failed-call, and repeated-identical-call constraints.
3. Implement exact and subsequence order comparison over normalized tool calls.
4. Produce findings and concise expected/actual trajectory diffs for every failure class.
5. Calculate trajectory and safety evidence without allowing weighted scores to override forbidden behavior.

**Verification:** Run `uv run pytest tests/test_eval_trajectory_grader.py -q` and expect automated passing and failing examples for every AC6 constraint.

## T11: Implement Outcome Graders

**Files:** `herness/octocoder/evals/graders/outcome.py`, `herness/tests/test_eval_outcome_grader.py`

**Dependencies:** T1, T3, T7

**Steps:**
1. Implement command checks using argument arrays, no shell, bounded execution time, and captured evidence.
2. Implement file exists, file absent, literal/regex content, and Git-diff content checks.
3. Implement workspace-boundary checks using normalized path-bearing tool arguments and workspace evidence.
4. Respect each check's weight and hard-gate declaration.
5. Bound captured command output and redact evidence before returning it.

**Verification:** Run `uv run pytest tests/test_eval_outcome_grader.py -q` and expect pass/fail, timeout, path, and hard-gate cases to pass.

## T12: Compose Scores And Hard Gates

**Files:** `herness/octocoder/evals/scoring.py`, `herness/tests/test_eval_scoring.py`

**Dependencies:** T10, T11

**Steps:**
1. Invoke outcome and trajectory graders independently.
2. Derive efficiency from limits and actual duration, turns, calls, failed calls, and tokens.
3. Derive reliability from completion status, retries, malformed events, unpaired tool events, and timeouts.
4. Compose separate outcome, trajectory, efficiency, safety, and reliability dimensions.
5. Apply unconditional failure for framework errors, required-check failure, and hard-gate findings.

**Verification:** Run `uv run pytest tests/test_eval_scoring.py -q` and verify a high numerical score cannot override a hard-gate failure.

## T13: Persist Immutable Run Artifacts

**Files:** `herness/octocoder/evals/artifacts.py`, `herness/tests/test_eval_artifacts.py`

**Dependencies:** T3, T4, T6, T12

**Steps:**
1. Create one run directory only beneath the configured artifact root.
2. Persist case snapshot, redacted raw events, normalized events, trajectory, patch, stderr, and score using stable filenames.
3. Write files atomically and reject accidental overwrite of an existing run ID.
4. Scan serialized artifacts for registered test secrets before declaring the write successful.

**Verification:** Run `uv run pytest tests/test_eval_artifacts.py -q` and verify the required artifact layout and zero secret leakage.

## T14: Aggregate And Render Reports

**Files:** `herness/octocoder/evals/report.py`, `herness/tests/test_eval_report.py`

**Dependencies:** T12, T13

**Steps:**
1. Aggregate repetitions without discarding individual results.
2. Calculate pass rate, mean, median, min, max, and p95 when sample count permits.
3. Render versioned suite JSON and concise Markdown tables.
4. Include hard-gate evidence, failed constraints, usage, duration, and relative artifact paths.
5. Keep volatile timestamps and run IDs out of deterministic equality sections.

**Verification:** Run `uv run pytest tests/test_eval_report.py -q` and expect deterministic snapshots for identical scripted inputs.

## T15: Implement Baseline Comparison

**Files:** `herness/octocoder/evals/compare.py`, `herness/tests/test_eval_compare.py`

**Dependencies:** T14

**Steps:**
1. Validate baseline/candidate schema compatibility and align case IDs.
2. Treat pass-to-fail, missing candidate cases, and new hard-gate failures as unconditional regressions.
3. Compare dimension scores, pass rate, duration, usage, turns, and tool calls against suite thresholds.
4. Classify improvement, regression, and unchanged metrics and render changed-case evidence.

**Verification:** Run `uv run pytest tests/test_eval_compare.py -q` and expect one simulated improvement, regression, and unchanged metric to be classified correctly.

## T16: Orchestrate Cases And Suites

**Files:** `herness/octocoder/evals/orchestration.py`, `herness/tests/test_eval_scoring.py`, `herness/tests/test_eval_scripted_runner.py`

**Dependencies:** T2-T15

**Steps:**
1. Implement the complete prepare-run-normalize-diff-grade-persist-cleanup lifecycle.
2. Select the real or scripted runner from validated case execution settings.
3. Preserve every repetition as an independent run.
4. Guarantee artifacts are written before optional workspace cleanup.
5. Convert framework exceptions into explicit run results while still performing safe cleanup.

**Verification:** Run `uv run pytest tests/test_eval_scripted_runner.py tests/test_eval_scoring.py tests/test_eval_artifacts.py -q` and expect the integrated deterministic lifecycle to pass.

## T17: Add The Evaluation CLI

**Files:** `herness/octocoder/evals/cli.py`, `herness/pyproject.toml`, `herness/tests/test_eval_cli.py`

**Dependencies:** T2, T14-T16

**Steps:**
1. Add `validate`, `run`, and `compare` subcommands with mutually exclusive case/suite/all selection.
2. Add execution override, repetition, output root, and keep-workspace options.
3. Print concise progress and final artifact locations without mixing them into JSON artifacts.
4. Return exit codes `0`, `1`, `2`, and `3` according to the approved plan.
5. Register the `octocoder-eval` console script.

**Verification:** Run `uv run pytest tests/test_eval_cli.py -q`, then run `uv run octocoder-eval --help` and expect all three subcommands.

## T18: Add Deterministic Fixtures, Cases, And Suites

**Files:** `evals/cases/smoke/*.yaml`, `evals/fixtures/*`, `evals/suites/*.yaml`, `evals/baselines/.gitkeep`, `evals/runs/.gitignore`

**Dependencies:** T17

**Steps:**
1. Add a successful scripted edit case that passes trajectory and file checks.
2. Add reference failure cases for forbidden tool, order violation, outcome failure, and execution failure/timeout.
3. Tag cases so smoke selects passing CI gates while failure references remain directly runnable for framework verification.
4. Define smoke, nightly, and release suites with explicit comparison thresholds.
5. Ignore generated runs while preserving baseline directory structure.

**Verification:** Run `uv run octocoder-eval validate --all` and expect every case/suite to validate; run the smoke suite and expect success without credentials.

## T19: Add CI And Usage Documentation

**Files:** `.github/workflows/evals.yml`, `README.zh-CN.md`, `README.md`

**Dependencies:** T17, T18

**Steps:**
1. Add a PR job that installs dependencies and runs deterministic tests plus the smoke suite.
2. Add scheduled and manual entry points for nightly/release suites, with real execution enabled only when repository configuration is present.
3. Document case authoring, trajectory constraints, outcome checks, artifacts, baseline comparison, exit codes, and the regression-case workflow.
4. Include the rule that every Agent behavior fix adds a reproducing evaluation case.

**Verification:** Parse the workflow as YAML, run documented smoke commands locally, and verify both README command examples match CLI help.

## T20: Run Full Regression And End-To-End Acceptance

**Files:** All files above

**Dependencies:** T1-T19

**Steps:**
1. Run all evaluation framework tests without credentials or network.
2. Run the complete existing backend test suite.
3. Run the deterministic smoke suite twice and compare normalized outputs.
4. Run simulated baseline/candidate comparison and verify regression exit code.
5. Inspect generated artifacts for expected files, readable trajectory diffs, and test-secret absence.
6. Run one opt-in real case only when a valid configured provider is available; otherwise record it as an unexecuted optional check rather than weakening deterministic acceptance.

**Verification:** Run `uv run pytest -q`, `uv run octocoder-eval run --suite smoke`, and the checklist commands; expect all mandatory checks to pass.

## Execution Order

```text
T1 -> T2
T1 -> T3
T1 -> T4
T1 -> T5
T1 -> T7
T4 + T5 -> T6
T3 + T7 -> T8
T3 + T4 + T5 + T7 -> T9
T6 -> T10
T3 + T7 -> T11
T10 + T11 -> T12
T3 + T4 + T6 + T12 -> T13
T12 + T13 -> T14
T14 -> T15
T2 through T15 -> T16
T16 -> T17
T17 -> T18
T18 -> T19
T1 through T19 -> T20
```
