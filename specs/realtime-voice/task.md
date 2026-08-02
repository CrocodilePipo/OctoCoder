# OctoCoder Realtime Voice Tasks

## File List

| Action | File | Responsibility |
| --- | --- | --- |
| Modify | `herness/octocoder/config.py` | Add provider profiles, ASR-only readiness, TTS readiness, and legacy migration. |
| Modify | `herness/octocoder/validator.py` | Validate profile capabilities, references, feature toggles, and migration input. |
| Modify | `herness/octocoder/remote.py` | Persist/redact profiles, dispatch streaming protocol, map Agent states, and coordinate pending input. |
| Modify | `herness/octocoder/voice/provider.py` | Split provider capabilities and classify provider failures. |
| Modify | `herness/octocoder/voice/factory.py` | Add batch ASR, streaming ASR, and TTS factories. |
| Modify | `herness/octocoder/voice/openai_compatible.py` | Map HTTP failures into retry classifications. |
| Modify | `herness/octocoder/voice/aliyun.py` | Consume profile configuration and remain the Aliyun batch/TTS adapter. |
| Modify | `herness/octocoder/voice/siliconflow.py` | Consume profile configuration and classified failures. |
| Modify | `herness/octocoder/voice/volcengine.py` | Consume profile configuration and classified failures. |
| Modify | `herness/octocoder/voice/models.py` | Extend audio/stream data structures and constants. |
| Modify | `herness/octocoder/voice/text.py` | Support shorter progressive speech segments. |
| Modify | `herness/octocoder/voice/__init__.py` | Export new realtime voice interfaces. |
| Create | `herness/octocoder/voice/audio.py` | Validate PCM and encode buffered PCM as WAV. |
| Create | `herness/octocoder/voice/aliyun_streaming.py` | Implement Alibaba duplex WebSocket ASR. |
| Create | `herness/octocoder/voice/fallback.py` | Select retryable ordered batch fallback candidates. |
| Create | `herness/octocoder/voice/session.py` | Own realtime stream state, queues, finalization, and exactly-once submission. |
| Create | `herness/octocoder/voice/speech.py` | Schedule optional status/final TTS and cancellation groups. |
| Modify | `herness/tests/test_voice_config.py` | Cover profiles, migration, ASR-only readiness, and redaction. |
| Modify | `herness/tests/test_voice_provider.py` | Cover split factories and classified HTTP failures. |
| Modify | `herness/tests/test_voice_remote.py` | Cover optional TTS and Agent voice phases. |
| Create | `herness/tests/test_voice_audio.py` | Cover PCM/WAV conversion and bounds. |
| Create | `herness/tests/test_voice_streaming_provider.py` | Cover Alibaba WebSocket command/event behavior. |
| Create | `herness/tests/test_voice_streaming_remote.py` | Cover local protocol, fallback, deduplication, and pending input. |
| Modify | `client/package.json` | Add pinned VAD/test dependencies and scripts. |
| Modify | `client/package-lock.json` | Lock new frontend dependencies. |
| Create | `client/scripts/copy-voice-assets.mjs` | Copy pinned VAD/ONNX assets into Vite output. |
| Create | `client/public/voice/pcm-worklet.js` | Convert microphone frames to mono PCM16. |
| Modify | `client/src/types.ts` | Add profile, phase, stream, partial transcript, and audio-group types. |
| Modify | `client/src/socket.ts` | Add client binary metadata ordering and backpressure reporting. |
| Create | `client/src/voice/pcm.ts` | Implement bounded PCM buffering and WAV recovery encoding. |
| Create | `client/src/voice/realtimeCapture.ts` | Own AudioWorklet capture and frame batching. |
| Create | `client/src/voice/turnDetector.ts` | Own local Silero VAD and continuous-turn lifecycle. |
| Modify | `client/src/voice/recorder.ts` | Retain legacy batch capture and share audio constants. |
| Modify | `client/src/voice/playback.ts` | Add grouped, prioritized, interruptible playback. |
| Modify | `client/src/voice/useVoiceAgent.ts` | Implement hold, streaming captions, fallback recovery, continuous mode, and cleanup. |
| Modify | `client/src/App.tsx` | Add realtime controls, captions, state, and profile settings. |
| Modify | `client/src/styles.css` | Style compact realtime and continuous voice states. |
| Create | `client/src/voice/pcm.test.ts` | Cover PCM buffering and WAV recovery. |
| Create | `client/src/voice/playback.test.ts` | Cover group ordering and interruption cleanup. |
| Create | `client/src/voice/voiceState.test.ts` | Cover voice state and exactly-once client behavior. |
| Modify | `desktop/scripts/build-client.cjs` | Verify VAD assets are included in the client build. |
| Modify | `desktop/src/main.cjs` | Extend sanitized diagnostics while preserving microphone policy. |

