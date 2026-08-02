# OctoCoder Voice Agent MVP Spec

## Background

OctoCoder currently accepts text tasks through its React/Electron client and sends them to the local Python coding-agent backend over WebSocket. Users cannot speak a task or listen to the final response.

The first voice-agent iteration will add a lightweight voice input/output layer around the existing OctoCoder Agent. It will use separately configurable OpenAI-compatible speech-to-text and text-to-speech services. The existing coding Agent remains responsible for reasoning, project context, tool use, permission checks, and file changes.

## Goals

- Let desktop users record a spoken coding request from the existing composer.
- Convert recorded speech into editable text before it reaches the coding Agent.
- Optionally submit a successful transcription automatically.
- Read the final user-facing response aloud for tasks initiated by voice.
- Keep speech providers independently configurable from the text-model provider.
- Preserve the existing text workflow and permission safety model.

## Functional Requirements

- F1: The composer provides a microphone control that starts and stops one recording session.
- F2: The client visibly distinguishes idle, requesting-permission, recording, transcribing, speaking, and error states.
- F3: A completed recording is sent to the local OctoCoder backend, which submits it to a configured OpenAI-compatible speech-to-text endpoint.
- F4: A successful transcription is placed in the composer as editable text and is not submitted automatically by default.
- F5: The user can enable automatic submission of successful voice transcriptions in settings.
- F6: When a transcribed task is submitted, it uses the same current workspace, conversation, coding Agent, tools, and permission checks as a typed task.
- F7: For a task initiated by voice, the final user-facing assistant response is sent to a configured OpenAI-compatible text-to-speech endpoint and played by the desktop client.
- F8: Thinking text, tool arguments, tool output, source code blocks, permission prompts, errors, and diagnostic messages are not automatically spoken.
- F9: The user can stop current audio playback without cancelling the underlying coding task.
- F10: Voice settings include enabled state, API Base URL, API Key, speech-to-text model, text-to-speech model, voice name, optional language, and automatic-submit preference.
- F11: The voice API Key is write-only in the UI: configuration status may report whether it exists but must not return the stored secret to the client.
- F12: Missing microphone permission, unsupported recording, invalid configuration, network failures, provider errors, and unsupported audio responses produce a visible recoverable error.
- F13: Voice recording has a bounded duration and payload size; reaching either limit stops or rejects the recording with a visible explanation.
- F14: Voice input cannot approve tool permissions, bypass permission rules, or silently convert a permission prompt into an allowed action.

## Non-Functional Requirements

- N1: The TEN Runtime and TEN Agent examples are not bundled or copied into the desktop application.
- N2: Speech-provider integration follows the commonly used OpenAI-compatible `/audio/transcriptions` and `/audio/speech` request shapes while keeping endpoint, model, and voice configurable.
- N3: Existing typed chat behavior remains available when voice is disabled or unavailable.
- N4: Voice failures do not terminate the local backend, disconnect the main chat WebSocket, or discard the current conversation.
- N5: The implementation respects Electron context isolation and does not expose Node.js APIs directly to the renderer.
- N6: Audio capture resources, media tracks, object URLs, and playback instances are released when a session finishes, is cancelled, errors, or the application closes.
- N7: The first release limits one recording to 120 seconds and one encoded upload to 16 MiB.
- N8: User-facing voice controls and status text are available in Chinese and match the current compact OctoCoder desktop UI.
- N9: The implementation is designed for Windows, Linux, and macOS, with Windows serving as the executable end-to-end verification platform for this implementation cycle.

## Out Of Scope

- Full-duplex speech-to-speech conversation.
- Voice activity detection, semantic turn detection, wake words, and automatic barge-in.
- Streaming partial transcription or streaming synthesized audio.
- Local/offline speech models and bundled model weights.
- Agora RTC, SIP calling, video input, avatars, and speaker diarization.
- Bundling or deriving TEN Framework Runtime code.
- Using speech as an authorization mechanism for tool or filesystem permissions.
- Speaking every typed task response or reading complete tool logs and code changes aloud.

## Acceptance Criteria

- AC1: Clicking the microphone control requests microphone access and enters a visible recording state; clicking it again ends recording.
- AC2: Denied microphone permission or an unavailable recording API shows an actionable error and leaves typed chat usable.
- AC3: A valid recording with valid voice settings produces a transcription in the composer without automatically executing it under default settings.
- AC4: With automatic submission enabled, a successful transcription is submitted exactly once through the existing task flow.
- AC5: A submitted voice task operates in the currently selected project, and any tool permission request still requires the existing explicit UI decision.
- AC6: After a voice task completes, only its final user-facing assistant response is synthesized and played.
- AC7: The user can stop synthesized playback while the completed conversation and task result remain visible.
- AC8: Saving voice settings does not expose the stored API Key in subsequent configuration responses.
- AC9: Missing settings, HTTP failures, malformed provider responses, oversized recordings, and recordings longer than 120 seconds all produce recoverable visible errors.
- AC10: Disabling voice hides or disables voice execution without affecting typed task submission.
- AC11: Frontend production build, backend automated tests, and desktop JavaScript syntax checks pass.
- AC12: The packaged Windows application can request microphone access, transcribe one spoken task using configured services, run it through the existing Agent, and play the final response without launching an additional terminal process.

## Multi-Provider Extension

- MP1: Voice settings expose a provider selector for SiliconFlow, Alibaba Cloud Model Studio, OpenAI, and a custom OpenAI-compatible service.
- MP2: Selecting a provider fills its documented Base URL, STT model, TTS model, and voice defaults; every field remains editable before saving.
- MP3: SiliconFlow uses its OpenAI-compatible transcription and speech endpoints without sending unsupported optional transcription fields.
- MP4: Alibaba Cloud Model Studio uses the Qwen ASR chat-completions audio contract and the DashScope non-streaming TTS contract, including retrieval of the returned signed audio URL.
- MP5: The backend selects the adapter from the saved provider identifier and rejects unknown identifiers before changing the configuration file.
- MP6: Provider status and diagnostics may include the provider identifier and whether a key exists, but never include the API key itself.
- MP7: Existing voice configuration without a provider identifier remains compatible and is treated as custom OpenAI-compatible configuration.
- MP8: Volcengine Doubao Voice is selectable with App ID, Access Token, optional Secret Key, ASR resource ID, TTS model, and voice type fields.
- MP9: Volcengine ASR uses the flash recording-recognition HTTP contract and receives 16 kHz mono PCM WAV generated locally by the renderer.
- MP10: Volcengine TTS uses the Bearer Token V1 non-streaming HTTP contract and decodes the returned Base64 MP3 audio.
- MP11: App ID, Access Token, and Secret Key are write-only; only configured booleans may appear in runtime status or diagnostics.
