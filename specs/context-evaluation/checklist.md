# OctoCoder Context Management Evaluation Checklist

> Metric-model amendment (2026-08-21): weighted-score checklist wording is
> superseded by check counts, semantic similarity, and absolute token/compaction
> measurements. Generated case evidence is stored in `verdict.json`.

Each item must be verified by running code or observing generated evidence. Commands are run from `herness/` unless stated otherwise.

## Implementation Completeness

- [x] C1. Context cases accept validated multi-stage setup, pressure, checkpoint, probe, and resume definitions while non-context cases remain valid (verification: run `uv run pytest tests/test_eval_context_models.py tests/test_eval_loader.py tests/test_eval_models.py -q` and expect all valid/invalid schema and reference cases to pass).
- [x] C2. Context expectations can declare critical facts, active and superseded instructions, task state, provenance, stale facts, token tolerances, compression limits, resume comparisons, and hard gates (verification: inspect the schema tests and run `uv run pytest tests/test_eval_context_models.py -q`; every expectation family must have at least one valid and one rejected example).
- [x] C3. Token anchoring emits bounded `usage_anchor` observations containing provider/estimate/message-count evidence without changing token accounting (verification: run `uv run pytest tests/test_context_observer.py tests/test_context.py -q` and compare observer-enabled and no-op results).
- [x] C4. Large tool-result persistence emits bounded spill/replacement observations with before/after sizes and stable non-secret identities (verification: run `uv run pytest tests/test_context_observer.py tests/test_replacement_state.py -q` and expect spill evidence plus unchanged replacement behavior).
- [x] C5. Compaction emits ordered started, skipped, completed, and failed lifecycle observations with trigger, threshold, window, token, message, retained-tail, summary-hash, retry, and failure evidence when available (verification: run `uv run pytest tests/test_context_observer.py tests/test_context.py -q` and assert the event transition matrix).
- [x] C6. Session restoration emits a stable boundary identity and restored message, replacement, summary, and retained-tail counts, including degraded malformed-boundary handling (verification: run `uv run pytest tests/test_context_observer.py tests/test_memory.py -q`).
- [x] C7. The optional no-op observer leaves normal Agent output and control flow unchanged and never requires evaluation infrastructure (verification: run `uv run pytest tests/test_context_observer.py tests/test_agent.py -q` with and without an observer).
- [x] C8. A persistent non-interactive session supports multiple turns, cumulative usage, checkpoints, persistence, reconstruction, and resume over one real conversation (verification: run `uv run pytest tests/test_noninteractive_session.py -q`).
- [x] C9. The existing `octocoder -p` path delegates to one persistent session turn without changing text or structured output contracts (verification: run `uv run pytest tests/test_noninteractive_session.py tests/test_stream_json_metadata.py -q`).
- [x] C10. Context events are normalized deterministically and malformed lifecycle transitions remain visible as reliability findings (verification: run `uv run pytest tests/test_eval_context_events.py tests/test_eval_events.py -q`).
- [x] C11. Scripted context execution replays all declared stages, enforces limits, supports compaction/resume failures, and needs no credentials or network (verification: clear provider credentials in the test process and run `uv run pytest tests/test_eval_context_scripted_runner.py -q`).
- [x] C12. Real context execution keeps one persistent session, can restart through persistence, captures partial evidence on failure, and passes against a local fake Agent/provider (verification: run `uv run pytest tests/test_eval_context_real_runner.py -q` without network access).
- [x] C13. Required facts, instruction priority, stale contamination, task continuity, tool pairing, resume consistency, token accuracy, and compression behavior are graded independently with first-failing checkpoint evidence (verification: run `uv run pytest tests/test_eval_context_grader.py -q` and expect every subscore and finding class to be exercised).
- [x] C14. Context scoring uses weights 25/20/15/15/10/10/5 for retention, instruction adherence, continuity, resume consistency, token accuracy, compression efficiency, and contamination, excluding unavailable optional metrics from the denominator (verification: run the exact-score and missing-metric cases in `uv run pytest tests/test_eval_context_grader.py tests/test_eval_scoring.py -q`).
- [x] C15. Declared loss of a critical fact or instruction, broken tool pair, resume divergence, overflow, or forbidden stale fact fails the case regardless of weighted scores (verification: run hard-gate matrix tests in `uv run pytest tests/test_eval_context_grader.py tests/test_eval_scoring.py -q`).

## Integration And Artifacts

