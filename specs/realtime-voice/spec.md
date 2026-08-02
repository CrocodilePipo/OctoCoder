# OctoCoder Realtime Voice Spec

## Background

OctoCoder currently supports a completed-recording voice flow: the desktop client records a whole clip, uploads it to the local Harness, waits for batch speech recognition, and optionally sends the transcript through the existing coding Agent. Text-to-speech is coupled to voice configuration, and no partial transcript is available while the user is speaking.

This iteration upgrades voice input into a real-time interaction channel. Alibaba Cloud Model Studio real-time speech recognition is the first domestic streaming provider. The existing batch providers remain available as fallback paths. Voice remains an input and presentation layer around the existing workspace-scoped Agent, tools, permission checks, and conversation state.

## Goals

- Let users hold the microphone control, see live transcription, and submit the final utterance when they release it.
- Allow speech-to-text to operate without any text-to-speech configuration.
- Add Alibaba Cloud Model Studio as the first real-time streaming ASR provider.
- Preserve captured speech long enough to fall back to batch recognition when streaming fails.
- Surface and optionally announce the Agent states that matter during voice operation.
- Optionally play short assistant responses progressively and allow immediate playback interruption.
- Add an opt-in hands-free conversation mode using local voice activity and turn detection.
- Support an independently configured primary provider and fallback provider without duplicate task submission.

## Functional Requirements

- F1: The composer provides a press-and-hold interaction. Pressing starts microphone capture and streaming recognition, partial text is shown while speaking, and releasing finalizes and submits the recognized utterance exactly once.
- F2: Releasing without intelligible speech, cancelling before release, losing microphone permission, or receiving an empty final transcript does not submit a task and leaves typed chat usable.
- F3: Speech-to-text can be enabled and considered ready without a text-to-speech model, voice, or text-to-speech credential. Text-to-speech has a separate disabled-by-default setting and readiness status.
- F4: Alibaba Cloud Model Studio real-time speech recognition is selectable as the primary streaming provider and supports Chinese real-time partial and final transcripts.
- F5: Press-and-hold recognition uses explicit end-of-turn submission controlled by the client release action rather than provider-detected silence.
- F6: The client keeps a bounded in-memory copy of the current utterance so that a retryable streaming failure can fall back to batch recognition without asking the user to repeat the utterance.
- F7: Voice settings support independently configured provider profiles, one primary ASR profile, and an optional ordered fallback profile. Existing single-provider settings migrate without exposing or discarding saved credentials.
- F8: Provider fallback is attempted only for retryable transport, timeout, rate-limit, interrupted-response, and provider-server failures. Authentication, authorization, invalid-request, and unsupported-format failures are reported directly so configuration problems are not hidden.
- F9: A spoken utterance is assigned one stable request identity across streaming, batch fallback, and Agent submission. Late or duplicated provider results cannot submit the same utterance more than once.
- F10: During a voice-origin task, the client visibly reports listening, transcribing, analyzing, executing, waiting for approval, speaking, interrupted, and recoverable-error states.
- F11: When text-to-speech is enabled, short localized status announcements are available for analyzing, executing, and waiting for approval. Repeated low-level tool events do not produce repeated announcements.
- F12: When text-to-speech is enabled, short final user-facing replies begin playback progressively without waiting for every speech segment to be synthesized. Source code, tool output, diagnostics, reasoning, secrets, paths, and permission details are not automatically spoken.
- F13: Starting a new utterance immediately stops current assistant audio playback. Stopping playback or speaking over it does not cancel the underlying coding task, approve a permission request, or alter tool authorization.
- F14: An opt-in continuous-conversation mode uses local voice activity detection to begin capture and local turn detection to finalize an utterance after configurable sustained silence.
- F15: Continuous-conversation mode returns to listening after a completed response or recoverable recognition error and can be stopped explicitly from the composer.
- F16: In continuous mode, speech detected during assistant playback interrupts playback and becomes the next utterance. If the Agent is still busy, the recognized utterance is retained as one pending input and is not silently interleaved with the active turn.
- F17: Voice-origin transcripts enter the same current workspace or default working directory, conversation, coding Agent, tools, and permission flow as typed messages.
- F18: Voice input cannot approve tool permissions, bypass permission rules, or act as identity verification. Permission decisions continue through the existing explicit desktop approval controls.
- F19: Streaming connection loss, malformed events, provider errors, and fallback exhaustion produce sanitized recoverable errors without terminating the Harness or main OctoCoder WebSocket.
- F20: Users can disable continuous mode, streaming ASR, fallback, status announcements, and final-response speech independently while retaining batch voice input or typed chat where configured.

