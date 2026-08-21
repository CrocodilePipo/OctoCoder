# OctoCoder Agent Evaluation MVP Spec

> Metric-model amendment (2026-08-21): numeric 100-point totals, dimension scores,
> pass-rate gates, and `score.json` are superseded by `verdict.json`, passed/total
> check counts, failed-run counts, and absolute duration/token/turn/tool-call
> measurements. Percentages are reserved for semantic similarity metrics. Older
> score terminology below records the originally approved design, not the current
> reporting contract.

## Background

OctoCoder already has automated component tests and emits structured Agent events, tool calls, tool results, usage, session transcripts, and Multi-Agent traces. It does not yet have a repeatable evaluation system that can execute representative coding tasks, preserve the complete observable trajectory, compare behavior against explicit expectations, and prevent capability regressions during development.

The first evaluation-system iteration establishes an Evaluation-Driven Development loop. Every capability change or production failure can be represented as an evaluation case, measured against a stored baseline, and checked before merge or release. The system uses a hybrid execution model: real configured model providers measure actual Agent performance, while deterministic scripted runs validate the evaluation framework itself without API cost or model variance.

## Goals

- Provide a versioned, human-readable format for defining Agent evaluation cases and suites.
- Run cases in isolated disposable workspaces without modifying source fixtures.
- Support both real-model execution and deterministic scripted execution.
- Record complete observable Agent behavior, including tool-call trajectories and execution outcomes.
- Compare final artifacts and tool trajectories against explicit case expectations.
- Produce machine-readable and human-readable evaluation reports.
- Establish stable smoke, nightly, and release evaluation workflows for future EDD adoption.
- Make failed production or development scenarios easy to convert into permanent regression cases.

## Functional Requirements

- F1: The system accepts versioned evaluation cases containing identity, description, task prompt, fixture reference, execution limits, tags, expected outcomes, and expected trajectory constraints.
- F2: Evaluation cases can be grouped into named suites, and a caller can run one case, one suite, or all discovered cases.
- F3: Every case runs in a fresh isolated workspace derived from its fixture, and changes made during one run do not affect the fixture or another run.
- F4: Real execution invokes OctoCoder with the selected runtime configuration and records the actual Agent behavior and final workspace state.
- F5: Deterministic execution consumes a scripted event sequence and produces the same run artifact and score structure as real execution without contacting a model provider.
- F6: Every run records a stable run identity, case identity, execution mode, timestamps, duration, completion state, final response, errors, usage, and workspace diff.
- F7: Every observable tool invocation records its global order, Agent identity when available, turn, tool identity, normalized arguments, result state, normalized result summary, duration, permission decision when available, and retry relationship when available.
- F8: Volatile trajectory values such as temporary workspace roots, path separators, generated request identifiers, timestamps, and unstable result payloads are normalized before comparison while raw events remain available for diagnosis.
- F9: Cases can require tools, forbid tools, constrain tool arguments, constrain maximum and minimum call counts, require relative ordering, and limit repeated identical calls or failed calls.
- F10: Trajectory comparison supports exact matching for deterministic protocol or safety cases and constraint-based or subsequence matching for non-deterministic Agent tasks.
- F11: Outcome grading supports command exit checks, file existence or absence checks, text-content checks, workspace-boundary checks, and Git-diff checks.
- F12: A case can define hard gates whose violation fails the run regardless of aggregate score, including forbidden tools, forbidden paths, workspace escape, and failed required verification commands.
- F13: The system calculates separate outcome, trajectory, efficiency, safety, and reliability results rather than hiding all behavior behind one aggregate score.
- F14: Run results distinguish framework failure, Agent failure, expectation failure, timeout, and successful completion.
- F15: A comparison operation reports regressions and improvements between a stored baseline and a candidate result at case, suite, and metric levels.
- F16: Reports include enough trajectory differences to identify missing, additional, reordered, repeated, failed, or argument-incompatible tool calls.
- F17: Machine-readable reports use a stable versioned schema, and human-readable reports summarize pass/fail state, hard-gate failures, score changes, resource usage, and artifact locations.
- F18: The command-line entry point returns a non-zero status when framework execution fails, a hard gate fails, or configured regression thresholds are exceeded so it can act as a CI gate.
- F19: The repository includes representative deterministic sample cases covering successful trajectory matching, forbidden behavior, ordering violations, outcome failure, and timeout or execution failure.
- F20: Evaluation framework tests run without model credentials, network access, or paid API calls.