- [x] C16. Context runner selection occurs only for cases that declare context expectations; all existing runner paths remain unchanged (verification: run `uv run pytest tests/test_eval_context_scripted_runner.py tests/test_eval_context_real_runner.py tests/test_eval_cli.py -q`).
- [x] C17. Shared typed matching preserves trajectory grading semantics while supporting bounded fact and state assertions (verification: run `uv run pytest tests/test_eval_trajectory_grader.py tests/test_eval_context_grader.py -q`).
- [x] C18. Every context run writes `context-events.jsonl`, `context-checkpoints.json`, and `context-metrics.json` atomically alongside existing artifacts (verification: run `uv run pytest tests/test_eval_context_artifacts.py tests/test_eval_artifacts.py -q` and inspect the asserted file set).
- [x] C19. Non-context runs do not create context-only artifacts (verification: run the non-context artifact compatibility case in `uv run pytest tests/test_eval_context_artifacts.py tests/test_eval_artifacts.py -q`).
- [x] C20. Context artifacts contain bounded, normalized, redacted evidence and no complete summary, unbounded tool result, configured API key, token, or injected fake secret (verification: run `uv run pytest tests/test_eval_context_artifacts.py tests/test_eval_redaction.py -q` and recursively scan the generated fixture artifacts for test secrets).
- [x] C21. Case Markdown reports link all context artifacts and identify the exact first failing stage/checkpoint with expected-versus-actual evidence (verification: run `uv run pytest tests/test_eval_context_artifacts.py tests/test_eval_report.py -q`).
- [x] C22. Suite reports aggregate context score, retention, resume consistency, token error, compression ratio, compaction count, and repetition mean/median/range/p95 where applicable (verification: run context report aggregation cases in `uv run pytest tests/test_eval_context_artifacts.py tests/test_eval_report.py -q`).
- [x] C23. Baseline comparison detects pass-to-fail transitions, missing checkpoints, new hard gates, and threshold regressions or improvements while preserving exit code `3` for regressions (verification: run `uv run pytest tests/test_eval_context_compare.py tests/test_eval_compare.py tests/test_eval_context_cli.py -q`).
- [x] C24. Existing CLI selection, validation, run, comparison, progress output, JSON output, artifact paths, and exit codes `0`, `1`, `2`, and `3` remain usable for context cases (verification: run `uv run pytest tests/test_eval_context_cli.py tests/test_eval_cli.py -q`).
- [x] C25. The real-provider suite uses the same case, checkpoint, grader, artifact, report, and comparison pipeline as scripted cases, but execution remains explicitly opt-in (verification: validate `context-nightly`, inspect its tags/execution settings, and run the fake-provider pipeline test; no external request may occur in default smoke).

## Build And Tests

- [x] C26. All evaluation catalog files, including passing and failure-reference context cases, validate through the existing CLI (verification: run `uv run octocoder-eval validate --all` and expect exit `0`).
- [x] C27. The mandatory context smoke suite passes offline without provider credentials (verification: run `uv run octocoder-eval run --suite context-smoke --output-root ../.tmp/context-eval-smoke` in an environment without provider credentials and expect exit `0`).
- [x] C28. Every failure-reference case fails for its declared context expectation rather than framework or runner failure (verification: run each case in `evals/cases/context/` marked as a failure reference and expect exit `1` plus the declared hard-gate/checkpoint evidence).
- [x] C29. Context-focused unit and integration tests pass (verification: run `uv run pytest tests/test_context_observer.py tests/test_noninteractive_session.py tests/test_eval_context_models.py tests/test_eval_context_events.py tests/test_eval_context_scripted_runner.py tests/test_eval_context_real_runner.py tests/test_eval_context_grader.py tests/test_eval_context_artifacts.py tests/test_eval_context_compare.py tests/test_eval_context_cli.py -q`).
- [x] C30. The complete backend test suite passes without network access (verification: run `uv run pytest -q` and expect no failures).
- [x] C31. Python sources and tests compile under the project's Python 3.11 minimum syntax (verification: run `uv run python -m compileall -q octocoder tests` and expect exit `0`).
- [x] C32. Repository formatting integrity is clean (verification: from the repository root run `git diff --check` and expect no output or errors).
- [x] C33. The GitHub workflow parses, runs deterministic context smoke in mandatory CI, and guards scheduled/manual real probes behind repository configuration (verification: parse `.github/workflows/evals.yml` with the installed YAML loader and inspect the job conditions in workflow tests or a local workflow validation command).
- [x] C34. Chinese and English READMEs document authoring, checkpoints, metrics, artifacts, thresholds, exit codes, offline smoke, EDD case-first practice, and possible real-provider cost (verification: compare `README.md`, `README.zh-CN.md`, and `README.en.md` against `octocoder-eval --help` and validate every documented command).

## Determinism, Safety, And Compatibility

- [x] C35. Running deterministic context smoke twice produces equivalent normalized timelines, checkpoints, metrics, scores, and deterministic report sections (verification: run the suite into two separate output roots and execute the deterministic comparison test; only explicitly volatile run metadata may differ).
- [x] C36. Context limits for stages, turns, events, wall-clock time, provider usage, regex size, and evidence size are validated or enforced with explicit failure categories (verification: run model, scripted-runner, real-runner, matching, and artifact boundary tests).
- [x] C37. Failures distinguish Agent failure, framework/protocol failure, context expectation failure, timeout, and unsupported instrumentation (verification: run the status matrix in runner, grader, and CLI tests and inspect emitted status/finding types).
- [x] C38. Existing non-context cases retain five dimensions, their previous score snapshots, report shape, artifact set, and runner selection (verification: run `uv run pytest tests/test_eval_scoring.py tests/test_eval_artifacts.py tests/test_eval_report.py tests/test_eval_cli.py -q`).
- [x] C39. Normal Agent execution with instrumentation disabled produces no context artifact dependency, credential exposure, or user-visible behavior change (verification: run core Agent, context, memory, and stream metadata regression tests).
- [x] C40. Context normalization produces equivalent path, ID, timestamp, hash, and key-order evidence for Windows-, Linux-, and macOS-shaped fixtures (verification: run the cross-platform parameterized cases in `uv run pytest tests/test_eval_context_events.py tests/test_eval_context_artifacts.py -q`).

