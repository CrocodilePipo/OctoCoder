# OctoCoder Realtime Voice Plan

## Architecture Overview

The realtime voice upgrade remains an OctoCoder-native pipeline. The Electron renderer captures mono PCM audio and sends bounded frames through the existing local WebSocket. The Python Harness owns all cloud credentials, opens the Alibaba Cloud Model Studio streaming WebSocket, normalizes partial/final transcripts, applies fallback policy, and submits one final transcript through the existing Agent path.

Press-and-hold and continuous conversation share the same backend stream protocol but use different local turn owners:

```text
Press-and-hold
  pointer down -> open local capture and backend stream
  audio frames -> Alibaba streaming ASR -> partial captions
  pointer up -> finish stream -> final transcript -> Agent

Continuous conversation
  enable session -> local Silero VAD listens
  speech start -> stop TTS, open backend stream, flush pre-roll
  speech frames -> Alibaba streaming ASR -> partial captions
  sustained silence -> finish stream -> final transcript -> Agent or one pending slot
```

The cloud streaming connection is never exposed to the renderer. The renderer-to-Harness WebSocket remains the only application transport, so API keys stay in the backend and the existing Electron permission policy remains authoritative.

```text
Renderer microphone
  -> PCM worklet / local VAD
  -> OctoCoder WebSocket stream protocol
  -> RealtimeVoiceCoordinator
     -> AliyunStreamingASRSession
     -> batch fallback coordinator
     -> exactly-once transcript gate
  -> existing RemoteServer._handle_user_message
  -> Agent events
     -> voice task-state mapper
     -> optional TTS scheduler
  -> renderer captions / status / progressive playback
```

## Core Data Structures

### VoiceProviderProfile

One independently configured speech-provider account and capability set.

```python
@dataclass
class VoiceProviderProfile:
    id: str
    name: str
    provider: str
    base_url: str
    streaming_url: str
    workspace_id: str
    api_key: str
    app_id: str
    secret_key: str
    batch_stt_model: str
    streaming_stt_model: str
    tts_model: str
    voice: str
    language: str

    def resolve_api_key(self) -> str: ...
    @property
    def batch_asr_configured(self) -> bool: ...
    @property
    def streaming_asr_configured(self) -> bool: ...
    @property
    def tts_configured(self) -> bool: ...
```

Secrets are write-only. `streaming_url` is editable so workspace-specific Beijing/Singapore endpoints can be used. The default Aliyun streaming URL remains the supported shared DashScope endpoint; `workspace_id`, when present, is sent in the documented header.

### VoiceConfig

```python
@dataclass
class VoiceConfig:
    enabled: bool = False
    mode: str = "hold"
    primary_asr_profile: str = "default"
    fallback_asr_profiles: list[str] = field(default_factory=list)
    tts_enabled: bool = False
    tts_profile: str = ""
    status_announcements: bool = False
    continuous_silence_ms: int = 900
    profiles: list[VoiceProviderProfile] = field(default_factory=list)

    @property
    def configured(self) -> bool: ...
    @property
    def streaming_configured(self) -> bool: ...
    @property
    def tts_configured(self) -> bool: ...
```

`configured` means ASR-ready only. TTS readiness is independent. A legacy single-provider `voice` mapping is normalized into a `default` profile in memory and is migrated to the profile schema on the next settings save while preserving credentials.

### VoiceProviderError

```python
class VoiceErrorKind(str, Enum):
    TRANSPORT = "transport"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER = "server"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_RESPONSE = "invalid_response"

class VoiceProviderError(RuntimeError):
    kind: VoiceErrorKind
    retryable: bool
    provider: str
    status_code: int | None
```

All provider adapters map failures to this structure. Only transport, timeout, rate-limit, interrupted-response, and server failures are retryable.

### TranscriptionEvent

```python
@dataclass(frozen=True)
class TranscriptionEvent:
    type: Literal["partial", "final", "finished"]
    text: str = ""
    sentence_id: int = 0
    revision: int = 0
```