## Non-Functional Requirements

- N1: Evaluation definitions, normalized run artifacts, baselines, and reports are deterministic and reviewable in source control where appropriate.
- N2: Raw run artifacts may contain model or tool output but must redact configured secrets before persistence or reporting.
- N3: Case execution has explicit limits for wall-clock duration, Agent turns, tool calls, and available model usage where the runtime exposes those controls.
- N4: Fixture preparation and cleanup are safe on Windows, Linux, and macOS and never recursively remove a path that has not been verified as an evaluation-owned temporary workspace.
- N5: A malformed case or suite fails validation before Agent execution and reports a precise field-level error.
- N6: Framework internals remain independent from the desktop UI and can run in local terminals and CI environments.
- N7: Adding a new grader or trajectory matcher does not require changing the case runner's execution lifecycle.
- N8: The MVP reuses existing OctoCoder structured events where possible and does not require access to private chain-of-thought text.
- N9: Reports preserve the model/provider configuration identity needed for comparison but never persist API keys or equivalent credentials.
- N10: Repeated real-model evaluation results preserve individual runs so variance can be measured rather than overwritten by an average.

## Out Of Scope

- A graphical evaluation dashboard in the desktop client.
- Automatic collection or upload of real-user conversations.
- A hosted evaluation service, distributed worker fleet, or shared cloud database.
- Automatic generation of evaluation cases from arbitrary issue reports.
- Full SWE-bench or other external benchmark integration.
- Audio-quality corpus management and detailed ASR WER/CER scoring; voice tasks may be represented later through dedicated extensions.
- LLM-as-judge grading in the first implementation cycle.
- Requiring one exact tool trajectory for every real-model coding task.
- Scoring or persisting hidden chain-of-thought reasoning.
- Statistical significance decisions beyond preserving repeated-run measurements and reporting basic aggregates.

## Acceptance Criteria

- AC1: A valid case and suite can be loaded, selected, and validated; malformed definitions fail before execution with an actionable error.
- AC2: Running the same deterministic case twice produces equivalent normalized events, scores, and report content apart from explicitly excluded run metadata.
- AC3: A real-model case can invoke the existing non-interactive OctoCoder path, capture its structured event stream, and produce a complete run artifact even when the Agent fails.
- AC4: A fixture remains byte-for-byte unchanged after a run, while all Agent file changes are available as a workspace diff in the run artifacts.
- AC5: Tool events preserve call order, tool name, normalized arguments, result status, duration, and available Agent/turn metadata in both raw and normalized trajectory outputs.
- AC6: Required-tool, forbidden-tool, argument, call-count, repeated-call, failed-call, exact-order, and subsequence-order expectations each have an automated passing and failing example.
- AC7: Outcome graders can automatically verify command exit status, file existence or absence, file content, Git diff, and workspace-boundary compliance.
- AC8: A forbidden tool or path and a failed required verification command cause an unconditional case failure even when other scores are high.
- AC9: Reports expose separate outcome, trajectory, efficiency, safety, and reliability results and clearly identify the exact failed constraints.
- AC10: Comparing a candidate run set to a baseline identifies at least one simulated regression, one improvement, and unchanged metrics.
- AC11: JSON results conform to a versioned schema and the Markdown report links or points to raw events, normalized trajectory, workspace diff, and grader evidence.
- AC12: The CLI exits successfully for a passing suite and non-zero for malformed input, framework errors, hard-gate violations, or threshold-breaking regressions.
- AC13: Deterministic framework tests and sample evaluations pass without model credentials or network access.
- AC14: Persisted artifacts and reports do not contain configured API keys or known test secrets.
- AC15: Existing backend automated tests continue to pass after integration.
- AC16: An end-to-end deterministic evaluation creates an isolated workspace, replays a scripted Agent run, records and normalizes its tool trajectory, grades trajectory and final files, emits JSON and Markdown reports, and exits with the expected status.