## T1: Add Profile-Based Voice Configuration

**Files:** `herness/octocoder/config.py`, `herness/octocoder/validator.py`, `herness/tests/test_voice_config.py`

**Dependencies:** None

**Steps:**

1. Add `VoiceProviderProfile` with independent batch ASR, streaming ASR, and TTS readiness properties.
2. Replace combined voice readiness with ASR-only `configured`, independent `streaming_configured`, and independent `tts_configured`.
3. Add primary ASR, ordered fallback, TTS profile, continuous mode, silence, and announcement settings.
4. Normalize a legacy single-provider mapping into a `default` profile without modifying the source file during load.
5. Validate unique profile IDs, valid references, supported providers, booleans, silence bounds, and capability requirements.
6. Add tests for legacy configuration, ASR-only configuration, optional TTS, invalid references, and environment credential fallback.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_config.py` and expect all configuration tests to pass.

## T2: Persist And Redact Provider Profiles

**Files:** `herness/octocoder/remote.py`, `herness/octocoder/config.py`, `herness/tests/test_voice_config.py`

**Dependencies:** T1

**Steps:**

1. Extend configuration status with profile capability booleans and selected profile IDs.
2. Accept profile-based settings saves while preserving omitted write-only credentials profile by profile.
3. Migrate a legacy mapping to the new schema only when the user saves settings.
4. Ensure API keys, App IDs, Secret Keys, transcript content, and audio never appear in status payloads.
5. Add save/reload tests with two profiles and literal-secret absence assertions.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_config.py -k "profile or redact or legacy or save"` and expect all selected tests to pass.

## T3: Split Provider Capabilities And Classify Errors

**Files:** `herness/octocoder/voice/provider.py`, `herness/octocoder/voice/factory.py`, `herness/octocoder/voice/openai_compatible.py`, `herness/octocoder/voice/aliyun.py`, `herness/octocoder/voice/siliconflow.py`, `herness/octocoder/voice/volcengine.py`, `herness/octocoder/voice/__init__.py`, `herness/tests/test_voice_provider.py`

**Dependencies:** T1

**Steps:**

1. Define batch ASR, streaming ASR, and TTS protocols plus classified provider errors.
2. Add capability-specific factories that reject unsupported capabilities with sanitized errors.
3. Update existing adapters to consume `VoiceProviderProfile` and retain their current request contracts.
4. Classify transport, timeout, interrupted response, 429, 5xx, 401, 403, invalid request, format, and malformed response failures.
5. Preserve compatibility for existing test fakes and batch behavior where practical.
6. Add factory and classification tests using mocked HTTP transports.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_provider.py` and expect all provider tests to pass without network access.

## T4: Add PCM And WAV Utilities

**Files:** `herness/octocoder/voice/audio.py`, `herness/octocoder/voice/models.py`, `herness/octocoder/voice/__init__.py`, `herness/tests/test_voice_audio.py`

**Dependencies:** T1

**Steps:**

1. Define PCM16 sample rate, channel count, frame, utterance, and queue limits.
2. Validate PCM byte alignment and cumulative size.
3. Encode mono 16 kHz PCM16 bytes into a standards-compliant WAV buffer without external tools.
4. Add tests for headers, payload preservation, empty input, odd-byte input, and size boundaries.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_audio.py` and expect all tests to pass.