## Non-Functional Requirements

- N1: Microphone audio uses a format supported by the selected real-time provider and is transmitted in bounded frames with backpressure so a slow connection cannot grow memory without limit.
- N2: Partial transcript updates are rate-limited before entering React state and remain responsive enough to appear live during normal speech.
- N3: The streaming connection uses heartbeat, explicit timeouts, bounded retries, and deterministic cleanup on release, cancel, error, disconnect, settings reload, and application exit.
- N4: Audio, partial transcripts, credentials, and synthesized speech are not written to application logs or diagnostics. Audio buffering is in memory and released after recognition or fallback finishes.
- N5: Provider credentials remain write-only. Runtime status may expose provider identifiers, capabilities, and configured booleans but never secret values.
- N6: Existing typed chat, batch voice recognition, workspace selection, Agent execution, and permission behavior remain backward compatible.
- N7: The implementation works with the packaged Electron application on Windows and retains portable browser/Python interfaces for Linux and macOS.
- N8: The TEN Runtime is not bundled. Local VAD and turn detection are contained within the OctoCoder desktop client.
- N9: Streaming and fallback failures are classified consistently so retry decisions are deterministic and testable without live provider credentials.
- N10: The existing recording duration and payload limits remain enforced; continuous mode additionally bounds each detected utterance and the single pending-input queue.

## Out Of Scope

- Wake words and always-on background listening when the OctoCoder window is not in an active voice session.
- Voice biometrics, speaker identity, or voice-based approval of filesystem and command permissions.
- Automatically cancelling an active coding task merely because the user starts speaking.
- Multiple simultaneous queued spoken tasks while the Agent is busy.
- Offline ASR/TTS model weights bundled into the desktop installer.
- RTC, telephone/SIP, video, avatars, speaker diarization, or meeting transcription.
- Replacing the existing coding Agent or tool protocol with TEN Framework.
- Guaranteeing seamless failover for non-retryable account, billing, resource-grant, or malformed-configuration errors.

## Acceptance Criteria

- AC1: Holding the microphone displays partial text during speech; releasing produces one final transcript and one Agent submission.
- AC2: Cancelling, releasing silence, denied microphone access, and empty recognition results produce no Agent submission and leave the composer usable.
- AC3: Enabling ASR with no TTS model or voice saves successfully, enables the microphone, and never attempts speech synthesis.
- AC4: Enabling TTS separately restores status/final-response speech without changing ASR readiness.
- AC5: Alibaba Cloud Model Studio streaming recognition sends microphone audio while the user is speaking and exposes partial and final Chinese transcripts through the local OctoCoder protocol.
- AC6: A simulated retryable streaming disconnect falls back to batch recognition from the buffered utterance and submits the resulting transcript exactly once.
- AC7: Simulated authentication or authorization failure does not trigger fallback and shows a configuration-oriented error.
- AC8: A late streaming final result arriving after batch fallback cannot create a duplicate transcript or task.
- AC9: Voice-origin tasks visibly transition through analyzing and executing, and permission requests visibly transition to waiting for approval.
- AC10: With status announcements enabled, each high-level state is announced at most once per relevant transition and tool-event noise is not spoken.
- AC11: With TTS enabled, the first playable final-response segment can start before later segments finish; interrupting playback releases queued audio without cancelling the task.
- AC12: In continuous mode, speech begins capture without pressing the microphone and sustained silence finalizes one utterance; stopping continuous mode releases microphone resources.
- AC13: Speaking during playback stops playback and captures a new utterance. If the Agent is busy, at most one pending utterance is retained and submitted after the active turn becomes available.
- AC14: Voice transcripts use the selected workspace or default working directory and cannot approve an existing permission request.
- AC15: Provider profiles and existing single-provider credentials survive configuration migration while all configuration/status/diagnostic responses remain secret-free.
- AC16: Streaming errors do not close the main chat WebSocket or terminate the Harness; a subsequent typed or spoken task can still be submitted.
- AC17: Backend automated tests, client production build, Electron syntax checks, packaged backend build, and Windows desktop packaging complete successfully.
- AC18: The packaged Windows application completes one press-and-hold streaming task, one simulated or real fallback task, one optional spoken response, and one continuous-mode turn without opening a terminal window.
