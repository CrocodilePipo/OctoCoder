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

export type ConfigStatus = {
  ready: boolean;
  configured: boolean;
  error: string;
  message: string;
  configPath: string;
  cwd: string;
  provider: ProviderSettings;
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
  | { type: "pong"; data: null };

export type ClientMessage =
  | { type: "user_message"; data: { content: string } }
  | { type: "project_open"; data: { path: string } }
  | { type: "project_clear"; data: Record<string, never> }
  | { type: "permission_response"; data: { id: string; response: "allow" | "allowAlways" | "deny" } }
  | { type: "config_get"; data: Record<string, never> }
  | { type: "config_save"; data: ConfigSavePayload }
  | { type: "cancel"; data: Record<string, never> }
  | { type: "ping"; data: Record<string, never> };