## T5: Implement Alibaba Streaming ASR

**Files:** `herness/octocoder/voice/aliyun_streaming.py`, `herness/octocoder/voice/factory.py`, `herness/octocoder/voice/__init__.py`, `herness/tests/test_voice_streaming_provider.py`

**Dependencies:** T3, T4

**Steps:**

1. Open the configured Alibaba WebSocket with Bearer authentication, optional workspace header, heartbeat, and explicit timeouts.
2. Send `run-task` for `qwen-audio-3.0-asr-flash-streaming` with duplex PCM16/16 kHz parameters.
3. Wait for `task-started` before accepting audio and send each PCM frame as binary.
4. Parse heartbeat, partial, sentence-final, task-finished, and task-failed events into normalized transcription events.
5. Send `finish-task`, accumulate sentence revisions by ID, and return one normalized final transcript.
6. Implement deterministic cancellation and classify handshake, timeout, close, malformed event, and task failures.
7. Test the complete command/event sequence using an injected fake WebSocket connector.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_streaming_provider.py` and expect all protocol tests to pass without live credentials.

## T6: Implement Ordered Batch Fallback

**Files:** `herness/octocoder/voice/fallback.py`, `herness/octocoder/voice/factory.py`, `herness/tests/test_voice_streaming_remote.py`

**Dependencies:** T3, T4

**Steps:**

1. Build the candidate order from primary batch capability followed by configured fallback profiles.
2. Remove duplicate profile/capability candidates while preserving order.
3. Attempt fallback only for retryable classified failures.
4. Convert buffered PCM to WAV once and reuse it across candidates.
5. Stop on the first non-empty transcript or return one sanitized aggregate failure.
6. Test retryable progression, non-retryable stop, candidate deduplication, and exhausted fallback.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_streaming_remote.py -k fallback` and expect all fallback tests to pass.

## T7: Implement Realtime Session State And Exactly-Once Gate

**Files:** `herness/octocoder/voice/session.py`, `herness/octocoder/voice/models.py`, `herness/tests/test_voice_streaming_remote.py`

**Dependencies:** T5, T6

**Steps:**

1. Create one bounded realtime session per connection/request with an audio queue and PCM buffer.
2. Validate monotonic chunk sequences, declared byte lengths, duration, payload, finish, and cancel order.
3. Run independent upstream sender and transcript receiver tasks so cloud latency never blocks the local socket loop.
4. Drain queued audio before provider finish and ignore late events after fallback starts.
5. Guard finalization and Agent submission with monotonic locks/flags.
6. Release worker tasks, queue contents, PCM, and upstream connections on every terminal path.
7. Test duplicate finish, late final, queue overflow, cancellation, and race conditions.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_streaming_remote.py -k "session or sequence or duplicate or late or cancel"` and expect all selected tests to pass.

## T8: Add Harness Streaming WebSocket Protocol

**Files:** `herness/octocoder/remote.py`, `herness/octocoder/voice/session.py`, `herness/tests/test_voice_streaming_remote.py`

**Dependencies:** T2, T7

**Steps:**

1. Dispatch stream start/chunk/finish/cancel/recovery and playback-interrupt control messages.
2. Pair each declared client chunk or recovery upload with exactly one following binary message.
3. Send stream-ready, partial transcript, final transcript, fallback status, and recoverable errors only to the initiating connection.
4. Keep legacy batch `voice_record_*` handling available for batch-only profiles.
5. Submit final press-and-hold transcripts automatically through the existing voice-origin Agent path.
6. Clear pending binary metadata and realtime sessions on client disconnect or settings reload.
7. Test valid and invalid protocol order, partial delivery, release submission, and chat-socket survival after failure.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_streaming_remote.py -k "protocol or partial or submit or recovery or disconnect"` and expect all selected tests to pass.