Partial events replace the current sentence revision instead of appending blindly. Final sentence text is accumulated by sentence ID, preventing repeated provider events from duplicating captions.

### StreamingASRSession

```python
class StreamingASRSession(Protocol):
    async def start(self) -> None: ...
    async def send_audio(self, pcm16: bytes) -> None: ...
    async def finish(self) -> str: ...
    async def cancel(self) -> None: ...
    def events(self) -> AsyncIterator[TranscriptionEvent]: ...
```

### Speech Provider Boundaries

```python
class BatchASRProvider(Protocol):
    async def transcribe(self, audio: bytes, *, filename: str,
                         content_type: str, language: str = "") -> str: ...

class StreamingASRProvider(Protocol):
    async def create_session(self, request_id: str) -> StreamingASRSession: ...

class TTSProvider(Protocol):
    async def synthesize(self, text: str) -> VoiceAudio: ...
```

Existing provider classes continue implementing batch ASR/TTS. Separate factories select only the capability requested, so ASR configuration does not construct or validate TTS.

### RealtimeVoiceSession

Per renderer connection and utterance, owned by the Harness.

```python
@dataclass
class RealtimeVoiceSession:
    request_id: str
    mode: Literal["hold", "continuous"]
    profile_id: str
    started_at: float
    phase: VoicePhase
    sequence: int = 0
    pcm: bytearray = field(default_factory=bytearray)
    input_queue: asyncio.Queue[bytes]
    upstream: StreamingASRSession | None = None
    finalized: bool = False
    submitted: bool = False
    fallback_started: bool = False
    worker_tasks: set[asyncio.Task]
```

The input queue and PCM buffer are bounded by the existing recording limits. `finalized` and `submitted` are monotonic gates protected by the session lock.

### VoiceTaskState

```typescript
type VoicePhase =
  | "idle"
  | "requesting_permission"
  | "connecting"
  | "listening"
  | "transcribing"
  | "falling_back"
  | "queued"
  | "analyzing"
  | "executing"
  | "waiting_approval"
  | "speaking"
  | "interrupted"
  | "error";
```

The backend is authoritative for provider and Agent phases. The client is authoritative for microphone permission, capture, local VAD, playback, and interrupted state.

### BufferedUtterance

```typescript
type BufferedUtterance = {
  requestId: string;
  mode: "hold" | "continuous";
  sequence: number;
  pcmChunks: Int16Array[];
  byteLength: number;
  startedAt: number;
};
```

The client retains this only until a terminal transcript/error acknowledgement. It can produce a PCM WAV recovery upload after a recoverable local connection interruption. The Harness also accumulates the received PCM for immediate provider fallback.

### PendingVoiceInput

```python
@dataclass
class PendingVoiceInput:
    request_id: str
    transcript: str
    requester: ServerConnection
```

Only continuous mode may occupy the one pending slot while the Agent is busy. A newer utterance is rejected visibly rather than replacing the pending input silently.

## WebSocket Protocol

Client control messages:

```typescript
{ type: "voice_stream_start"; data: {
    requestId: string;
    mode: "hold" | "continuous";
    format: "pcm_s16le";
    sampleRate: 16000;
    channels: 1;
  } }
{ type: "voice_stream_chunk"; data: {
    requestId: string;
    sequence: number;
    byteLength: number;
  } }
// The next client binary WebSocket message is the declared PCM chunk.
{ type: "voice_stream_finish"; data: { requestId: string; finalSequence: number } }
{ type: "voice_stream_cancel"; data: { requestId: string } }
{ type: "voice_recovery_upload"; data: {
    requestId: string;
    mimeType: "audio/wav";
    byteLength: number;
  } }
// The next client binary WebSocket message is the recovery WAV.
{ type: "voice_playback_interrupt"; data: { requestId: string; groupId: string } }
```

Server messages:

