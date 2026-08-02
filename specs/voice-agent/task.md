# OctoCoder Voice Agent MVP Tasks

## File List

| Action | File | Responsibility |
| --- | --- | --- |
| Modify | `herness/octocoder/config.py` | Add optional voice configuration to the application model and merge flow. |
| Modify | `herness/octocoder/validator.py` | Validate and normalize the optional voice section. |
| Modify | `herness/octocoder/remote.py` | Save/redact voice settings, receive binary recordings, run STT, bridge Agent execution, and return TTS audio. |
| Create | `herness/octocoder/voice/__init__.py` | Export the public voice-domain interfaces. |
| Create | `herness/octocoder/voice/models.py` | Define upload and synthesized-audio data structures and limits. |
| Create | `herness/octocoder/voice/provider.py` | Define the provider protocol and normalized errors. |
| Create | `herness/octocoder/voice/openai_compatible.py` | Implement OpenAI-compatible STT and TTS HTTP calls. |
| Create | `herness/octocoder/voice/text.py` | Extract and segment final speakable response text. |
| Create | `herness/tests/test_voice_config.py` | Cover configuration defaults, validation, merging, saving, and secret redaction. |
| Create | `herness/tests/test_voice_provider.py` | Cover HTTP request/response behavior with mocked transport. |
| Create | `herness/tests/test_voice_text.py` | Cover markdown filtering and sentence-aware segmentation. |
| Create | `herness/tests/test_voice_remote.py` | Cover upload state, limits, transcription, automatic submission, and TTS routing. |
| Modify | `client/src/types.ts` | Add voice settings, state, and WebSocket message types. |
| Modify | `client/src/socket.ts` | Send binary recordings and pair incoming binary audio with metadata. |
| Create | `client/src/voice/recorder.ts` | Own microphone capture, MIME selection, limits, and resource cleanup. |
| Create | `client/src/voice/playback.ts` | Own ordered synthesized-audio playback and cleanup. |
| Create | `client/src/voice/useVoiceAgent.ts` | Coordinate renderer voice state and socket events. |
| Modify | `client/src/App.tsx` | Integrate voice state, composer controls, transcript handling, settings, and diagnostics. |
| Modify | `client/src/styles.css` | Style compact microphone/status/settings controls without layout shift. |
| Modify | `desktop/src/main.cjs` | Add trusted microphone permissions and voice-safe diagnostics fields. |

## T1: Add Voice Configuration Contract

**Files:** `herness/octocoder/config.py`, `herness/octocoder/validator.py`, `herness/tests/test_voice_config.py`

**Dependencies:** None

**Steps:**

1. Add `VoiceConfig` with disabled defaults, API-key environment fallback, and a computed configured state.
2. Extend `AppConfig` and layered configuration merging with the optional `voice` section.
3. Validate booleans, strings, defaults, and required fields when voice is enabled.
4. Extend remote configuration save/status behavior so the key is preserved when omitted and never returned to the client.
5. Add tests for old configs without voice, enabled/disabled configurations, invalid enabled settings, environment fallback, merge behavior, and redacted status.

**Verification:** Run `uv run pytest tests/test_voice_config.py` from `herness` and expect all tests to pass.

## T2: Implement Voice Provider Adapter

**Files:** `herness/octocoder/voice/__init__.py`, `herness/octocoder/voice/models.py`, `herness/octocoder/voice/provider.py`, `herness/octocoder/voice/openai_compatible.py`, `herness/tests/test_voice_provider.py`

**Dependencies:** T1

**Steps:**

1. Define the provider protocol, `VoiceAudio`, recording constants, and sanitized provider exception.
2. Implement URL joining and bearer authorization without logging API keys.
3. Implement multipart transcription with model, file, response format, and optional language.
4. Implement MP3 speech generation with model, voice, and text.
5. Apply explicit connect/read timeouts and normalize non-success, malformed JSON, empty transcription, and non-audio speech responses.
6. Test request paths, headers, form/JSON fields, successful responses, and provider failure cases using `httpx.MockTransport` or an injected async client.

**Verification:** Run `uv run pytest tests/test_voice_provider.py` from `herness` and expect all tests to pass without network access.

## T3: Implement Speakable Text Processing

**Files:** `herness/octocoder/voice/text.py`, `herness/tests/test_voice_text.py`

**Dependencies:** T2

**Steps:**

1. Remove fenced source-code blocks and empty output.
2. Normalize inline markdown, links, raw URLs, headings, lists, and whitespace into natural prose.
3. Split long prose at paragraph and sentence boundaries with a hard maximum of 3500 characters per segment.
4. Cover Chinese and English punctuation, code-only replies, long unbroken text, and multi-segment replies.

