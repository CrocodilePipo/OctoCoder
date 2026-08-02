# OctoCoder Voice Agent MVP Plan

## Architecture Overview

The voice MVP adds an audio input/output layer around the existing remote Agent flow. The React renderer records microphone audio with browser media APIs. The existing WebSocket carries JSON control messages and binary audio frames to the local Python backend. A provider-neutral voice service converts audio to text and final response text to audio through OpenAI-compatible HTTP endpoints.

The coding path remains unchanged: a voice transcription becomes a normal user message handled by the current workspace-scoped Agent and permission system. Voice-origin metadata is used only to decide whether the final response should be synthesized and returned to the initiating WebSocket connection.

```text
Renderer MediaRecorder
  -> JSON voice_record_start
  -> one binary encoded-audio frame
  -> JSON voice_record_stop
  -> RemoteServer voice upload/session handler
  -> OpenAI-compatible STT adapter
  -> transcript response or automatic submission
  -> existing RemoteServer._handle_user_message
  -> existing Agent.run and permission flow
  -> final speakable response extractor
  -> OpenAI-compatible TTS adapter
  -> JSON voice_audio_start + binary audio frame(s)
  -> renderer playback queue
```

## Core Data Structures

### VoiceConfig

Backend configuration loaded from the optional `voice` section of `.octocoder/config.yaml`.

```python
@dataclass
class VoiceConfig:
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "tts-1"
    voice: str = "alloy"
    language: str = ""
    auto_submit: bool = False

    def resolve_api_key(self) -> str: ...
    @property
    def configured(self) -> bool: ...
```

The API key may resolve from the saved value or `OCTOCODER_VOICE_API_KEY`. Status responses expose only `apiKeyConfigured`.

### VoiceUpload

Per-WebSocket recording state owned by the backend.

```python
@dataclass
class VoiceUpload:
    request_id: str
    mime_type: str
    started_at: float
    payload: bytearray
```

Only one upload is active per connection. The server rejects duplicate starts, binary data without an active upload, recordings over 120 seconds, and payloads over 16 MiB.

### VoiceAudio

```python
@dataclass(frozen=True)
class VoiceAudio:
    data: bytes
    content_type: str
```

### VoiceProvider

```python
class VoiceProvider(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str,
        content_type: str,
        language: str = "",
    ) -> str: ...

    async def synthesize(self, text: str) -> VoiceAudio: ...
```

### VoiceClientState

Frontend state used by the composer and audio controller.

```typescript
type VoicePhase =
  | "idle"
  | "requesting_permission"
  | "recording"
  | "transcribing"
  | "speaking"
  | "error";

type VoiceClientState = {
  phase: VoicePhase;
  requestId: string | null;
  elapsedMs: number;
  error: string;
  pendingTranscriptRequestId: string | null;
};
```

### WebSocket Protocol Additions

Client JSON messages:

```typescript
{ type: "voice_record_start"; data: { requestId: string; mimeType: string } }
{ type: "voice_record_stop"; data: { requestId: string } }
{ type: "voice_record_cancel"; data: { requestId: string } }
{ type: "user_message"; data: { content: string; source?: "text" | "voice"; voiceRequestId?: string } }
```

The encoded recording is sent as one binary WebSocket frame between `voice_record_start` and `voice_record_stop`.

Server JSON messages:

```typescript
{ type: "voice_status"; data: { requestId: string; phase: VoicePhase; message?: string } }
{ type: "voice_transcript"; data: { requestId: string; text: string; submitted: boolean } }
{ type: "voice_audio_start"; data: {
    requestId: string;
    audioId: string;
    mimeType: string;
    index: number;
    total: number;
  } }
{ type: "voice_error"; data: { requestId: string; message: string } }
```

Each `voice_audio_start` is immediately followed by one binary audio frame. The socket wrapper pairs the metadata with that frame before handing it to the playback queue.

## Module Design

### Backend Configuration

**Responsibility:** Parse, validate, merge, save, and report voice-provider configuration without exposing secrets.

**Public Interface:** `VoiceConfig`, `AppConfig.voice`, validated `voice` dictionary, and the existing config status/save messages extended with voice fields.

**Dependencies:** Existing YAML configuration and validation modules.

Configuration remains optional so CLI users and existing config files continue to work. Enabling voice requires Base URL, API key, STT model, TTS model, and voice name.

### OpenAI-Compatible Voice Provider

**Responsibility:** Implement speech-to-text and text-to-speech HTTP calls.

**Public Interface:** `VoiceProvider.transcribe()` and `VoiceProvider.synthesize()`.

**Dependencies:** Existing `httpx` dependency and `VoiceConfig`.

`transcribe()` sends multipart form data to `<base_url>/audio/transcriptions` with the encoded media file, configured model, optional language, and JSON response format. `synthesize()` sends JSON to `<base_url>/audio/speech` with model, voice, text, and MP3 response format. Both methods apply explicit timeouts, preserve concise provider error details, and validate response content before returning.

Endpoint joining accepts Base URLs with or without a trailing slash and does not duplicate `/v1` supplied by the user.