```typescript
{ type: "voice_stream_ready"; data: { requestId: string; provider: string } }
{ type: "voice_transcript_partial"; data: {
    requestId: string;
    text: string;
    revision: number;
  } }
{ type: "voice_transcript"; data: {
    requestId: string;
    text: string;
    submitted: boolean;
    provider: string;
    fallbackUsed: boolean;
  } }
{ type: "voice_status"; data: {
    requestId: string;
    phase: VoicePhase;
    provider?: string;
    message?: string;
  } }
{ type: "voice_audio_start"; data: {
    requestId: string;
    groupId: string;
    purpose: "status" | "final";
    audioId: string;
    mimeType: string;
    index: number;
    total: number;
  } }
```

Legacy `voice_record_*` messages remain accepted for batch-only profiles and compatibility. Client and server reject mismatched request IDs, non-monotonic chunk sequences, incorrect binary lengths, duplicate finishes, and binary messages without pending metadata.

## Module Design

### Configuration And Migration

**Responsibility:** Normalize legacy voice settings, validate provider profiles and capability selections, save multiple write-only credentials, and expose redacted readiness.

**Public Interface:** `VoiceConfig`, `VoiceProviderProfile`, configuration save/status payloads, and provider capability presets.

**Dependencies:** Existing YAML configuration loader, validator, remote settings handlers, and diagnostics exporter.

Validation ensures unique profile IDs, valid references, one configured primary ASR profile, valid ordered fallback references, and a TTS-capable profile only when TTS is enabled. Missing TTS fields never block ASR. Environment fallback remains supported for the migrated default profile.

### Aliyun Streaming ASR Adapter

**Responsibility:** Implement the current Alibaba Cloud Model Studio duplex WebSocket protocol without the DashScope SDK.

**Public Interface:** `AliyunStreamingASRProvider.create_session()`.

**Dependencies:** Existing `websockets>=14`, `VoiceProviderProfile`, and injectable WebSocket connector for tests.

The adapter:

1. Opens the configured `wss://` endpoint with `Authorization: Bearer <key>`, optional workspace header, open timeout, ping interval, and ping timeout.
2. Sends `run-task` with a UUID task ID, `streaming=duplex`, model `qwen-audio-3.0-asr-flash-streaming` by default, mono PCM at 16 kHz, language hints, and heartbeat enabled.
3. Waits for `task-started` before accepting upstream audio.
4. Sends binary PCM frames while a receiver task parses `result-generated` events.
5. Ignores provider heartbeat sentences, replaces partial sentence revisions, and freezes `sentence_end=true` text by sentence ID.
6. Sends `finish-task`, continues reading final results, waits for `task-finished`, and returns the accumulated transcript.
7. Maps handshake status, `task-failed`, timeout, close, malformed event, and incomplete message errors to classified provider errors.

The official shared endpoint remains usable; users may configure the recommended workspace-specific Beijing or Singapore endpoint.

### Streaming Session And Fallback Coordinator

**Responsibility:** Own client chunk ordering, upstream producer/consumer tasks, transcript delivery, retry classification, batch fallback, and exactly-once Agent submission.

**Public Interface:** Internal handlers called by `RemoteServer` for stream start/chunk/binary/finish/cancel/recovery.

**Dependencies:** Streaming/batch provider factories, WAV encoder, existing per-connection task tracking, and Agent message handler.

The local WebSocket receive loop never awaits a cloud send. It validates metadata and puts PCM into a bounded queue. A worker forwards frames upstream; a reader emits rate-limited partial captions. On release, the coordinator drains the queue before calling upstream `finish()`.

For retryable streaming failure, candidate order is:

```text
primary profile batch ASR capability
  -> explicitly ordered fallback profile 1
  -> explicitly ordered fallback profile 2 ...
```

Duplicate profile/capability combinations are skipped. Non-retryable failures stop immediately. The final transcript passes through one atomic submission gate; late upstream events are ignored after fallback begins.

### PCM Capture And Local Buffer

**Responsibility:** Capture one microphone stream, resample to 16 kHz mono PCM16, emit bounded frames, retain one utterance, and produce a fallback WAV.

