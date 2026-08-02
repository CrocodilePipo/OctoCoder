export type ConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";

export type CommandInfo = {
  name: string;
  description: string;
};

export type Usage = {
  inputTokens: number;
  outputTokens: number;
};

export type ToolStatus = "running" | "ok" | "error";

export type ProviderSettings = {
  name: string;
  protocol: "anthropic" | "openai" | "openai-compat";
  baseUrl: string;
  model: string;
  apiKeyConfigured: boolean;
  thinking: boolean;
  contextWindow: number;
  maxOutputTokens: number;
};

export type VoicePhase =
  | "idle"
  | "connecting"
  | "listening"
  | "requesting_permission"
  | "recording"
  | "transcribing"
  | "queued"
  | "analyzing"
  | "executing"
  | "waiting_approval"
  | "speaking"
  | "error";

export type VoiceProviderId = "openai" | "siliconflow" | "aliyun" | "volcengine" | "openai-compatible";

export type VoiceSettings = {
  provider: VoiceProviderId;
  enabled: boolean;
  configured: boolean;
  baseUrl: string;
  apiKeyConfigured: boolean;
  appIdConfigured: boolean;
  secretKeyConfigured: boolean;
  sttModel: string;
  ttsModel: string;
  voice: string;
  language: string;
  autoSubmit: boolean;
  streamingConfigured: boolean;
  ttsEnabled: boolean;
  ttsConfigured: boolean;
  mode: "hold" | "continuous";
  primaryAsrProfile: string;
  fallbackAsrProfiles: string[];
  ttsProfile: string;
  statusAnnouncements: boolean;
  continuousSilenceMs: number;
  profiles: VoiceProviderSettings[];
};

export type VoiceProviderSettings = {
  id: string;
  name: string;
  provider: VoiceProviderId;
  baseUrl: string;
  streamingUrl: string;
  workspaceId: string;
  apiKeyConfigured: boolean;
  appIdConfigured: boolean;
  secretKeyConfigured: boolean;
  batchSttModel: string;
  streamingSttModel: string;
  ttsModel: string;
  voice: string;
  language: string;
  batchAsrConfigured: boolean;
  streamingAsrConfigured: boolean;
  ttsConfigured: boolean;
};

export type VoiceProviderSavePayload = Omit<
  VoiceProviderSettings,
  "apiKeyConfigured" | "appIdConfigured" | "secretKeyConfigured" |
  "batchAsrConfigured" | "streamingAsrConfigured" | "ttsConfigured"
> & {
  apiKey: string;
  appId: string;
  secretKey: string;
};

export type VoiceConfigSavePayload = {
  provider: VoiceProviderId;
  enabled: boolean;
  baseUrl: string;
  apiKey: string;
  appId: string;
  secretKey: string;
  sttModel: string;
  ttsModel: string;
  voice: string;
  language: string;
  autoSubmit: boolean;
  mode: "hold" | "continuous";
  primaryAsrProfile: string;
  fallbackAsrProfiles: string[];
  ttsEnabled: boolean;
  ttsProfile: string;
  statusAnnouncements: boolean;
  continuousSilenceMs: number;
  profiles: VoiceProviderSavePayload[];
};

export type VoiceAudioMetadata = {
  requestId: string;
  audioId: string;
  mimeType: string;
  index: number;
  total: number;
  groupId: string;
  kind: "status" | "response";
};

export type ConfigStatus = {
  ready: boolean;
  configured: boolean;
  error: string;
  message: string;
  configPath: string;
  cwd: string;
  provider: ProviderSettings;
  voice: VoiceSettings;
};

export type ConfigSavePayload = {
  name: string;
  protocol: ProviderSettings["protocol"];
  baseUrl: string;
  model: string;
  apiKey: string;
  thinking: boolean;
  contextWindow: number;
  maxOutputTokens: number;
  permissionMode: "default" | "acceptEdits" | "plan" | "bypassPermissions";
  voice: VoiceConfigSavePayload;
};

export type ProjectInfo = {
  name: string;
  path: string;
  lastOpened?: number;
};

