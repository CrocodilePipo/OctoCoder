# OctoCoder Realtime Voice Checklist

Each item must be verified by running code or observing behavior. Mocked provider checks and live-provider checks are recorded separately; a mocked check cannot be used to mark a live credential or audible playback check complete.

## Implementation Completeness

- [ ] Legacy single-provider voice configuration loads as one `default` profile without rewriting the source YAML. (Verification: run the legacy migration cases in `tests/test_voice_config.py`; compare the config file bytes before and after load and expect no change.)
- [ ] Saving migrated settings writes the profile schema while preserving every omitted write-only credential. (Verification: run the migration-save test with literal fake secrets, reload the YAML, and expect profile references plus unchanged secrets.)
- [ ] ASR-only configuration is ready without a TTS model or voice. (Verification: run the ASR-only configuration test and expect `configured=true`, `ttsConfigured=false`, and no validation error.)
- [ ] TTS enablement and readiness are independent from ASR readiness. (Verification: toggle TTS in configuration tests and observe ASR readiness remains unchanged while TTS readiness follows its selected profile.)
- [ ] Profile IDs are unique and primary, fallback, and TTS references must resolve to existing capable profiles. (Verification: run invalid profile/reference/capability tests and expect precise configuration errors.)
- [ ] Provider status and diagnostics expose profile/provider IDs and readiness booleans but no API Key, App ID, Secret Key, transcript, or audio. (Verification: save unique literal test secrets/content, request status/export diagnostics, search outputs for every literal, and expect no match.)
- [ ] Provider failures are classified as transport, timeout, rate-limit, server, authentication, authorization, invalid request, unsupported format, or invalid response. (Verification: run classification cases in `tests/test_voice_provider.py` and inspect `kind` and `retryable` assertions.)
- [ ] Only transport, timeout, rate-limit, interrupted-response, and server failures are retryable. (Verification: run the retryability parameterized test and expect 401/403/4xx format/configuration cases to be non-retryable.)
- [ ] PCM16 validation and WAV recovery encoding preserve mono 16 kHz samples and produce a valid RIFF/WAVE header. (Verification: run `uv run pytest tests/test_voice_audio.py` and inspect header/sample assertions.)
- [ ] Alibaba streaming ASR sends authenticated `run-task`, waits for `task-started`, sends binary PCM, sends `finish-task`, and waits for `task-finished`. (Verification: run the fake-WebSocket command-order test in `tests/test_voice_streaming_provider.py`.)
- [ ] Alibaba heartbeat results are ignored and partial sentence revisions replace previous revisions instead of duplicating text. (Verification: replay heartbeat and repeated `result-generated` events in the provider tests and expect one normalized caption.)
- [ ] Alibaba sentence-final events accumulate by sentence ID into one final transcript. (Verification: replay multiple final sentences and expect one ordered transcript exactly once.)
- [ ] Alibaba handshake 401/403, `task-failed`, malformed JSON, timeout, and early close map to sanitized classified errors. (Verification: run all failure cases with fake keys and confirm error strings contain no credential.)
- [ ] Client audio is captured through AudioWorklet as bounded 16 kHz mono PCM16 frames of approximately 100 ms. (Verification: run `src/voice/pcm.test.ts` with synthetic source-rate frames and inspect output format/frame-size assertions.)
- [ ] Client and Harness enforce duration, utterance-size, frame-size, queue, and WebSocket backpressure limits. (Verification: run client PCM boundary tests and backend session queue/size tests; expect recoverable errors and no Agent submission.)
- [ ] AudioWorklet, AudioContext, media tracks, VAD instance, timers, queues, object URLs, and upstream WebSockets are released on every terminal path. (Verification: run instrumented client cleanup tests and backend cancel/disconnect tests; expect each resource's close/stop/destroy/revoke method exactly once.)

## Realtime Transcription

- [ ] Pressing and holding the microphone enters permission/connecting/listening states and opens one realtime request. (Verification: run the hold-start client state test and observe one `voice_stream_start` with one stable request ID.)
- [ ] Audio captured before `voice_stream_ready` remains bounded and flushes in sequence after readiness. (Verification: delay the ready event in the client test, emit several frames, then expect ordered sequence numbers after ready.)
- [ ] Partial transcript text is visible while holding and is throttled to no more than ten React updates per second. (Verification: emit rapid partial revisions in a fake-timer test and inspect rendered caption/update count.)
- [ ] Releasing inside or outside the microphone button sends one finish after all queued frames and submits one final transcript. (Verification: run pointer-capture/release tests and backend protocol tests; expect one finish and one Agent call.)
- [ ] Keyboard press/release on the focused microphone provides equivalent hold behavior. (Verification: dispatch the supported key events in a component test and expect the same start/finish sequence.)
- [ ] Cancelling, releasing silence, denied microphone access, empty recognition, and stale request events produce no Agent submission. (Verification: run client/backend negative cases and assert Agent handler call count is zero.)
- [ ] Non-monotonic sequence, mismatched byte length, duplicate finish, and unsolicited binary frames are rejected recoverably. (Verification: run malformed protocol cases and expect `voice_error` while the main WebSocket remains usable.)
- [ ] A stable request ID survives streaming, fallback, final transcript, and Agent submission. (Verification: inspect one fallback test's captured messages and expect the same request ID everywhere.)
- [ ] A late streaming final after fallback starts cannot publish or submit a second transcript. (Verification: release the fake late-final barrier after batch fallback succeeds and expect one transcript event and one Agent call.)

## Fallback And Provider Profiles

- [ ] Retryable streaming failure first attempts the primary profile's batch capability, then explicitly ordered fallback profiles. (Verification: run the ordered fallback test and inspect provider invocation order.)
- [ ] Duplicate fallback profile/capability entries are called once. (Verification: configure repeated IDs and expect one invocation per unique candidate.)
- [ ] Buffered PCM is converted to WAV once and reused without asking the user to speak again. (Verification: instrument WAV encoding in the fallback test and expect one conversion with identical bytes supplied to candidates.)
- [ ] Authentication, authorization, invalid request, unsupported format, and configuration failures do not trigger fallback. (Verification: parameterize non-retryable failures and expect fallback provider call count zero.)
- [ ] Exhausting all retryable fallbacks produces one sanitized visible error and does not terminate the Harness. (Verification: make every fake candidate fail, then submit a typed message and expect it to be accepted.)
- [ ] Existing batch-only providers continue to work through legacy recording messages. (Verification: run the existing batch upload/transcription tests and expect unchanged successful behavior.)
- [ ] Profile settings can create, edit, remove, select, and order primary/fallback/TTS profiles without exposing stored secrets. (Verification: exercise settings with component/manual UI checks, save/reopen, and confirm selections persist with secret placeholders only.)

## Agent States And Safety

- [ ] A submitted voice task transitions to analyzing before Agent output. (Verification: run the voice phase test and expect analyzing immediately after final transcript submission.)
- [ ] First tool use transitions to executing and repeated tool events do not repeat the transition. (Verification: feed multiple `ToolUseEvent` instances and expect one executing event/announcement.)
- [ ] A permission request transitions to waiting for approval and only an explicit desktop permission response resolves it. (Verification: run the permission test, send unrelated voice text, and expect the permission future unresolved until the UI response message.)
- [ ] Explicit permission response returns the voice task to executing. (Verification: submit allow/deny through the existing permission-response handler and inspect the next phase.)
- [ ] Voice input cannot approve permissions, bypass permission rules, or act as authorization. (Verification: say/transcribe "确认" while a fake permission is pending and expect it to be queued/rejected as normal input, not applied to the permission future.)
- [ ] Voice-origin tasks use the selected workspace, or the default working directory when no workspace is selected. (Verification: run one voice task in each state with a fake Agent/tool and inspect the Agent working directory.)
- [ ] A continuous transcript finalized while the Agent is busy occupies one pending slot and is submitted after the active turn exits. (Verification: block a fake Agent, finalize one utterance, release the Agent, and expect ordered one-time submission.)
- [ ] A second continuous transcript while the pending slot is occupied is rejected visibly and never replaces the first. (Verification: finalize two utterances during the blocked Agent and inspect pending content and Agent call count.)
- [ ] Press-and-hold is disabled while the Agent is actively running. (Verification: render the busy state and expect hold start to be unavailable without requesting microphone access.)
- [ ] Streaming/fallback failure never closes the main chat WebSocket or terminates the Harness. (Verification: force a provider failure, then send a typed task over the same fake/real socket and expect normal handling.)

## Optional Speech And Interruption

- [ ] ASR-only mode creates no TTS provider and makes zero synthesis calls for status or final responses. (Verification: run the ASR-only remote test with a failing-if-called TTS fake and expect no call.)
- [ ] With TTS and announcements enabled, analyzing, executing, and waiting-approval are each announced at most once per relevant transition. (Verification: run the announcement deduplication test with repeated Agent events.)
- [ ] With status announcements disabled, high-level states remain visible and produce no status audio. (Verification: run the disabled-announcement test and inspect status messages plus zero status synthesis calls.)
- [ ] Final speech excludes code, tool output, diagnostics, paths, permission details, reasoning, URLs, and secrets. (Verification: pass a mixed Markdown/tool response through the TTS integration test and inspect every synthesized input.)
- [ ] The first final-response segment is sent to the renderer before later segments finish synthesis. (Verification: control per-segment fake completion barriers and expect audio metadata/binary for segment 0 while segment 1 is still blocked.)
- [ ] Renderer playback preserves segment order when audio arrives progressively. (Verification: run `src/voice/playback.test.ts` and inspect fake audio play order.)
- [ ] Starting speech or pressing stop immediately pauses playback, revokes all group URLs, and clears queued segments. (Verification: run the barge-in and stop tests with URL/audio spies.)
- [ ] Playback interruption cancels unsent synthesis for that group but does not send Agent cancellation or permission responses. (Verification: inspect socket messages and backend synthesis tasks after interruption.)
- [ ] Stale status audio cannot play over a newer final response or new utterance. (Verification: deliver delayed status audio after phase advancement and expect it to be discarded.)

## Continuous Conversation

- [ ] Continuous mode loads VAD model/worklet/WASM from packaged local assets and makes no CDN request. (Verification: search built files for `cdn.jsdelivr`, `unpkg`, and remote VAD asset URLs; expect no match, then inspect local asset requests.)
- [ ] Enabling continuous mode requests microphone access once and enters passive listening without opening an Agent task. (Verification: start with a fake VAD and expect listening state with zero Agent submissions before speech.)
- [ ] Local VAD speech start opens one stream and includes pre-speech audio so the first spoken sound is not clipped. (Verification: feed ring-buffer frames before speech start and inspect the first transmitted PCM.)
- [ ] Sustained silence at the configured threshold finalizes exactly one utterance. (Verification: use fake timers/VAD callbacks around the threshold and expect one finish.)
- [ ] VAD misfires and speech shorter than the configured minimum do not submit tasks. (Verification: trigger misfire/short-noise callbacks and expect zero finish/Agent calls.)
- [ ] After completion or recoverable ASR failure, continuous mode returns to listening until explicitly stopped. (Verification: run success and recoverable-error cycles and inspect the final state.)
- [ ] Speaking during assistant playback interrupts the audio and captures a new utterance. (Verification: begin fake playback, trigger VAD speech start, and expect pause/revoke followed by stream start.)
- [ ] Speaking during active Agent execution never automatically cancels that coding task. (Verification: block a fake Agent, trigger speech start, and expect the Agent cancellation event remains unset.)
- [ ] Stopping continuous mode releases microphone/VAD/audio resources and does not restart automatically. (Verification: stop, advance timers, emit stale callbacks, and expect destroyed resources plus idle state.)

## Integration

- [ ] Renderer control messages, declared binary PCM frames, Harness session state, Alibaba adapter, transcript events, and Agent submission use real public call sites rather than test-only helpers. (Verification: trace one integration test through the actual socket dispatcher and factories.)
- [ ] Main WebSocket ping/pong, text chat, project switching, config save, permission response, and cancellation remain functional with streaming protocol additions. (Verification: run existing remote tests plus one mixed-message integration test.)
- [ ] Settings reload cancels active voice sessions and reconstructs provider factories from the new profile configuration. (Verification: save settings during a fake active session and inspect cancellation plus new selected providers.)
- [ ] Client reconnect clears pending binary metadata, active capture, captions, playback, and stale request IDs. (Verification: run disconnect/reconnect lifecycle tests and deliver stale events afterward.)
- [ ] Typed tasks never trigger voice status announcements or final TTS unless a future explicit feature enables them. (Verification: run the existing typed-task TTS test and expect zero synthesis calls.)
- [ ] Legacy batch input, manual text input, workspace selection, and approval behavior pass their existing regression tests. (Verification: run the full backend/client suites.)

## Security And Privacy

- [ ] Alibaba credentials are sent only by the Harness during the cloud WebSocket handshake and never cross the renderer protocol. (Verification: inspect all captured renderer WebSocket messages and search for the fake credential.)
- [ ] Logs and diagnostics contain no audio bytes, Base64 audio, transcript content, synthesis payload, or provider secret. (Verification: run a voice flow with unique markers, export logs/diagnostics, and search for each marker.)
- [ ] Provider error messages are bounded and sanitized before reaching the renderer. (Verification: inject a long provider response containing a fake key and expect a bounded message without the key.)
- [ ] VAD and ONNX assets are fixed package files with no runtime script execution from remote origins. (Verification: inspect package resources and renderer network requests during continuous-mode startup.)
- [ ] Electron continues allowing audio media only for the trusted renderer and rejects video/untrusted origins. (Verification: run or manually exercise permission policy cases for packaged and development origins.)

## Build And Tests

- [x] Focused backend voice tests pass. (Verification: from `herness`, run `uv run pytest tests/test_voice_config.py tests/test_voice_provider.py tests/test_voice_audio.py tests/test_voice_streaming_provider.py tests/test_voice_streaming_remote.py tests/test_voice_remote.py`.)
- [x] Full backend tests pass, with managed-sandbox filesystem exceptions documented and separately verified when necessary. (Verification: from `herness`, run `uv run pytest`; rerun only sandbox-blocked tests with the approved filesystem context.)
- [x] Client voice tests pass. (Verification: from `client`, run `npm.cmd test -- --run`.)
- [x] Client production build passes and contains all required local voice assets. (Verification: from `client`, run `npm.cmd run build`, then inspect `dist/voice`.)
- [x] Electron main and preload syntax checks pass. (Verification: from `desktop`, run `node --check src/main.cjs` and `node --check src/preload.cjs`.)
- [x] PyInstaller backend build includes all realtime voice modules and starts successfully. (Verification: run `npm.cmd run build:backend`, launch the bundled backend with a test port, and observe its health endpoint become ready.)
- [x] Windows Electron directory package builds and remains running during the smoke interval. (Verification: run `npm.cmd run package`, launch the packaged executable for at least 15 seconds, and observe no early exit.)
- [x] Windows installer generation succeeds. (Verification: run `npm.cmd run make` and confirm the expected installer artifact exists.)
- [x] `git diff --check` reports no whitespace errors. (Verification: run `git diff --check` at the repository root.)
- [x] No local configuration, credential, generated audio, or test secret is staged for commit. (Verification: inspect `git status --short`, staged diff, and repository search for the test-secret markers.)

## End-To-End Scenarios

- [ ] Scenario 1, press-and-hold: hold microphone, speak a Chinese coding request, observe live captions, release, and observe exactly one task begin in the selected project. (Verification: packaged Windows app with a valid Alibaba profile; inspect UI timeline and backend submission log/count.)
- [ ] Scenario 2, ASR-only: remove/disable TTS settings, restart the app, complete a press-and-hold task, and observe successful execution with no spoken output or TTS error. (Verification: packaged app plus provider-call diagnostics.)
- [ ] Scenario 3, retryable fallback: interrupt the primary streaming connection after audio arrives, observe fallback status, and see one batch transcript and one task without repeating speech. (Verification: integration fault injection or a controlled proxy failure.)
- [ ] Scenario 4, non-retryable configuration error: use an invalid or unauthorized test credential, observe a configuration-oriented 401/403 error, and confirm no fallback request or Agent task occurs. (Verification: controlled fake endpoint is preferred; do not expose real credentials.)
- [ ] Scenario 5, Agent state and approval: speak a task that requires a tool approval, observe analyzing, executing, and waiting-approval, then approve through the desktop UI and observe execution continue. (Verification: packaged app with default permission mode.)
- [ ] Scenario 6, optional TTS and barge-in: enable TTS, complete a short task, hear progressive reply playback, begin speaking, and observe immediate playback interruption while the completed coding task remains intact. (Verification: packaged app with audible output and timeline inspection.)
- [ ] Scenario 7, continuous conversation: enable continuous mode, speak without pressing the microphone, pause, observe one task, receive the response, and observe listening resume. (Verification: packaged app with local VAD assets and microphone permission.)
- [ ] Scenario 8, busy Agent pending input: while a long voice task is running, speak one follow-up, observe queued status, and see it run once after the active task; a second follow-up is visibly rejected. (Verification: controlled long-running fake or real task.)
- [ ] Scenario 9, recovery: after a provider failure, submit a typed task over the same connection and confirm normal operation without restarting OctoCoder. (Verification: packaged app or full socket integration test.)
- [ ] Scenario 10, package privacy: complete voice scenarios, export diagnostics, and confirm credentials, transcript text, and audio markers are absent. (Verification: literal-marker search in exported diagnostics/log directory.)

## Acceptance Record

Record each command, pass count, artifact path, live-provider result, and any user-acceptance-only item here during implementation. Do not mark an item complete without the stated evidence.

- 2026-08-02: focused backend voice suite passed, 87 tests.
- 2026-08-02: full backend suite passed, 656 tests with 3 skipped. Three filesystem-sandbox failures were rerun with the required temporary/user-directory access and all 3 passed.
- 2026-08-02: client Vitest suite passed, 6 tests across voice state and playback.
- 2026-08-02: TypeScript/Vite production build passed; seven local VAD/ONNX/worklet files were present under `client/dist/voice`, and no CDN reference was found.
- 2026-08-02: Electron main/preload syntax checks and `git diff --check` passed.
- 2026-08-02: PyInstaller backend health endpoint returned HTTP 200 from the packaged executable.
- 2026-08-02: Windows directory package remained alive for the 15-second smoke interval at `desktop/out/OctoCoder-win32-x64/OctoCoder.exe`.
- 2026-08-02: Squirrel artifacts validated at `desktop/out/make/squirrel.windows/x64`; Squirrel emitted a non-fatal `rcedit` metadata warning after writing the validated artifacts.
- 2026-08-02: production npm dependency audit reported zero vulnerabilities; supplied credential literals were absent from the source tree.
- User-acceptance pending: live Alibaba microphone scenarios, audible TTS/barge-in, and continuous-conversation scenarios require an interactive packaged-app run with the user's valid provider entitlement.
- Visual automation note: the configured in-app browser runtime could not initialize its local kernel asset directory; production build and executable smoke validation completed, but automated screenshot review was not recorded.