### Speakable Text Processing

**Responsibility:** Select and normalize only final user-facing prose for speech.

**Public Interface:**

```python
def extract_speakable_text(markdown: str) -> str: ...
def split_speakable_text(text: str, max_chars: int = 3500) -> list[str]: ...
```

**Dependencies:** Python standard library only.

The extractor removes fenced code blocks, inline code formatting, raw URLs, markdown decoration, and empty content. The splitter prefers paragraph and sentence boundaries and guarantees bounded request sizes. Tool events, thinking events, permissions, errors, and diagnostics never enter these functions.

### Remote Voice Session Handling

**Responsibility:** Receive recordings, enforce limits, call STT, bridge transcriptions into the existing Agent, identify the final answer, and return synthesized audio only to the initiating connection.

**Public Interface:** New internal handlers for voice start, binary data, stop, cancel, transcription, and synthesis.

**Dependencies:** `VoiceProvider`, existing `RemoteServer`, Agent events, and WebSocket connection.

The message loop branches on `bytes` before JSON parsing. Transcription and synthesis run in background tasks so ping, cancel, permission responses, and normal chat messages remain responsive. Per-connection uploads and tasks are cleared on disconnect.

For manual submission, `voice_transcript.submitted` is false and the client fills the composer. A later `user_message` includes `source: "voice"` and the request ID. For automatic submission, the backend sends `voice_transcript.submitted` as true and invokes the existing user-message handler exactly once.

During Agent execution, the server tracks text by turn. A turn containing tool use is not selected for speech. At successful loop completion, the latest non-tool final text is processed and synthesized. Cancelled or failed Agent runs do not start TTS.

### Renderer Recording Controller

**Responsibility:** Acquire microphone permission, record one bounded audio clip, manage recording state, and release media resources.

**Public Interface:** A React hook returning voice state and `startRecording()`, `stopRecording()`, `cancelRecording()`, and `stopPlayback()` actions.

**Dependencies:** `navigator.mediaDevices.getUserMedia`, `MediaRecorder`, the socket wrapper, and browser timers.

The recorder chooses the first supported MIME type from `audio/webm;codecs=opus`, `audio/webm`, and `audio/mp4`, falling back to the browser default. It requests audio only, stops every media track on all terminal paths, enforces the 120-second limit in the renderer, checks the 16 MiB payload before upload, and uses request IDs to ignore stale events.

### Renderer Playback Queue

**Responsibility:** Pair incoming audio metadata with binary frames and play one or more synthesized segments in order.

**Public Interface:** `enqueue()`, `stop()`, and `dispose()`.

**Dependencies:** `Blob`, object URLs, and `HTMLAudioElement`.

Stopping playback clears queued segments and releases object URLs without sending an Agent cancellation. New recording stops current playback before requesting the microphone.

### Composer And Settings UI

**Responsibility:** Expose compact microphone/playback controls, voice states, editable transcripts, and voice-provider settings.

**Public Interface:** Existing `Composer` and `SettingsDialog` props extended with voice state/actions/configuration.

**Dependencies:** Existing React state, Lucide icons, socket protocol, and current CSS system.

The microphone control is icon-first with a tooltip and stable dimensions. Recording/transcribing/speaking status appears inside the composer action area without resizing it. Voice settings are grouped separately from the coding model settings. Disabling voice disables the microphone path but leaves normal send behavior unchanged.

### Electron Microphone Permission Policy

**Responsibility:** Allow microphone-only media requests from the trusted OctoCoder renderer and reject unrelated media/origins.

**Public Interface:** Session permission check and request handlers registered when the window is created.

**Dependencies:** Electron `session`/`webContents` permission APIs.

Both permission check and request handlers are installed because Electron documents that complete permission handling requires both. The policy accepts audio media requests from the packaged `file:` renderer and configured local development renderer, rejects video and untrusted origins, and leaves operating-system permission prompts intact.

### Diagnostics

**Responsibility:** Make voice configuration and runtime state diagnosable without leaking secrets or audio content.

**Public Interface:** Existing diagnostics export extended with enabled/configured flags, selected model names, current phase, and last sanitized error.

**Dependencies:** Existing desktop diagnostics export.

Raw microphone bytes, synthesized audio, transcribed prompt content, and API keys are excluded.

## Module Interactions

1. The user enables and configures voice settings. The backend validates structure, saves the secret, reloads runtime configuration, and returns redacted status.
2. The user clicks the microphone. The renderer stops existing playback, requests audio-only permission, creates a request ID, records, and displays elapsed time.
3. Stopping recording sends start metadata, one binary encoded recording, and stop metadata in WebSocket order.
4. The backend validates connection state, MIME type, duration, size, and voice configuration, then calls STT asynchronously.
5. Manual mode returns an editable transcript. Automatic mode publishes the transcript as submitted and invokes the same Agent handler used by typed tasks.
6. A manually reviewed transcript is later sent as a normal user message with voice-origin metadata.
7. The Agent runs with the existing workspace, tools, and permission flow. Voice metadata does not change authorization behavior.
8. On successful loop completion, the backend extracts the latest final response, removes non-speakable content, splits long prose, and synthesizes each segment.
9. The initiating renderer receives paired audio metadata/binary frames and plays them sequentially. Other connected clients still receive normal text events but not private synthesized audio.
10. Stop-playback affects only the renderer queue. Agent cancellation remains the existing separate stop action.