**Public Interface:** `RealtimePcmCapture.start()`, `finish()`, `cancel()`, `dispose()`, and frame callbacks.

**Dependencies:** `getUserMedia`, `AudioContext`, `AudioWorklet`, existing socket wrapper, and Electron microphone permissions.

An AudioWorklet replaces the deprecated realtime `ScriptProcessorNode` path. Frames are accumulated into approximately 100 ms chunks before sending, matching Alibaba guidance. The sender checks `WebSocket.bufferedAmount`, keeps a bounded local queue, and fails recoverably instead of growing memory indefinitely.

The existing `VoiceRecorder` remains for non-streaming batch-only operation and fallback compatibility.

### Local VAD And Turn Detection

**Responsibility:** Start and end continuous-mode utterances from local speech probability while sharing the same microphone lifecycle.

**Public Interface:** `LocalTurnDetector.start()`, `pause()`, `resume()`, and `dispose()` plus speech-start/frame/speech-end callbacks.

**Dependencies:** `@ricky0123/vad-web`, ONNX Runtime Web, locally packaged Silero VAD model/worklet/WASM assets, and the realtime voice controller.

No CDN asset is used. Build scripts copy pinned VAD assets into the Vite output. A pre-speech ring buffer prevents clipping initial consonants. Configurable silence is mapped to the VAD redemption window, while minimum speech duration filters clicks and short noise. `onSpeechStart` interrupts playback and opens a stream; frame callbacks feed PCM; `onSpeechEnd` finishes the turn.

### Renderer Voice Controller

**Responsibility:** Coordinate press-and-hold pointer lifecycle, partial captions, continuous mode, recovery upload, one pending utterance presentation, and resource cleanup.

**Public Interface:** The existing `useVoiceAgent()` hook extended with `startHold()`, `finishHold()`, `cancelHold()`, `startContinuous()`, `stopContinuous()`, and playback interruption.

**Dependencies:** PCM capture, local turn detector, playback scheduler, WebSocket protocol, React state, and settings.

Pointer capture ensures release outside the microphone button still finishes the utterance. Keyboard users receive equivalent Space/Enter press-and-release behavior when the microphone control is focused. Partial captions are throttled to at most ten UI updates per second and are kept visually separate from editable composer text until finalized.

### Agent Voice State Mapper

**Responsibility:** Convert existing Agent events into high-level voice task states.

**Public Interface:** Internal state transitions tied to a voice request ID and initiating connection.

**Dependencies:** Existing `StreamText`, `ThinkingText`, `ToolUseEvent`, `PermissionRequest`, `TurnComplete`, `LoopComplete`, cancellation, and permission response flow.

Transitions are:

```text
transcript submitted -> analyzing
first tool use -> executing
permission request -> waiting_approval
permission response -> executing
loop complete -> speaking when TTS is enabled, otherwise idle
error/cancel -> error or interrupted -> idle
```

Only state changes are emitted; repeated tool events do not repeat announcements.

### TTS Scheduler And Progressive Playback

**Responsibility:** Keep TTS optional, synthesize high-level status phrases, progressively send final response segments, and cancel stale speech groups.

**Public Interface:** Backend `VoiceSpeechScheduler` and renderer `VoicePlaybackQueue` grouped by request/purpose.

**Dependencies:** TTS provider factory, speakable-text filtering, WebSocket binary audio transport, and playback interruption protocol.

When TTS is disabled or unconfigured, no synthesis provider is created or called. Status announcements use fixed localized phrases and are cached in memory by provider/model/voice/language. Final prose is split into short sentence groups; each completed segment is sent immediately in order instead of waiting for all segments. A playback group token lets user speech or the stop button discard queued audio and cancel unsent synthesis without affecting the Agent.

### Pending Continuous Input

**Responsibility:** Prevent overlapping Agent turns while continuous listening remains active.

**Public Interface:** One pending slot per active renderer connection.

**Dependencies:** Agent busy state, realtime transcript finalization, and voice status messages.