## End-To-End Scenarios

- [x] C41. Passing retention flow: seed facts/instructions/state, create pressure, compact, probe, persist/resume, probe again, and pass all context subscores offline (verification: run the passing case through `uv run octocoder-eval run --suite context-smoke` and inspect both checkpoint probes and final context metrics).
- [x] C42. Stale-value flow: correct an earlier value, compact, then expose the stale value in an answer or tool action; the first contaminated checkpoint is reported and the case fails (verification: run the stale-contamination reference case and expect exit `1`).
- [x] C43. Instruction-priority flow: supersede a lower-priority instruction while retaining a mandatory project/safety constraint; loss of the active mandatory constraint triggers a hard gate (verification: run the instruction-priority reference case and expect the declared active/superseded evidence).
- [x] C44. Continuity flow: retain target files, completed edits, known test failure, pending work, next action, and complete tool-use/tool-result pairs across compaction (verification: run the continuity fixture and inspect its checkpoint and trajectory evidence).
- [x] C45. Resume flow: persist the actual compact boundary, reconstruct a session, compare declared before/after fields, and detect an intentionally divergent restoration (verification: run both passing resume coverage and `resume-divergence`; expect pass and exit `1`, respectively).
- [x] C46. Token/compression flow: consume provider-shaped usage anchors, detect out-of-tolerance trigger drift, and report before/after tokens, reclaimed tokens, ratio, retained tail, spill savings, and count (verification: run token-drift and ineffective-compaction references and inspect `context-metrics.json`).
- [x] C47. Baseline flow: compare a passing baseline with a candidate containing a context regression and receive a concise changed-checkpoint report plus exit `3` (verification: run `octocoder-eval compare` against the test reports in the comparison integration test).
- [x] C48. Real-path flow: run all stages through the subprocess worker and local fake Agent/provider, including one persistence restart, without network access (verification: run `uv run pytest tests/test_eval_context_real_runner.py -q` and inspect captured partial evidence for the injected failure case).
- [x] C49. Optional provider flow: when explicitly configured, repeated real probes produce variability statistics; when not configured, mandatory CI does not invoke or fail on them (verification: run suite-selection tests unconfigured, and record a configured probe separately only when the operator opts in).
- [x] C50. Final secret audit: all artifacts from smoke, failure references, fake-real execution, and baseline comparison contain no configured or seeded secrets (verification: run the automated recursive secret scan over every acceptance output root and expect zero matches).

## Acceptance Traceability

| Spec criterion | Checklist evidence |
| --- | --- |
| AC1 | C1, C11, C41 |
| AC2 | C3-C6, C10, C18 |
| AC3 | C13, C41 |
| AC4 | C13, C15, C42 |
| AC5 | C13-C15, C43 |
| AC6 | C13, C44 |
| AC7 | C6, C8, C45 |
| AC8 | C13, C46 |
| AC9 | C14, C22, C46 |
| AC10 | C13-C14, C22 |
| AC11 | C15, C28, C42-C45 |
| AC12 | C18, C21 |
| AC13 | C23, C47 |
| AC14 | C26-C28, C41 |
| AC15 | C12, C22, C25, C49 |
| AC16 | C7, C9, C16, C19, C38-C39 |
| AC17 | C20, C29-C35, C40, C50 |

## Acceptance Evidence

- Full backend suite: `768 passed, 4 skipped, 1 warning` in 46.43 seconds. The warning is the pre-existing unregistered `pytest.mark.timeout` marker.
- Catalog: 13 cases and 5 suites validated through `octocoder-eval validate --all`.
- Offline gate: `context-smoke` passed without network or provider credentials.
- Determinism: two independent smoke runs produced identical SHA-256 values for `context-events.jsonl`, `context-checkpoints.json`, `context-metrics.json`, and case `report.md`.
- Failure references: all six returned evaluation exit `1` and exposed their declared context hard-gate finding.
- Comparison: a regressed candidate produced `regression: true`; the direct CLI executable returned exit `3`.
- Privacy: 321 repository files and 117 generated evaluation files were scanned against five discovered configured secrets; zero matches were found.
- Runtime: persistent multi-turn, resume, subprocess timeout, partial evidence, and fake-provider real-path tests passed offline.
- Optional real-provider probe: intentionally not executed because it is opt-in and may incur cost; CI remains guarded by `OCTOCODER_REAL_CONTEXT_EVALS=true`.
- Static checks: Python compilation, workflow YAML parsing, trailing-whitespace scan, and `git diff --check` passed.