**Verification:** Run `uv run pytest tests/test_voice_text.py` from `herness` and expect all tests to pass.

## T4: Add Recording Upload And Transcription Protocol

**Files:** `herness/octocoder/remote.py`, `herness/tests/test_voice_remote.py`

**Dependencies:** T1, T2

**Steps:**

1. Track one `VoiceUpload` and related background task per WebSocket connection.
2. Branch on binary WebSocket messages before JSON decoding.
3. Handle start, one binary payload, stop, cancel, disconnect cleanup, duplicate operations, and stale request IDs.
4. Enforce the 120-second and 16 MiB limits on both control and binary paths.
5. Call STT asynchronously and send `voice_status`, `voice_transcript`, or `voice_error` only to the initiating connection.
6. In manual mode, return an editable unsubmitted transcript; in automatic mode, mark it submitted and invoke the normal user-message handler exactly once.
7. Test state transitions, invalid ordering, size/duration boundaries, manual transcription, automatic submission, provider failures, and disconnect cleanup with fake sockets/providers.

**Verification:** Run `uv run pytest tests/test_voice_remote.py -k "upload or transcrib or auto_submit"` from `herness` and expect all selected tests to pass.

## T5: Add Voice-Origin Agent And TTS Bridge

**Files:** `herness/octocoder/remote.py`, `herness/tests/test_voice_remote.py`

**Dependencies:** T3, T4

**Steps:**

1. Accept optional `source` and `voiceRequestId` metadata on `user_message` without changing typed-message behavior.
2. Track per-turn streamed text and whether each turn used tools.
3. Select only the latest successful non-tool final turn after loop completion.
4. Skip TTS for typed tasks, cancelled runs, errors, empty prose, thinking, tool events, permission prompts, and code-only output.
5. Extract and split speakable text, synthesize segments sequentially, and send each as metadata followed by one binary frame to the initiating connection only.
6. Report recoverable TTS failures without changing the completed text task or conversation.
7. Test voice-versus-text routing, final-turn selection, filtered content, multiple audio segments, cancellation, and TTS failure behavior.

**Verification:** Run `uv run pytest tests/test_voice_remote.py` from `herness` and expect all tests to pass.

## T6: Extend Frontend Socket And Type Contracts

**Files:** `client/src/types.ts`, `client/src/socket.ts`

**Dependencies:** T4, T5

**Steps:**

1. Add redacted voice settings, save payload, phase, and protocol union types.
2. Set the WebSocket binary type to `arraybuffer`.
3. Add a binary send method that reports whether the socket accepted the payload.
4. Pair every `voice_audio_start` message with the immediately following binary frame and expose a typed audio callback.
5. Clear pending binary metadata on reconnect/close and ignore unsolicited binary frames safely.

**Verification:** Run `npm.cmd run build` from `client` and expect TypeScript and Vite production build to succeed.

## T7: Implement Renderer Recording And Playback Controllers

**Files:** `client/src/voice/recorder.ts`, `client/src/voice/playback.ts`, `client/src/voice/useVoiceAgent.ts`

**Dependencies:** T6

**Steps:**

1. Implement supported MIME selection and audio-only `getUserMedia` recording.
2. Collect encoded chunks, stop at 120 seconds, reject payloads over 16 MiB, and release all media tracks and timers on every terminal path.
3. Send start metadata, one binary frame, and stop metadata in WebSocket order.
4. Implement the voice state machine with request-ID checks so stale server events cannot mutate the active session.
5. Implement an ordered audio queue using object URLs and `HTMLAudioElement`.
6. Ensure starting a recording stops playback, while stopping playback never sends Agent cancellation.
7. Dispose recorder/playback resources on React unmount and socket disconnect.

**Verification:** Run `npm.cmd run build` from `client` and expect no TypeScript errors, including strict lifecycle and browser API types.

## T8: Integrate Composer And Settings UI

**Files:** `client/src/App.tsx`, `client/src/styles.css`

**Dependencies:** T1, T6, T7

**Steps:**

1. Connect server voice messages and binary audio callbacks to the voice hook.
2. Add a stable icon microphone control, elapsed recording status, transcribing status, speaking/stop control, tooltips, and accessible labels.
3. Fill the composer with manual transcripts and preserve voice-origin metadata when the reviewed text is submitted.
4. Reflect automatic submissions in the conversation exactly once without duplicating user messages.
5. Add a separate voice settings section with enabled state, Base URL, write-only API Key, STT model, TTS model, voice, language, and automatic submission.
6. Disable voice execution when unconfigured while keeping typed submission available.
7. Render provider and microphone failures as recoverable notices and include sanitized voice state in diagnostics input.
8. Keep the compact composer and settings layout stable across current desktop widths.

