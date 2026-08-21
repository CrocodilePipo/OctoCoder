# OctoCoder Agent Evaluation MVP Checklist

> Metric-model amendment (2026-08-21): checklist references to numeric scores,
> pass rates, and `score.json` are superseded by verdicts, check counts,
> failed-run counts, absolute resource measurements, and `verdict.json`.

Each item must be verified by running code or observing generated artifacts. Optional real-provider checks do not replace mandatory deterministic acceptance.

## Implementation Completeness

- [ ] Versioned case and suite schemas are implemented and reject unsupported schema versions (verification: run `uv run pytest tests/test_eval_models.py -q` and observe valid-version acceptance plus unsupported-version failure).
- [ ] Case validation covers IDs, prompts, fixtures, execution mode, limits, expectations, scripted effects, relative paths, and incompatible fields (verification: run `uv run pytest tests/test_eval_models.py -q` and inspect field-level validation assertions).
- [ ] YAML case discovery rejects duplicate IDs and resolves explicit IDs and tag selectors deterministically (verification: run `uv run pytest tests/test_eval_loader.py -q`).
- [ ] Malformed cases, unknown suite references, and escaping fixture paths fail before a runner starts (verification: run `uv run pytest tests/test_eval_loader.py -q` and confirm runner-spy call count remains zero for invalid definitions).
- [ ] Fixture preparation creates a fresh evaluation-owned workspace and does not copy fixture Git metadata (verification: run `uv run pytest tests/test_eval_workspace.py -q` and inspect the prepared baseline assertions).
- [ ] Workspace patch capture includes modified, deleted, new text, and new binary files (verification: run `uv run pytest tests/test_eval_workspace.py -q`).
- [ ] Workspace cleanup requires a matching ownership marker and a resolved path beneath the run root (verification: run `uv run pytest tests/test_eval_workspace.py -q` and confirm unsafe cleanup attempts are rejected without deleting sentinel files).
- [ ] Runtime credentials are recursively redacted from text, mappings, events, stderr, patches, JSON, and Markdown (verification: run `uv run pytest tests/test_eval_redaction.py tests/test_eval_artifacts.py -q`).
- [ ] Existing non-interactive `stream-json` events include sequence, run ID, elapsed time, turn, and lead Agent metadata without changing text-mode output (verification: run `uv run pytest tests/test_stream_json_metadata.py -q`).
- [ ] Permission requests and their non-interactive decisions are observable structured events (verification: run the permission scenario in `tests/test_stream_json_metadata.py` and inspect the paired request/decision assertions).
- [ ] Provider/model identity and available Multi-Agent trace summaries are emitted without credentials (verification: run `uv run pytest tests/test_stream_json_metadata.py tests/test_eval_redaction.py -q`).
- [ ] Raw NDJSON parsing preserves actionable malformed-line findings instead of silently dropping data (verification: run `uv run pytest tests/test_eval_events.py -q`).
- [ ] Event normalization canonicalizes workspace paths, Windows/Linux separators, generated IDs, object-key order, timestamps, and long results (verification: run `uv run pytest tests/test_eval_events.py -q` and confirm equivalent inputs normalize identically).
- [ ] Tool-use and tool-result events are paired by ID, and missing halves remain visible as reliability findings (verification: run `uv run pytest tests/test_eval_events.py tests/test_eval_scoring.py -q`).
- [ ] Tool trajectories preserve order, tool name, normalized arguments, status, result summary/hash, duration, permission, retry, Agent, trace, and turn metadata when available (verification: inspect trajectory assertions in `uv run pytest tests/test_eval_events.py -q`).
- [ ] The scripted runner replays events and applies validated file writes/deletes without model credentials or network (verification: clear provider credential environment variables and run `uv run pytest tests/test_eval_scripted_runner.py -q`).
- [ ] The scripted runner rejects absolute paths, parent traversal, and symlink escapes (verification: run `uv run pytest tests/test_eval_scripted_runner.py -q`).
- [ ] The real runner launches the existing non-interactive OctoCoder protocol, consumes stdout/stderr concurrently, and preserves partial output on failure (verification: run `uv run pytest tests/test_eval_real_runner.py -q`).
- [ ] The real runner enforces timeout and terminates the spawned process tree (verification: run the hanging-child scenario in `uv run pytest tests/test_eval_real_runner.py -q` and confirm no child remains running).
- [ ] Required and forbidden tool expectations support minimum/maximum counts and typed argument constraints (verification: run `uv run pytest tests/test_eval_trajectory_grader.py -q`).
- [ ] Argument matching supports `equals`, `contains`, `matches`, `glob`, and `exists` over dotted argument paths (verification: run the operator matrix in `uv run pytest tests/test_eval_trajectory_grader.py -q`).
- [ ] Exact, subsequence, and constraint trajectory modes each have passing and failing tests (verification: run `uv run pytest tests/test_eval_trajectory_grader.py -q`).
- [ ] Total calls, failed calls, and repeated identical call limits produce explicit findings and expected/actual diffs (verification: run `uv run pytest tests/test_eval_trajectory_grader.py -q`).
- [ ] Outcome grading supports command exit, file existence, file absence, literal/regex content, Git diff, and workspace-boundary checks (verification: run `uv run pytest tests/test_eval_outcome_grader.py -q`).
- [ ] Outcome commands run without a shell, have bounded time, and capture bounded redacted evidence (verification: run command-injection, timeout, and long-output cases in `uv run pytest tests/test_eval_outcome_grader.py -q`).
- [ ] Case scoring reports separate outcome, trajectory, efficiency, safety, and reliability dimensions (verification: run `uv run pytest tests/test_eval_scoring.py -q` and inspect all five dimension fields).
- [ ] Forbidden behavior, workspace escape, framework failure, and required hard-gate check failure unconditionally fail a case (verification: run `uv run pytest tests/test_eval_scoring.py -q` and confirm high non-safety scores cannot change the failed result).
- [ ] Execution results distinguish completed, Agent failed, framework failed, timeout, and expectation failure outcomes (verification: run `uv run pytest tests/test_eval_scoring.py tests/test_eval_scripted_runner.py tests/test_eval_real_runner.py -q`).
- [ ] Every run persists case snapshot, raw events, normalized events, trajectory, patch, stderr, score, and Markdown report using stable filenames (verification: run `uv run pytest tests/test_eval_artifacts.py -q`).
- [ ] Repeated runs remain individually addressable and report pass rate, mean, median, min, max, and eligible p95 metrics (verification: run `uv run pytest tests/test_eval_report.py -q`).
- [ ] Baseline comparison identifies pass-to-fail, new hard gates, missing cases, numeric regression, improvement, and unchanged metrics (verification: run `uv run pytest tests/test_eval_compare.py -q`).
- [ ] The CLI implements `validate`, `run`, and `compare`, including case/suite/all selection and execution/repeat/output options (verification: run `uv run octocoder-eval --help` and each subcommand's `--help`, then run `uv run pytest tests/test_eval_cli.py -q`).
- [ ] CLI exit codes are `0` for pass, `1` for evaluation failure, `2` for schema/framework failure, and `3` for threshold regression (verification: run the exit-code matrix in `uv run pytest tests/test_eval_cli.py -q`).
- [ ] Deterministic reference cases cover success, forbidden tool, ordering violation, outcome failure, and execution failure or timeout (verification: run `uv run octocoder-eval validate --all` and list discovered case IDs in the command output).
- [ ] Smoke, nightly, and release suites resolve to deterministic ordered case lists with declared thresholds (verification: run loader tests and `uv run octocoder-eval validate --suite smoke`, `--suite nightly`, and `--suite release`).

## Integration

- [ ] Real and scripted runners both produce the same validated `RunnerOutput` contract consumed by one normalization and scoring path (verification: run `uv run pytest tests/test_eval_scripted_runner.py tests/test_eval_real_runner.py tests/test_eval_events.py -q`).
- [ ] The orchestrator performs prepare, run, redact, normalize, diff, grade, persist, and cleanup in the approved order (verification: run the lifecycle spy test in `uv run pytest tests/test_eval_scripted_runner.py tests/test_eval_artifacts.py -q`).
- [ ] Artifacts are persisted before a disposable workspace is removed, and failed runs still retain diagnostic artifacts (verification: run completed and failed lifecycle cases in `uv run pytest tests/test_eval_artifacts.py -q`).
- [ ] A new grader can be registered against `GradeContext` without modifying real or scripted runners (verification: run the test-only grader integration in `uv run pytest tests/test_eval_scoring.py -q`).
- [ ] Existing `octocoder -p` text and `stream-json` consumers remain compatible with the enriched protocol (verification: run `uv run pytest tests/test_stream_json_metadata.py tests/test_agent.py -q`).
- [ ] Generated JSON conforms to schema version `1`, and Markdown points to raw events, normalized trajectory, patch, and grader evidence (verification: run `uv run pytest tests/test_eval_artifacts.py tests/test_eval_report.py -q` and parse generated JSON through `SuiteReport`).
- [ ] The GitHub workflow runs deterministic tests and smoke evaluation without requiring repository secrets (verification: parse `.github/workflows/evals.yml` as YAML and inspect the PR job commands; run the same commands locally with provider credentials removed).
- [ ] Chinese and English documentation commands match actual CLI options and explain the EDD regression-case workflow (verification: compare README command blocks with `uv run octocoder-eval --help` and run the documented smoke command).

## Build And Tests

- [ ] Evaluation-focused tests pass without network access or paid credentials (verification: remove provider credential environment variables and run `uv run pytest tests/test_eval_*.py tests/test_stream_json_metadata.py -q`).
- [ ] All existing and new backend tests pass (verification: run `uv run pytest -q` from `herness` and expect zero failures).
- [ ] Python source compiles without syntax errors (verification: run `uv run python -m compileall -q octocoder`).
- [ ] Evaluation CLI installation and imports succeed through the project entry point (verification: run `uv sync`, `uv run octocoder-eval --help`, and `uv run python -c "import octocoder.evals"`).
- [ ] All case and suite definitions validate (verification: run `uv run octocoder-eval validate --all` and expect exit code `0`).
- [ ] The deterministic smoke suite passes without credentials (verification: remove provider credentials, run `uv run octocoder-eval run --suite smoke`, and expect exit code `0`).
- [ ] Two deterministic smoke runs have equivalent normalized trajectories, scores, and deterministic report sections (verification: run the suite twice to separate output roots and execute the deterministic comparison test or comparison command).
- [ ] Generated artifacts contain no registered test secret (verification: recursively search both run roots for the known test-secret literals and expect no matches).
- [ ] `git diff --check` reports no whitespace errors introduced by the implementation (verification: run `git diff --check`).

## End-To-End Scenarios

- [ ] Successful deterministic edit: select the smoke success case, create an isolated workspace, replay ReadFile/EditFile/Bash events, modify the expected file, pass trajectory and outcome checks, emit all artifacts, clean the workspace, and exit `0` (verification: run `uv run octocoder-eval run --case successful-edit` and inspect its JSON, Markdown, trajectory, and patch).
- [ ] Forbidden behavior: run the reference forbidden-tool case and observe a safety hard-gate finding and exit `1` even when file outcomes pass (verification: run that case directly and inspect `score.json`).
- [ ] Order violation: run the reference order case and observe an expected-versus-actual trajectory diff identifying reordered calls (verification: run that case directly and inspect `report.md`).
- [ ] Agent execution failure: run the scripted failure or timeout case and observe a complete diagnostic artifact directory with `agent_failed` or `timeout` status rather than a framework crash (verification: run the reference case and inspect `raw-events.jsonl`, `stderr.txt`, and `score.json`).
- [ ] Baseline regression gate: compare prepared baseline and candidate reports containing one regression, one improvement, and one unchanged metric; observe exit `3` and a Markdown comparison summary (verification: run the comparison fixture command used by `tests/test_eval_compare.py`).
- [ ] Fixture protection: hash a fixture before and after a successful and failed run and observe identical hashes while each run has its own patch (verification: run the fixture-integrity end-to-end test in `tests/test_eval_workspace.py`).
- [ ] Secret protection: include a known fake API key in scripted stderr, tool output, and a file diff; observe only the redaction marker in every persisted artifact (verification: run the redaction end-to-end case and recursively search its artifact directory).
- [ ] Real-run protocol: with no paid call required, launch the real runner against a controlled local non-interactive process and observe structured-event capture, workspace diff, completion/failure classification, and report generation (verification: run the subprocess integration scenario in `tests/test_eval_real_runner.py`).
- [ ] Optional configured-provider smoke: when the local user explicitly has a valid provider and chooses to spend API usage, run one real evaluation case and observe provider/model identity, tool trajectory, usage, final response, patch, and score without any secret in artifacts (verification: run `uv run octocoder-eval run --case <real-case-id>`; record as optional if no valid provider is available).