A continuous transcript finalized while the Agent is running enters the pending slot and receives `queued` status. After the active turn exits, it is submitted once. A second transcript while the slot is occupied is rejected visibly. Press-and-hold is disabled while the Agent is busy.

### Diagnostics And Security

**Responsibility:** Report capabilities and sanitized phase/failure information without audio, transcripts, or credentials.

**Public Interface:** Existing settings status and diagnostics export.

Diagnostics include selected profile IDs, provider IDs, ASR/TTS readiness, continuous-mode availability, current phase, fallback count, and last classified error kind. They exclude URLs containing query secrets, API keys, App IDs where treated as credentials, audio buffers, transcript text, and synthesized audio.

## Module Interactions

1. Settings load normalizes either the legacy single-provider schema or the new profile schema and returns redacted capability status.
2. Pressing the microphone stops playback, requests microphone access, starts PCM capture, creates a request ID, and asks the Harness to open a streaming session.
3. The Harness opens Alibaba streaming ASR and sends `voice_stream_ready` only after `task-started`.
4. The client flushes its bounded pre-ready audio queue, then sends ordered metadata/binary PCM pairs while showing partial transcript revisions.
5. Releasing drains local audio and sends `voice_stream_finish`; the Harness drains its queue, sends `finish-task`, and waits for the provider's final events.
6. A retryable streaming failure moves the state to `falling_back` and runs batch candidates against the buffered PCM WAV. A non-retryable failure is shown directly.
7. The transcript gate publishes one final transcript and submits it once through the existing Agent path, or places it into the one continuous pending slot when busy.
8. Agent events drive analyzing, executing, and waiting-approval states. Existing UI approval controls remain the only permission-response path.
9. When enabled, the TTS scheduler produces one announcement per high-level transition and progressively sends filtered final-response segments.
10. New speech stops the current playback group immediately and informs the Harness to cancel remaining synthesis. The coding task continues.
11. Continuous mode restarts listening after task completion or recoverable voice failure until explicitly stopped.
12. Every terminal path closes upstream WebSockets, cancels workers, stops microphone tracks/worklets/VAD, clears in-memory audio, and releases playback URLs.

## File Organization

```text
OctoCoder/
  herness/
    octocoder/
      config.py                          - profile-based ASR/TTS configuration and migration
      validator.py                       - capability-aware validation and defaults
      remote.py                          - protocol dispatch and Agent status integration
      voice/
        provider.py                      - classified errors and split provider protocols
        factory.py                       - batch ASR, streaming ASR, and TTS factories
        audio.py                         - PCM validation and WAV encoding
        session.py                       - realtime session and exactly-once coordinator
        fallback.py                      - retry classification and ordered batch fallback
        aliyun_streaming.py              - Alibaba duplex WebSocket ASR adapter
        speech.py                        - status/final TTS scheduler and cancellation groups
    tests/
      test_voice_config.py               - migration, profiles, ASR-only, redaction
      test_voice_provider.py             - classified existing provider failures
      test_voice_streaming_provider.py   - Alibaba protocol/event contract
      test_voice_streaming_remote.py     - chunks, fallback, deduplication, pending input
      test_voice_remote.py               - optional TTS and Agent phase integration
  client/
    package.json                         - pinned local VAD dependencies and test scripts
    package-lock.json                    - dependency lock update
    scripts/
      copy-voice-assets.mjs              - copy VAD model/worklet/WASM into build output
    public/
      voice/
        pcm-worklet.js                   - PCM capture/resampling worklet
    src/
      types.ts                           - profile, phase, and protocol contracts
      socket.ts                          - ordered binary metadata and backpressure status
      App.tsx                            - settings, partial caption, controls, status
      styles.css                         - compact realtime/continuous voice states
      voice/
        pcm.ts                           - PCM/WAV conversion and bounded utterance buffer
        realtimeCapture.ts               - AudioWorklet microphone lifecycle
        turnDetector.ts                  - local Silero VAD lifecycle
        playback.ts                      - grouped priority playback and interruption
        useVoiceAgent.ts                 - complete renderer voice state machine
      voice/*.test.ts                    - state, PCM, turn, playback, and protocol tests
  desktop/
    scripts/
      build-client.cjs                   - include locally built voice assets
    src/
      main.cjs                           - preserve trusted microphone permission policy
```

