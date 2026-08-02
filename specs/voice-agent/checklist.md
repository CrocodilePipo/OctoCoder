# OctoCoder Voice Agent MVP Checklist

Each item must be verified by running code or observing behavior. Items that require live speech credentials must not be marked complete using mocked tests alone.

## Implementation Completeness

- [x] Optional voice configuration loads without breaking an existing text-only configuration. (Verification: run `uv run pytest tests/test_voice_config.py` and observe the legacy-config test pass.)
- [x] Enabled voice configuration requires Base URL, API Key or environment fallback, STT model, TTS model, and voice name. (Verification: run the invalid-enabled-settings cases in `tests/test_voice_config.py` and observe normalized validation errors.)
- [ ] Saved voice API keys are write-only and absent from configuration status and diagnostics. (Verification: save a test key, request config status, export diagnostics, and search both outputs for the literal test key; expect no match.)
- [x] The provider sends OpenAI-compatible transcription and speech requests with configurable endpoints and models. (Verification: run `uv run pytest tests/test_voice_provider.py` and inspect mocked requests for `/audio/transcriptions` and `/audio/speech`.)
- [x] Provider HTTP failures, malformed responses, empty transcripts, and non-audio speech responses become sanitized recoverable errors. (Verification: run the provider failure cases and expect typed provider exceptions without API-key content.)
- [x] Final-response processing removes fenced code, raw URLs, and markdown decoration and splits long Chinese/English prose into segments no longer than 3500 characters. (Verification: run `uv run pytest tests/test_voice_text.py` and observe all extraction/segmentation cases pass.)
- [ ] The renderer exposes idle, permission, recording, transcribing, speaking, and error states. (Verification: exercise each state with mocked socket/media events and observe the composer status/control update without changing dimensions.)
- [ ] Recording cleanup stops media tracks and timers after stop, cancel, timeout, error, disconnect, and unmount. (Verification: exercise each terminal path with instrumented media mocks or browser DevTools and observe no live audio track or recording timer remains.)
- [ ] Playback cleanup releases object URLs and queued audio after completion, stop, error, and unmount. (Verification: instrument URL creation/revocation and observe each created URL is revoked.)
- [ ] The 120-second recording limit and 16 MiB upload limit are enforced by both client and backend. (Verification: run backend boundary tests and simulate client timeout/oversize blobs; observe a visible error and no Agent submission.)

## Integration

- [x] The WebSocket accepts JSON voice controls and one binary recording frame in the defined order. (Verification: run `uv run pytest tests/test_voice_remote.py -k upload` and observe valid ordering succeed and invalid ordering fail recoverably.)
- [x] Manual mode returns a transcript to the composer without executing it. (Verification: submit a mocked recording with `auto_submit=false`; observe `voice_transcript.submitted=false`, editable composer text, and zero Agent calls.)
- [x] Automatic mode submits one transcription exactly once. (Verification: submit a mocked recording with `auto_submit=true`; observe one user timeline item and exactly one Agent invocation.)
- [ ] A manually reviewed transcript retains voice origin when submitted. (Verification: edit returned text, submit it, and observe the backend receives `source=voice` with the original request ID.)
- [ ] Voice-origin tasks use the currently active workspace and existing conversation. (Verification: select a fixture project, submit a voice task, and observe the Agent work directory and conversation match the selected project/session.)
- [ ] Voice-origin tasks use the existing permission checker and cannot approve permissions through voice messages. (Verification: trigger a write or command permission request and observe execution waits for an explicit existing UI permission response.)
- [x] Typed tasks remain unchanged and do not trigger TTS. (Verification: submit a typed task with voice enabled and observe normal text streaming with zero speech-provider calls.)
- [x] Only the latest successful non-tool final turn from a voice task reaches TTS. (Verification: run a fake Agent sequence containing thinking, tool use/result, permission, intermediate text, and final text; assert only sanitized final text reaches the provider.)
- [ ] Synthesized audio is sent only to the WebSocket that initiated the voice task. (Verification: connect two fake clients, initiate voice from one, and observe only that connection receives `voice_audio_start` and its binary frame.)
- [ ] Stopping playback does not cancel or modify the coding task or conversation. (Verification: stop audio during playback and observe no `cancel` message, while the completed response remains in the timeline.)
- [ ] A failed STT or TTS request leaves the WebSocket, backend, typed composer, and conversation usable. (Verification: inject provider failures, then submit a typed task successfully on the same connection.)
- [ ] Disabling voice prevents recording execution while leaving typed submission enabled. (Verification: disable voice in settings and observe the microphone control unavailable and the send button still functional.)
- [ ] Electron permits trusted audio-only microphone requests and rejects video or untrusted-origin media requests. (Verification: exercise permission handlers with trusted audio, trusted video, and untrusted audio fixtures; expect allow, deny, and deny.)
- [x] Electron context isolation and disabled renderer Node integration remain unchanged. (Verification: inspect the created `BrowserWindow` options and run the packaged renderer without direct `require` access.)

## Build And Tests