## File Organization

```text
OctoCoder/
  herness/
    octocoder/
      config.py                         - add VoiceConfig to application configuration
      validator.py                      - validate optional voice settings
      remote.py                         - binary protocol, voice sessions, Agent/TTS bridge
      voice/
        __init__.py                     - public voice module exports
        models.py                       - VoiceUpload and VoiceAudio data structures
        provider.py                     - VoiceProvider protocol and provider errors
        openai_compatible.py            - HTTP STT/TTS implementation
        text.py                         - speakable-text extraction and splitting
    tests/
      test_voice_config.py              - validation, merge, and secret-redaction tests
      test_voice_provider.py            - mocked OpenAI-compatible HTTP contract tests
      test_voice_text.py                - markdown filtering and segmentation tests
      test_voice_remote.py              - upload limits and Agent bridge behavior tests
  client/
    src/
      App.tsx                           - voice state integration, composer, settings, diagnostics
      socket.ts                         - binary send/receive and audio metadata pairing
      types.ts                          - voice configuration and protocol types
      styles.css                        - compact recording/status/settings styles
      voice/
        recorder.ts                     - MediaRecorder lifecycle and limits
        playback.ts                     - ordered audio playback and cleanup
        useVoiceAgent.ts                - renderer voice state machine
  desktop/
    src/
      main.cjs                          - trusted microphone permission policy
```

## Technical Decisions

### Multi-Provider Adapter Extension

The provider-neutral `VoiceProvider` protocol remains the runtime boundary. A factory selects `SiliconFlowVoiceProvider`, `AliyunVoiceProvider`, or the generic `OpenAICompatibleVoiceProvider` from `VoiceConfig.provider`. Provider presets live in validation and renderer configuration so saved settings are explicit and portable rather than dependent on hidden runtime defaults.

SiliconFlow reuses the compatible HTTP transport with its documented request fields. Alibaba Cloud Model Studio has a dedicated adapter because ASR accepts Base64 audio through chat completions while TTS returns a signed download URL from the DashScope speech service. Unknown provider identifiers fail structural validation before the config writer replaces the existing file.

The settings UI applies provider defaults on selection, keeps all endpoint/model fields editable, and sends the provider identifier with the existing write-only credential payload. Runtime status returns only `provider`, normalized non-secret fields, and `has_api_key`.

Volcengine uses a dedicated `VolcengineVoiceProvider`. Flash ASR posts Base64 WAV audio to `/api/v3/auc/bigmodel/recognize/flash` with the documented `X-Api-*` headers. Non-streaming TTS posts to `/api/v1/tts` with `Authorization: Bearer; <token>` and returns Base64 MP3. Because Chromium records WebM by default while this ASR API documents WAV, MP3, and OGG Opus, the renderer records Volcengine input as 16 kHz mono 16-bit PCM WAV. App ID and Access Token are required; Secret Key is retained as an optional write-only value for future HMAC support but is not used by the Bearer path.

| Decision | Choice | Rationale |
| --- | --- | --- |
| Voice architecture | Native OctoCoder adapter layer | Avoids TEN desktop licensing restrictions and preserves current packaging. |
| Speech provider | Configurable OpenAI-compatible REST endpoints | Matches the approved scope and works without another bundled runtime. |
| Audio capture | Browser `getUserMedia` plus `MediaRecorder` | Available in Electron Chromium and avoids native capture dependencies. |
| Audio transport | Existing WebSocket with JSON control and binary frames | Reuses the local connection while avoiding Base64 overhead. |
| Recording granularity | One encoded frame per completed recording | Keeps MVP state deterministic; partial streaming remains out of scope. |
| Automatic submission owner | Backend | Guarantees exactly-once execution even if renderer state changes. |
| Manual transcript submission | Existing `user_message` with voice-origin metadata | Preserves editable review and reuses the existing Agent path. |
| TTS trigger | Latest successful non-tool final turn from a voice-origin task | Prevents thinking, tools, permissions, and intermediate work from being spoken. |
| Long TTS responses | Sentence-aware chunks up to 3500 characters | Fits common speech endpoint limits without truncating the final answer. |
| Audio response | Metadata JSON followed by a binary frame | Supports multiple chunks without exposing large Base64 strings to React state. |
| Secret handling | Save-only API key plus redacted status | Matches existing settings behavior while preventing secret round trips. |
| Permission safety | Voice cannot answer permission requests | Recognition errors must not authorize filesystem or command actions. |
| New dependencies | None for MVP | `httpx` and browser media APIs already cover the required behavior. |
| Verification platform | Automated cross-platform logic plus Windows packaged E2E | Matches the current build environment while retaining portable APIs. |