## T9: Add Agent Voice States And One Pending Continuous Input

**Files:** `herness/octocoder/remote.py`, `herness/tests/test_voice_remote.py`, `herness/tests/test_voice_streaming_remote.py`

**Dependencies:** T8

**Steps:**

1. Emit analyzing after voice transcript submission, executing on first tool use, and waiting-approval on permission request.
2. Return to executing after an explicit UI permission response and to idle/speaking on terminal Agent events.
3. Suppress repeated phase events for repeated tool calls.
4. Add one pending continuous transcript slot while the Agent is busy.
5. Submit the pending transcript after the active run exits and reject a second pending utterance visibly.
6. Ensure press-and-hold remains unavailable while an Agent turn is active.
7. Test phase ordering, permission safety, pending submission, and rejection of overflow input.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_remote.py tests/test_voice_streaming_remote.py -k "phase or approval or pending or busy"` and expect all selected tests to pass.

## T10: Make TTS Optional And Add Speech Scheduling

**Files:** `herness/octocoder/voice/speech.py`, `herness/octocoder/voice/text.py`, `herness/octocoder/remote.py`, `herness/tests/test_voice_remote.py`

**Dependencies:** T3, T9

**Steps:**

1. Construct a TTS provider only when TTS is enabled and its selected profile is ready.
2. Skip all synthesis when ASR-only mode is active.
3. Map analyzing, executing, and waiting-approval to one localized announcement per transition.
4. Cache fixed status audio in memory by provider/model/voice/language.
5. Split final speakable text into short ordered segments and send each immediately after synthesis.
6. Assign playback group IDs and cancel unsent status/final synthesis after an interrupt message.
7. Keep code, tool output, diagnostics, paths, permission details, and failed/cancelled tasks out of TTS.
8. Test ASR-only zero-call behavior, announcement deduplication, progressive segment order, and interruption.

**Verification:** From `herness`, run `uv run pytest tests/test_voice_remote.py -k "tts or speech or announcement or interrupt or asr_only"` and expect all selected tests to pass.

## T11: Add Client Voice Dependencies And Local Assets

**Files:** `client/package.json`, `client/package-lock.json`, `client/scripts/copy-voice-assets.mjs`, `desktop/scripts/build-client.cjs`

**Dependencies:** None

**Steps:**

1. Add pinned `@ricky0123/vad-web`, compatible ONNX Runtime Web, Vitest, and browser test environment dependencies.
2. Add build/test scripts and update the npm lock file.
3. Copy the required VAD model, worklet, and WASM files from installed packages into `client/dist/voice` after Vite builds.
4. Fail the client/desktop build when a required runtime asset is missing.
5. Avoid CDN URLs in generated application code and assets.

**Verification:** From `client`, run `npm.cmd install`, `npm.cmd run build`, and inspect `dist/voice`; expect the pinned model/worklet/WASM assets to exist locally.

## T12: Implement PCM Worklet And Bounded Capture

**Files:** `client/public/voice/pcm-worklet.js`, `client/src/voice/pcm.ts`, `client/src/voice/realtimeCapture.ts`, `client/src/voice/recorder.ts`, `client/src/voice/pcm.test.ts`

**Dependencies:** T11

**Steps:**

1. Capture one audio-only microphone stream with echo cancellation and noise suppression.
2. Resample incoming audio to mono 16 kHz and convert it to signed PCM16 in an AudioWorklet.
3. Batch worklet output into approximately 100 ms frames.
4. Retain a bounded utterance buffer and encode it as WAV for recovery.
5. Enforce duration, payload, local queue, and cleanup bounds across finish, cancel, error, and dispose.
6. Keep the existing MediaRecorder/WAV recorder for legacy batch mode.
7. Test PCM conversion, WAV output, queue limits, and cleanup with browser API mocks.

**Verification:** From `client`, run `npm.cmd test -- --run src/voice/pcm.test.ts` and `npm.cmd run build`; expect tests and TypeScript/Vite build to pass.

## T13: Extend Client Socket And Protocol Types

**Files:** `client/src/types.ts`, `client/src/socket.ts`, `client/src/voice/voiceState.test.ts`

**Dependencies:** T8, T12

**Steps:**

1. Add provider-profile settings, independent ASR/TTS readiness, expanded voice phases, and realtime message unions.
2. Add ordered client metadata/binary sending helpers.
3. Expose socket buffered amount and reject sends over the configured backpressure threshold.
4. Pair server TTS metadata/binary frames by audio ID and clear pending metadata on reconnect.
5. Test malformed ordering, disconnect cleanup, and backpressure behavior.

**Verification:** From `client`, run `npm.cmd test -- --run src/voice/voiceState.test.ts` and `npm.cmd run build`; expect both to pass.

## T14: Implement Press-And-Hold Realtime Transcription

**Files:** `client/src/voice/useVoiceAgent.ts`, `client/src/voice/realtimeCapture.ts`, `client/src/App.tsx`, `client/src/types.ts`, `client/src/voice/voiceState.test.ts`

**Dependencies:** T12, T13

**Steps:**

1. Start capture and a backend stream on microphone pointer/key down.
2. Buffer audio until stream-ready, then flush and continue ordered realtime frames.
3. Display throttled partial transcript separately from editable composer text.
4. Finish on pointer/key release even when release occurs outside the button.
5. Automatically submit one final transcript and clear the local buffer only after terminal acknowledgement.
6. Cancel silence, empty results, pointer cancellation, permission denial, and connection loss without Agent submission.
7. Use recovery WAV upload only when the local protocol reports a recoverable interruption requiring it.
8. Test hold/release, stale events, duplicate finals, silence, and resource cleanup.

**Verification:** From `client`, run `npm.cmd test -- --run src/voice/voiceState.test.ts` and `npm.cmd run build`; expect all realtime hold tests and build to pass.

## T15: Add Local VAD And Continuous Turn Detection

**Files:** `client/src/voice/turnDetector.ts`, `client/src/voice/useVoiceAgent.ts`, `client/src/voice/voiceState.test.ts`

**Dependencies:** T11, T14

**Steps:**

1. Initialize the pinned local Silero VAD from packaged model/worklet/WASM assets.
2. Maintain a pre-speech ring buffer and feed detected speech frames into the same realtime stream protocol.
3. Map speech start to playback interruption and stream start.
4. Map configurable sustained silence to one stream finish.
5. Resume listening after completion or recoverable recognition failure until explicitly stopped.
6. Pause continuous capture safely while a pending input slot is full.
7. Destroy VAD, microphone tracks, audio contexts, worklets, buffers, and callbacks on stop/disconnect/unmount.
8. Test speech start/end, VAD misfire, playback barge-in, restart, and cleanup with a fake VAD adapter.

**Verification:** From `client`, run `npm.cmd test -- --run src/voice/voiceState.test.ts` and expect all continuous-mode tests to pass.

## T16: Add Grouped Playback And Barge-In

**Files:** `client/src/voice/playback.ts`, `client/src/voice/useVoiceAgent.ts`, `client/src/voice/playback.test.ts`

**Dependencies:** T10, T13

**Steps:**

1. Group incoming status/final audio by request and playback group.
2. Preserve segment order and begin playing the first segment before later segments arrive.
3. Give current final speech precedence over stale status speech.
4. On microphone speech start or stop-playback, pause audio, revoke every group URL, clear queues, and notify the Harness to cancel remaining synthesis.
5. Never send Agent cancellation or permission responses from playback interruption.
6. Test progressive arrival, stale status suppression, interruption, error, and URL cleanup.

**Verification:** From `client`, run `npm.cmd test -- --run src/voice/playback.test.ts` and expect all playback tests to pass.

## T17: Implement Realtime Voice UI And Profile Settings

**Files:** `client/src/App.tsx`, `client/src/styles.css`, `client/src/types.ts`

**Dependencies:** T2, T14, T15, T16

**Steps:**

1. Change the microphone control to press-and-hold behavior with stable pointer/keyboard interactions and tooltips.
2. Display live partial captions and listening, transcribing, fallback, queued, analyzing, executing, waiting-approval, speaking, interrupted, and error states compactly.
3. Add an explicit continuous-conversation toggle and stop control.
4. Add provider profile create/edit/remove controls plus primary, ordered fallback, and TTS profile selection.
5. Separate ASR enabled, TTS enabled, status announcements, and continuous-mode settings.
6. Disable/hide TTS model and voice fields when TTS is off and allow ASR-only save.
7. Keep credentials write-only and preserve configured placeholders without echoing values.
8. Ensure typed chat, workspace behavior, composer sizing, and existing compact UI remain unchanged when voice is off.

**Verification:** From `client`, run `npm.cmd test -- --run` and `npm.cmd run build`; expect all client tests and the production build to pass.

## T18: Extend Desktop Diagnostics And Asset Checks

**Files:** `desktop/src/main.cjs`, `desktop/scripts/build-client.cjs`

**Dependencies:** T11, T17

**Steps:**

1. Preserve the trusted audio-only microphone permission policy.
2. Include redacted profile IDs, providers, readiness, phase, fallback count, and classified error kind in diagnostics.
3. Exclude credentials, transcript text, audio, signed URLs, and synthesis payloads.
4. Verify packaged client VAD assets exist before launching/packaging.
5. Keep renderer context isolation and current menu/IPC boundaries unchanged.

**Verification:** From `desktop`, run `node --check src/main.cjs`, `node --check src/preload.cjs`, and `npm.cmd run build:client`; expect syntax checks and the asset-aware client build to pass.

## T19: Run Focused And Full Automated Verification

**Files:** All backend/client files above, `specs/realtime-voice/checklist.md`

**Dependencies:** T1 through T18

**Steps:**

1. Run all focused backend voice tests and fix failures.
2. Run the full backend test suite and separately verify any managed-sandbox filesystem tests if required.
3. Run all client voice tests and the production build.
4. Run Electron main/preload syntax checks.
5. Run `git diff --check` and inspect tracked/untracked files for credentials or generated local configuration.
6. Record commands and actual pass counts in the acceptance checklist.

**Verification:** Expect focused voice tests, full `uv run pytest`, client `npm.cmd test -- --run`, client build, Electron syntax checks, and `git diff --check` to pass.

## T20: Build And Smoke-Test The Windows Package

**Files:** Desktop/package output and `specs/realtime-voice/checklist.md`

**Dependencies:** T19

**Steps:**

1. Rebuild the PyInstaller backend with the new streaming modules and dependencies.
2. Build the Electron Windows directory package and installer.
3. Verify VAD model/worklet/WASM and bundled backend files exist in package resources.
4. Launch the packaged `OctoCoder.exe` without a terminal and verify it remains running through the smoke interval.
5. Exercise mocked or live press-and-hold, fallback, optional TTS, and continuous-mode flows where credentials and microphone access permit.
6. Record provider-dependent checks honestly as passed, failed, or requiring user acceptance.

**Verification:** From `desktop`, run `npm.cmd run package` and `npm.cmd run make`; expect package/installer generation and the packaged-process smoke test to succeed.

## Execution Order

```text
T1 -> T2
 |     |
 v     v
T3 -> T5 ----\
 |     |      \
 v     v       -> T7 -> T8 -> T9 -> T10
T4 -> T6 ----/                    |
                                      v
T11 -> T12 -> T13 -> T14 -> T15 -> T16 -> T17 -> T18
                                      ^
                                      |
                              backend T10 contract

T1-T18 -> T19 -> T20
```
