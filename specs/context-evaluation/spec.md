# OctoCoder Context Management Evaluation Spec

> Metric-model amendment (2026-08-21): context reporting no longer calculates a
> weighted or 100-point score. It reports check counts and concrete token,
> compaction, duration, turn, and tool-call measurements. Only retention,
> instruction adherence, continuity, and resume similarity use percentages.
> Relative token error and compression-ratio gates are superseded by absolute
> token-error, before/after-token, reclaimed-token, and retained-token limits.

## Background

OctoCoder currently manages context through several cooperating mechanisms:

- large tool results are persisted and replaced with bounded previews;
- provider usage is anchored and combined with estimates for messages added after the anchor;
- conversations are automatically compacted near the effective context-window limit;
- a recent message tail and complete tool-use/tool-result pairs are preserved verbatim;
- summaries, recently read files, active skills, available tools, replacement decisions, and compact boundaries support continuation and session resume.

Existing unit tests verify many local invariants, while the Agent evaluation framework measures final outcomes, tool trajectories, efficiency, safety, and reliability. It does not yet determine whether context compaction preserves the facts, instructions, working state, and provenance required to continue a coding task. Context lifecycle events also lack enough structured data to diagnose why a context regression occurred.

This feature adds a hybrid context-management evaluation layer. Deterministic white-box scenarios are mandatory and run offline in CI. Optional black-box scenarios exercise the real Agent and configured model to measure semantic retention under realistic long conversations without making model-dependent results the default pull-request gate.

## Goals

- Make context lifecycle behavior observable through stable structured events and artifacts.
- Evaluate semantic retention, instruction adherence, task continuity, resume consistency, token accounting, compression efficiency, and context contamination separately.
- Provide deterministic, network-free context regression cases suitable for PR gating.
- Provide optional real-model probes that use the same case, scoring, artifact, and baseline infrastructure.
- Turn critical context loss into explicit hard-gate failures rather than hiding it inside an average efficiency score.
- Enable EDD for context changes: every context-management bug fix can begin with a reproducing evaluation case.

## Functional Requirements

- F1: Context evaluations support multi-stage conversations containing setup turns, context-pressure turns, compaction or persistence boundaries, probe turns, and optional resume stages.
- F2: Cases can declare named critical facts, user instructions, task-state claims, source/provenance expectations, stale facts that must not survive, and expected working artifacts.
- F3: Deterministic cases can replay context lifecycle events and state transitions without a model provider, network access, or credentials.
- F4: Optional real cases can execute the existing Agent and configured provider through the same multi-stage case definition and produce comparable context evidence.
- F5: Structured context events expose available trigger reason, threshold, context-window size, estimated or provider-reported token counts, before/after counts, compacted and retained message counts, retained token estimate, summary result, spill/replacement counts, retry/failure state, and resume boundary identity.
- F6: Context events and artifacts do not persist full sensitive context by default. Text evidence is bounded, hashed where appropriate, and processed through existing secret redaction.
- F7: Evaluation checks can verify that required facts and instructions remain available after compaction, while forbidden or superseded facts are absent from the final answer and subsequent actions.
- F8: Evaluation checks can verify instruction priority, including that later user corrections supersede earlier values without overriding higher-priority project or safety constraints.
- F9: Evaluation checks can verify task continuity, including retained target files, pending work, previous edits, test failures, tool-use/tool-result pairing, and the next expected action.
- F10: Evaluation checks can verify that a compacted session resumed from persisted state behaves consistently with the state immediately after compaction.
- F11: Token evaluation compares estimates with provider-reported anchors when both exist, reports absolute and relative error, and detects early, late, missing, or repeated compaction triggers.
- F12: Compression evaluation reports reclaimed tokens, compression ratio, retained-tail size, persisted tool-result savings, number of compactions, and whether context remains beneath declared safety margins.
- F13: Context quality is reported as a separate evaluation dimension rather than being folded only into generic efficiency or final outcome.
- F14: The context dimension includes separate evidence for retention, instruction adherence, continuity, resume consistency, token accuracy, compression efficiency, and contamination.
- F15: Missing critical facts, lost mandatory instructions, broken tool-call pairing, session-resume divergence, context overflow, or survival of explicitly forbidden stale facts can be declared hard gates.
- F16: Context findings identify the stage and checkpoint where a failure first became observable and include concise expected-versus-actual evidence.
- F17: Each run persists a normalized context timeline and context metrics alongside existing raw events, trajectory, patch, score, and Markdown artifacts.
- F18: Suite reports and baseline comparison include context score, retention rate, token-estimation error, compression ratio, compaction count, and resume consistency.
- F19: The repository includes deterministic reference cases for successful retention, critical-fact loss, stale-fact contamination, instruction-priority failure, broken resume, token-estimation drift, and excessive or ineffective compaction.
- F20: Smoke context cases run without credentials. Real-provider context cases are opt-in and are excluded from mandatory PR checks unless explicitly enabled by repository configuration.
- F21: Existing evaluation cases, reports, and non-interactive event consumers remain backward compatible when context expectations are absent.