## Technical Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| First streaming provider | Alibaba Cloud Model Studio | Explicit user choice and domestic availability. |
| Default streaming model | `qwen-audio-3.0-asr-flash-streaming` | Current Alibaba documentation recommends it for realtime multilingual/dialect recognition. |
| Provider transport | Direct `websockets` protocol in Harness | Keeps credentials outside the renderer and avoids adding the DashScope SDK. |
| Cloud interaction mode | Explicit `finish-task` for press-and-hold | Release is the user-owned turn boundary and maps directly to the documented duplex protocol. |
| Audio format | 16 kHz mono signed PCM16, about 100 ms per frame | Supported by Alibaba and efficient over the local WebSocket. |
| Local capture | AudioWorklet | Realtime-safe browser API and replacement for deprecated ScriptProcessor-based streaming. |
| Local VAD | Pinned `@ricky0123/vad-web` with Silero VAD v5 | Proven browser VAD with speech/frame callbacks; avoids hand-rolled speech detection. |
| VAD assets | Packaged locally, no CDN | Desktop voice must start without downloading runtime model/WASM assets. |
| Turn detection | Local VAD speech-end with configurable silence | Keeps continuous mode responsive and independent of provider-side sentence timing. |
| ASR/TTS configuration | Capability-specific profile schema | Enables ASR-only readiness and independently selected fallback/TTS providers. |
| Legacy migration | Normalize to a `default` profile and write new schema only on save | Preserves existing installations and write-only credentials. |
| Fallback input | Buffered PCM converted to WAV | Reuses one utterance across streaming and all existing batch adapters. |
| Fallback policy | Retryable failures only | Avoids masking invalid credentials, missing grants, and malformed settings. |
| Exactly-once behavior | Stable request ID plus monotonic finalized/submitted gates | Prevents late finals and fallback races from creating duplicate tasks. |
| Agent concurrency | One continuous pending slot | Supports barge-in without interleaving or unbounded queued coding tasks. |
| Barge-in behavior | Stop playback and cancel TTS group only | Speech recognition errors must not cancel coding work or approve tools. |
| Progressive TTS | Ordered short synthesis segments sent as each completes | Works with current TTS providers while reducing wait for multi-segment replies. |
| Status announcements | One cached localized phrase per high-level transition | Gives useful feedback without speaking every tool event. |
| Test strategy | Mock cloud WebSockets/HTTP plus client state/PCM tests | Verifies protocol and race behavior without live credentials. |
| TEN integration | None | The requested capabilities fit the existing local Harness and desktop architecture. |

## Requirement Coverage

| Spec Requirements | Plan Coverage |
| --- | --- |
| F1-F2 | PCM capture, press-and-hold controller, stream protocol, exactly-once gate |
| F3 | Capability-specific configuration and provider factories |
| F4-F5 | Aliyun streaming adapter with manual finish flow |
| F6-F9 | Client/server PCM buffers, classified fallback, stable request identity |
| F10-F13 | Agent state mapper, TTS scheduler, grouped playback interruption |
| F14-F16 | Local Silero VAD, turn detector, one pending input slot |
| F17-F18 | Existing Agent submission and unchanged permission-response path |
| F19-F20 | Isolated session workers, independent feature toggles, legacy batch path |

## References

- Alibaba realtime ASR WebSocket flow: https://help.aliyun.com/en/model-studio/fun-asr-realtime-websocket-api
- Alibaba client events and PCM parameters: https://help.aliyun.com/zh/model-studio/fun-asr-client-events
- Alibaba server partial/final events: https://help.aliyun.com/zh/model-studio/fun-asr-server-events
- Alibaba current ASR model selection: https://help.aliyun.com/zh/model-studio/asr-model/
- Browser Silero VAD project: https://github.com/ricky0123/vad