export type TimelineItem =
  | {
      id: string;
      type: "user";
      content: string;
      createdAt: number;
    }
  | {
      id: string;
      type: "assistant";
      content: string;
      streaming: boolean;
      createdAt: number;
    }
  | {
      id: string;
      type: "thinking";
      content: string;
      createdAt: number;
    }
  | {
      id: string;
      type: "tool";
      toolId: string;
      toolName: string;
      args: unknown;
      output: string;
      elapsed?: number;
      status: ToolStatus;
      createdAt: number;
    }
  | {
      id: string;
      type: "permission";
      permissionId: string;
      toolName: string;
      description: string;
      status: "pending" | "allow" | "allowAlways" | "deny";
      createdAt: number;
    }
  | {
      id: string;
      type: "system" | "error" | "done" | "retry" | "compact";
      content: string;
      createdAt: number;
    };

export type ServerMessage =
  | { type: "connected"; data: { session: string; cwd: string } }
  | { type: "project_opened"; data: { name: string; path: string; session: string } }
  | { type: "commands"; data: CommandInfo[] }
  | { type: "config_status"; data: ConfigStatus }
  | { type: "system"; data: { message: string } }
  | { type: "clear"; data: null }
  | { type: "command_done"; data: null }
  | { type: "replay_user"; data: { content: string } }
  | { type: "replay_assistant"; data: { content: string } }
  | { type: "stream_text"; data: { text: string } }
  | { type: "stream_end"; data: { text: string } }
  | { type: "thinking_text"; data: { text: string } }
  | { type: "tool_use"; data: { toolId: string; toolName: string; args: unknown } }
  | {
      type: "tool_result";
      data: {
        toolId: string;
        toolName: string;
        output: string;
        isError: boolean;
        elapsed?: number;
      };
    }
  | {
      type: "permission_request";
      data: { id: string; toolName: string; description: string };
    }
  | { type: "turn_complete"; data: { turn: number } }
  | { type: "loop_complete"; data: { totalTurns: number; elapsed: number } }
  | { type: "usage"; data: Usage }
  | { type: "error"; data: { message: string } }
  | { type: "compact"; data: { message: string } }
  | { type: "retry"; data: { reason: string; waitMs: number } }
  | { type: "voice_status"; data: { requestId: string; phase: VoicePhase } }
  | { type: "voice_stream_ready"; data: { requestId: string; mode: "hold" | "continuous"; format: "pcm_s16le"; sampleRate: 16000; channels: 1 } }
  | { type: "voice_transcript_partial"; data: { requestId: string; text: string; sentenceId: number; revision: number; final: boolean } }
  | { type: "voice_transcript"; data: { requestId: string; text: string; submitted: boolean; provider?: string; profileId?: string; fallbackUsed?: boolean } }
  | { type: "voice_audio_start"; data: VoiceAudioMetadata }
  | { type: "voice_audio_cancel"; data: { requestId: string } }
  | { type: "voice_error"; data: { requestId: string; message: string } }
  | { type: "pong"; data: null };

export type ClientMessage =
  | { type: "user_message"; data: { content: string; source?: "text" | "voice"; voiceRequestId?: string } }
  | { type: "project_open"; data: { path: string } }
  | { type: "project_clear"; data: Record<string, never> }
  | { type: "permission_response"; data: { id: string; response: "allow" | "allowAlways" | "deny" } }
  | { type: "config_get"; data: Record<string, never> }
  | { type: "config_save"; data: ConfigSavePayload }
  | { type: "voice_record_start"; data: { requestId: string; mimeType: string } }
  | { type: "voice_record_stop"; data: { requestId: string } }
  | { type: "voice_record_cancel"; data: { requestId: string } }
  | { type: "voice_stream_start"; data: { requestId: string; mode: "hold" | "continuous"; format: "pcm_s16le"; sampleRate: 16000; channels: 1 } }
  | { type: "voice_stream_chunk"; data: { requestId: string; sequence: number; byteLength: number } }
  | { type: "voice_stream_finish"; data: { requestId: string } }
  | { type: "voice_stream_cancel"; data: { requestId: string } }
  | { type: "voice_playback_interrupt"; data: { requestId: string } }
  | { type: "cancel"; data: Record<string, never> }
  | { type: "ping"; data: Record<string, never> };