**Verification:** Run `npm.cmd run build` from `client` and expect the production build to pass; inspect the built UI in Electron and verify controls do not shift the composer layout.

## T9: Add Electron Microphone Permission Policy

**Files:** `desktop/src/main.cjs`

**Dependencies:** T7, T8

**Steps:**

1. Define trusted packaged and local-development renderer origins.
2. Install both permission-check and permission-request handlers on the window session.
3. Permit audio microphone access only for the trusted main renderer and reject video or unrelated origins.
4. Preserve operating-system microphone permission behavior and existing context isolation.
5. Extend exported diagnostics with redacted voice capability/state only; exclude API keys, transcripts, and audio data.

**Verification:** Run `node --check src/main.cjs` and `node --check src/preload.cjs` from `desktop` and expect both commands to exit successfully.

## T10: Run Full Integration And Package Verification

**Files:** All files listed above

**Dependencies:** T1 through T9

**Steps:**

1. Run all backend tests and fix regressions outside the focused voice tests.
2. Build the production React client.
3. Run Electron main/preload syntax checks.
4. Build the bundled Python backend and local desktop package.
5. Launch the packaged Windows application and verify it remains running.
6. With valid configured speech credentials, manually verify denied permission, manual transcript review, automatic submission, current-project execution, explicit tool permission, final-response playback, and stop-playback behavior.
7. Verify diagnostics contain voice status but no API key, transcript, or audio payload.
8. Record any provider-dependent check that cannot run without valid voice credentials as requiring user-side acceptance rather than reporting it as passed.

**Verification:** Run `uv run pytest` from `herness`, `npm.cmd run build` from `client`, `node --check src/main.cjs` and `node --check src/preload.cjs` from `desktop`, then `npm.cmd run package` from `desktop`. Expect automated checks and packaging to complete, and the packaged `OctoCoder.exe` to remain running during the launch smoke test.

## T11: Add Selectable Voice Providers

**Files:** `herness/octocoder/validator.py`, `herness/octocoder/config.py`, `herness/octocoder/voice/factory.py`, `herness/octocoder/voice/siliconflow.py`, `herness/octocoder/voice/aliyun.py`, `herness/octocoder/remote.py`, `client/src/types.ts`, `client/src/App.tsx`, `desktop/src/main.cjs`, `herness/tests/test_voice_config.py`, `herness/tests/test_voice_provider.py`

1. Add stable provider identifiers and documented defaults for SiliconFlow, Alibaba Cloud Model Studio, OpenAI, and custom OpenAI-compatible services.
2. Add a provider factory and dedicated SiliconFlow and Alibaba adapters while retaining the shared provider protocol.
3. Validate provider identifiers before saving and preserve compatibility for existing configurations without an identifier.
4. Add a settings selector that applies editable defaults and persists the selected provider.
5. Keep API keys write-only in status and diagnostics.
6. Cover factory selection, provider-specific request shapes, signed audio download, preset validation, status output, and rejected invalid saves with mocked tests.

**Verification:** Run the focused backend voice suite and the React production build; expect `41 passed` and a successful Vite build without live provider credentials.

## T12: Add Volcengine Doubao Voice Provider

**Files:** `herness/octocoder/validator.py`, `herness/octocoder/config.py`, `herness/octocoder/voice/volcengine.py`, `herness/octocoder/voice/factory.py`, `herness/octocoder/remote.py`, `client/src/types.ts`, `client/src/App.tsx`, `client/src/voice/recorder.ts`, `client/src/voice/useVoiceAgent.ts`, `desktop/src/main.cjs`, `herness/tests/test_voice_config.py`, `herness/tests/test_voice_provider.py`

1. Add Volcengine defaults and write-only App ID, Access Token, and optional Secret Key configuration.
2. Implement flash ASR request headers/body, response status validation, and transcript extraction.
3. Implement Bearer Token non-streaming TTS and Base64 MP3 decoding.
4. Generate 16 kHz mono PCM WAV in the renderer for documented ASR format compatibility.
5. Add provider selection fields, redacted status/diagnostics, and credential-preserving saves.
6. Cover provider selection, request contracts, configuration requirements, credential redaction, and preservation with fake credentials.

**Verification:** Run the focused voice backend suite and client production build; expect `47 passed` and successful TypeScript/Vite output without using live credentials.

## Execution Order

```text
T1 -> T2 -> T3
          \-> T4 -> T5 -> T6 -> T7 -> T8 -> T9 -> T10 -> T11 -> T12
T1 --------------------------/
```