## Non-Functional Requirements

- N1: Deterministic context cases produce equivalent normalized timelines, metrics, and scores across repeated runs and supported operating systems.
- N2: Mandatory context evaluation completes offline and does not require paid APIs.
- N3: Real-model probe variability is represented through repetition statistics and baseline thresholds rather than exact text equality.
- N4: Evaluation inputs and artifacts remain versioned, validated, bounded in size, and safe to retain in CI.
- N5: Context instrumentation adds negligible behavior change to normal Agent execution and does not expose model credentials or unbounded conversation text.
- N6: A new context check or metric can be added without changing real or scripted runner lifecycle ownership.
- N7: Context cases have explicit limits for stages, turns, context events, wall-clock time, and provider usage.
- N8: Failures distinguish Agent failure, framework failure, context expectation failure, timeout, and unsupported instrumentation.
- N9: The implementation supports the project's Python 3.11 minimum and Windows, Linux, and macOS execution model.

## Out Of Scope

- Replacing the existing two-layer context-management algorithm in this implementation cycle.
- Automatically selecting new production compaction thresholds based on evaluation results.
- A required LLM-as-judge grader for deterministic CI.
- Exact output-text equality across different model providers.
- Evaluating long-term memory extraction quality beyond context injected or restored for the active task.
- A hosted evaluation dashboard or remote artifact service.
- Voice-session context evaluation.
- Public benchmark submission or comparison with third-party coding agents.

## Acceptance Criteria

- AC1: A deterministic multi-stage case can seed facts and instructions, create context pressure, cross a compact boundary, issue probes, and complete without network access.
- AC2: Normalized events show when and why compaction or tool-result persistence occurred, including before/after token and message evidence when available.
- AC3: A passing retention case proves that all declared critical facts, active instructions, and task-state claims remain available after compaction.
- AC4: A stale-fact case fails when a superseded value appears in the final answer or drives a subsequent tool action.
- AC5: An instruction-priority case distinguishes active instructions from superseded instructions and produces a hard-gate failure when mandatory constraints are lost.
- AC6: A continuity case verifies complete tool-use/tool-result pairs, current target files, prior edits, known failures, and the expected next action after compaction.
- AC7: A resume case persists a compact boundary, reconstructs the session, and verifies equivalent declared context state before and after resume.
- AC8: A token-accounting case reports estimate error against provider-shaped usage anchors and detects a compaction trigger outside the declared tolerance.
- AC9: A compression case reports before/after tokens, reclaimed tokens, ratio, retained-tail size, spill savings, and compaction count.
- AC10: Case scores contain a separate context dimension with retention, adherence, continuity, resume, token, compression, and contamination findings.
- AC11: Any declared critical context hard-gate failure fails the case regardless of the other dimension scores.
- AC12: Run artifacts include `context-events.jsonl` and `context-metrics.json`, and Markdown reports point to both files and the exact failed checkpoint.
- AC13: Baseline comparison classifies context regressions and improvements using declared suite thresholds and returns the existing regression exit code.
- AC14: Context smoke and failure-reference cases validate through the existing CLI, and the smoke selection passes offline.
- AC15: Optional real-model probes use the same schema and report pipeline, include repetition statistics, and remain excluded from mandatory CI by default.
- AC16: Existing non-context cases continue to validate and retain their previous scoring behavior.
- AC17: All existing and new backend tests pass, deterministic context smoke runs twice with equivalent normalized evidence, and generated artifacts contain no configured secret.