- [x] Focused voice backend tests pass. (Verification: run `uv run pytest tests/test_voice_config.py tests/test_voice_provider.py tests/test_voice_text.py tests/test_voice_remote.py` from `herness` and expect zero failures.)
- [ ] The complete backend test suite passes. (Verification: run `uv run pytest` from `herness` and expect zero failures.)
- [x] The React/TypeScript production client builds successfully. (Verification: run `npm.cmd run build` from `client` and expect `tsc` and Vite to exit successfully.)
- [x] Electron entry files pass JavaScript syntax checks. (Verification: run `node --check src/main.cjs` and `node --check src/preload.cjs` from `desktop` and expect exit code 0.)
- [x] The bundled backend and desktop application package build successfully. (Verification: run `npm.cmd run package` from `desktop` and verify `out/OctoCoder-win32-x64/OctoCoder.exe` and the platform backend executable exist.)
- [x] The packaged application starts without a terminal window and remains running through the startup smoke interval. (Verification: launch the packaged executable, wait at least 12 seconds, and observe the UI remains open with the backend status connected.)

## End-To-End Scenarios

- [ ] Manual-review scenario: enable valid voice settings, record a spoken coding request, stop recording, edit the transcript, and submit it; the Agent executes the edited text in the current workspace and plays only the final reply. (Verification: observe recording/transcribing states, editable text before submission, normal Agent timeline, and final audio playback.)
- [ ] Automatic-submit scenario: enable automatic submission and record one request; the transcript appears once and the Agent starts exactly once without another click. (Verification: observe one user timeline entry, one task execution, and one final TTS playback sequence.)
- [ ] Permission-safety scenario: issue a voice request that requires a filesystem or command permission; speech does not grant it and execution waits for the existing permission buttons. (Verification: deny once and observe the tool is not executed; repeat and explicitly allow through UI to observe normal execution.)
- [ ] Microphone-denied scenario: reject operating-system microphone access; OctoCoder shows an actionable error and a typed task still works immediately afterward. (Verification: deny permission, then submit text successfully without restarting the app.)
- [ ] Provider-failure scenario: configure an invalid speech endpoint or key; the failure is visible, no secret appears in the error, and the existing text Agent remains usable. (Verification: trigger STT and TTS failures and inspect both UI error text and diagnostics.)
- [ ] Limit scenario: let a recording reach 120 seconds or inject an oversized payload; recording stops or is rejected, no task executes, and a clear size/duration message is shown. (Verification: observe the composer return to a recoverable state and accept a later short recording.)
- [ ] Playback-stop scenario: use a response long enough to create multiple speech segments, stop during the first segment, and verify remaining segments do not play while the full text response remains visible. (Verification: observe the playback queue clear and no Agent cancellation.)
- [ ] Packaged Windows scenario: from `OctoCoder.exe`, configure voice services and complete record -> transcribe -> Agent/tool permission -> final TTS without opening or requiring a separate terminal process. (Verification: observe the complete flow in the packaged application and confirm no separate backend console window appears.)

## Multi-Provider Extension

- [x] Settings list SiliconFlow, Alibaba Cloud Model Studio, OpenAI, and custom OpenAI-compatible providers and apply editable provider defaults.
- [x] The backend factory selects the saved provider adapter and preserves legacy configuration behavior.
- [x] SiliconFlow transcription uses only documented multipart fields, and Alibaba ASR/TTS use their provider-specific request and response contracts.
- [x] Unknown provider identifiers are rejected before the existing configuration file is overwritten.
- [x] Provider status and desktop diagnostics include no API-key value.
- [x] Multi-provider focused tests and the production client build pass without external credentials.
- [x] Volcengine settings expose App ID, Access Token, optional Secret Key, resource/model, and voice fields without returning credential values.
- [x] Volcengine flash ASR and Bearer TTS request/response contracts are covered with mocked transport and fake credentials.
- [x] Volcengine recordings are encoded locally as 16 kHz mono PCM WAV before upload.

## Verification Record

- 2026-08-02: focused backend voice suite passed with `33 passed`.
- 2026-08-02: multi-provider focused backend voice suite passed with `41 passed`; React/TypeScript production build passed.
- 2026-08-02: the expanded full suite completed with `601 passed, 3 skipped` in the managed sandbox; the three filesystem-permission cases passed separately outside the sandbox.
- 2026-08-02: the multi-provider PyInstaller backend and desktop directory package were rebuilt; the packaged process remained running for the 15-second smoke interval.
- 2026-08-02: Volcengine focused voice tests passed as part of `47 passed`; the renderer production build passed with the provider-specific WAV recorder path.
- 2026-08-02: the Volcengine-expanded backend suite completed with `607 passed, 3 skipped` in the managed sandbox; the three filesystem-permission cases passed separately outside the sandbox. The Windows package was rebuilt and remained running for the 15-second smoke interval.
- 2026-08-02: corrected Volcengine TTS authorization to the exact `Bearer;<token>` form and added normalization for accidentally pasted `Bearer;` prefixes.
- 2026-08-02: added Volcengine App ID format validation and reordered the settings fields to prevent App ID/Access Token reversal.
- 2026-08-02: the normal full-suite run completed with `592 passed, 3 skipped`; three existing tests that write outside the workspace were blocked by the execution sandbox, and those three passed in a separate unrestricted run. The single-run full-suite item remains unchecked because the managed environment could not provide one filesystem context suitable for both groups.
- 2026-08-02: the React production build and both Electron syntax checks passed.
- 2026-08-02: PyInstaller rebuilt `desktop/backend-dist/win32-x64`, local desktop packaging completed, and the final packaged process remained running for 15 seconds.
- Provider-credential, operating-system microphone, audible playback, and complete packaged voice-flow checks remain user acceptance items and are intentionally unchecked.
