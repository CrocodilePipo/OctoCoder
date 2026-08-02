import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, RefObject, ReactNode } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  Circle,
  CircleUserRound,
  Folder,
  Hammer,
  KeyRound,
  Loader2,
  MessagesSquare,
  Mic,
  MoreHorizontal,
  OctagonX,
  PanelLeft,
  Plus,
  Send,
  Settings,
  Square,
  SquarePen,
  Trash2,
  VolumeX,
  X
} from "lucide-react";
import { OctoCoderSocket } from "./socket";
import { useVoiceAgent } from "./voice/useVoiceAgent";
import type {
  ClientMessage,
  CommandInfo,
  ConfigSavePayload,
  ConfigStatus,
  ConnectionState,
  ProjectInfo,
  ServerMessage,
  TimelineItem,
  ToolStatus,
  Usage,
  VoicePhase,
  VoiceProviderId,
  VoiceProviderSavePayload,
  VoiceSettings
} from "./types";
import { formatElapsed, makeId, stringifyJson, toolPreview } from "./utils";

const T = {
  appName: "OctoCoder",
  defaultWorkspace: "\u9ed8\u8ba4\u5de5\u4f5c\u8def\u5f84",
  newTask: "\u65b0\u5efa\u4efb\u52a1",
  chat: "\u804a\u5929",
  fileMenu: "\u6587\u4ef6",
  editMenu: "\u7f16\u8f91",
  viewMenu: "\u89c6\u56fe",
  helpMenu: "\u5e2e\u52a9",
  toggleSidebar: "\u6536\u8d77\u6216\u5c55\u5f00\u8fb9\u680f",
  back: "\u540e\u9000",
  forward: "\u524d\u8fdb",
  project: "\u9879\u76ee",
  projects: "\u9879\u76ee",
  settings: "\u8bbe\u7f6e",
  chooseProject: "\u9009\u62e9\u9879\u76ee",
  chooseProjectFolder: "\u9009\u62e9\u672c\u5730\u9879\u76ee\u6587\u4ef6\u5939",
  startInProject: "\u5f00\u59cb\u5728\u8fd9\u4e2a\u9879\u76ee\u4e2d\u5de5\u4f5c",
  openProject: "\u6253\u5f00\u8fd9\u4e2a\u9879\u76ee",
  removeWorkspace: "\u79fb\u9664",
  workspaceActions: "\u5de5\u4f5c\u533a\u64cd\u4f5c",
  modelNotConfigured: "\u672a\u914d\u7f6e\u6a21\u578b",
  ready: "\u5df2\u51c6\u5907\u597d",
  readyHint: "\u53ef\u4ee5\u5148\u9009\u62e9\u5de6\u4fa7\u9879\u76ee\uff1b\u5982\u679c\u76f4\u63a5\u63d0\u95ee\uff0cOctoCoder \u4f1a\u5728\u9ed8\u8ba4\u5de5\u4f5c\u8def\u5f84\u5185\u6267\u884c\u3002",
  settingsRequired: "\u9700\u8981\u5b8c\u6210\u8bbe\u7f6e",
  settingsHint: "\u5148\u4fdd\u5b58\u6a21\u578b\u914d\u7f6e\uff0c\u7136\u540e\u9009\u62e9\u672c\u5730\u9879\u76ee\u6587\u4ef6\u5939\u5f00\u59cb\u5de5\u4f5c\u3002",
  inputPlaceholder: "\u8981\u6c42\u540e\u7eed\u53d8\u66f4",
  disabledPlaceholder: "\u9700\u8981\u5148\u5728\u8bbe\u7f6e\u91cc\u5b8c\u6210\u914d\u7f6e",
  environment: "\u73af\u5883\u4fe1\u606f",
  changes: "\u53d8\u66f4",
  local: "\u672c\u5730",
  push: "\u63d0\u4ea4\u6216\u63a8\u9001",
  background: "\u540e\u53f0\u8fdb\u7a0b",
  cwd: "\u5f53\u524d\u5de5\u4f5c\u76ee\u5f55",
  source: "\u6765\u6e90",
  currentTask: "\u5f53\u524d\u4efb\u52a1",
  waitingConfig: "\u7b49\u5f85\u914d\u7f6e",
  notSelected: "\u672a\u9009\u62e9",
  cancel: "\u53d6\u6d88",
  saveVerify: "\u4fdd\u5b58\u5e76\u9a8c\u8bc1",
  configVerified: "\u914d\u7f6e\u5df2\u9a8c\u8bc1\u3002",
  closeSettings: "\u5173\u95ed\u8bbe\u7f6e",
  notSignedIn: "\u672a\u767b\u5165",
  openProjectFolder: "\u6253\u5f00\u9879\u76ee\u6587\u4ef6\u5939",
  recentProjects: "\u6700\u8fd1\u9879\u76ee",
  noRecentProjects: "\u6682\u65e0\u6700\u8fd1\u9879\u76ee",
  defaultChat: "\u9ed8\u8ba4\u5de5\u4f5c\u8def\u5f84\u804a\u5929",
  quit: "\u9000\u51fa",
  undo: "\u64a4\u9500",
  redo: "\u91cd\u505a",
  cut: "\u526a\u5207",
  copy: "\u590d\u5236",
  paste: "\u7c98\u8d34",
  selectAll: "\u5168\u9009",
  clearInput: "\u6e05\u7a7a\u8f93\u5165\u6846",
  clearConversation: "\u6e05\u7a7a\u5f53\u524d\u5bf9\u8bdd",
  copyLastReply: "\u590d\u5236\u6700\u540e\u4e00\u6761\u56de\u590d",
  zoomIn: "\u653e\u5927",
  zoomOut: "\u7f29\u5c0f",
  zoomReset: "\u91cd\u7f6e\u7f29\u653e",
  fullscreen: "\u5168\u5c4f",
  reloadUi: "\u91cd\u65b0\u52a0\u8f7d\u754c\u9762",
  devTools: "\u6253\u5f00\u5f00\u53d1\u8005\u5de5\u5177",
  quickStart: "\u5feb\u901f\u5f00\u59cb",
  checkConfig: "\u68c0\u67e5\u914d\u7f6e",
  openLogsFolder: "\u6253\u5f00\u65e5\u5fd7\u76ee\u5f55",
  exportDiagnostics: "\u5bfc\u51fa\u8bca\u65ad\u4fe1\u606f",
  about: "\u5173\u4e8e OctoCoder",
  copiedLastReply: "\u5df2\u590d\u5236\u6700\u540e\u4e00\u6761\u56de\u590d\u3002",
  noAssistantReply: "\u8fd8\u6ca1\u6709\u53ef\u590d\u5236\u7684\u56de\u590d\u3002",
  checkingConfig: "\u6b63\u5728\u68c0\u67e5\u914d\u7f6e\uff0c\u7ed3\u679c\u4f1a\u5728\u8bbe\u7f6e\u7a97\u53e3\u4e2d\u66f4\u65b0\u3002",
  logsOpened: "\u5df2\u6253\u5f00\u65e5\u5fd7\u76ee\u5f55\u3002",
  diagnosticsExported: "\u8bca\u65ad\u4fe1\u606f\u5df2\u5bfc\u51fa",
  actionFailed: "\u64cd\u4f5c\u5931\u8d25",
  quickStartTitle: "OctoCoder \u5feb\u901f\u5f00\u59cb",
  quickStartBody: "\u5148\u5728\u8bbe\u7f6e\u91cc\u586b\u5199\u6a21\u578b\u548c API Key\uff0c\u7136\u540e\u9009\u62e9\u672c\u5730\u9879\u76ee\u6587\u4ef6\u5939\u5f00\u59cb\u4efb\u52a1\u3002\u5982\u679c\u4e0d\u9009\u9879\u76ee\u76f4\u63a5\u63d0\u95ee\uff0cOctoCoder \u4f1a\u5728\u9ed8\u8ba4\u5de5\u4f5c\u8def\u5f84\u5185\u6267\u884c\u3002",
  aboutBody: "\u672c\u5730\u684c\u9762\u5ba2\u6237\u7aef\uff0c\u524d\u7aef\u8d1f\u8d23\u4ea4\u4e92\uff0c\u540e\u7aef\u7531\u672c\u5730 OctoCoder \u670d\u52a1\u63d0\u4f9b\u6267\u884c\u80fd\u529b\u3002",
  voiceSettings: "\u8bed\u97f3 Agent",
  enableVoice: "\u542f\u7528\u8bed\u97f3",
  autoSubmitVoice: "\u8f6c\u5199\u540e\u81ea\u52a8\u63d0\u4ea4",
  startRecording: "\u5f00\u59cb\u5f55\u97f3",
  stopRecording: "\u505c\u6b62\u5f55\u97f3\u5e76\u8f6c\u5199",
  cancelRecording: "\u53d6\u6d88\u5f55\u97f3",
  stopPlayback: "\u505c\u6b62\u8bed\u97f3\u64ad\u653e",
  requestingMicrophone: "\u6b63\u5728\u8bf7\u6c42\u9ea6\u514b\u98ce\u6743\u9650",
  recording: "\u5f55\u97f3\u4e2d",
  transcribing: "\u6b63\u5728\u8f6c\u5199",
  speaking: "\u6b63\u5728\u64ad\u653e",
  voiceUnavailable: "\u8bf7\u5148\u5728\u8bbe\u7f6e\u4e2d\u914d\u7f6e\u8bed\u97f3",
};

const SIDEBAR_WIDTH_KEY = "octocoder:sidebarWidth";
const SIDEBAR_DEFAULT_WIDTH = 286;
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 420;

const VOICE_PROVIDER_PRESETS: Record<VoiceProviderId, {
  label: string;
  baseUrl: string;
  streamingUrl: string;
  sttModel: string;
  streamingSttModel: string;
  ttsModel: string;
  voice: string;
}> = {
  siliconflow: {
    label: "\u7845\u57fa\u6d41\u52a8 SiliconFlow",
    baseUrl: "https://api.siliconflow.cn/v1",
    streamingUrl: "",
    sttModel: "FunAudioLLM/SenseVoiceSmall",
    streamingSttModel: "",
    ttsModel: "FunAudioLLM/CosyVoice2-0.5B",
    voice: "FunAudioLLM/CosyVoice2-0.5B:anna"
  },
  aliyun: {
    label: "\u963f\u91cc\u4e91\u767e\u70bc",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    streamingUrl: "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
    sttModel: "qwen3-asr-flash",
    streamingSttModel: "qwen-audio-3.0-asr-flash-streaming",
    ttsModel: "qwen-audio-3.0-tts-flash",
    voice: "longanhuan_v3.6"
  },
  volcengine: {
    label: "\u706b\u5c71\u5f15\u64ce\u8c46\u5305\u8bed\u97f3",
    baseUrl: "https://openspeech.bytedance.com",
    streamingUrl: "",
    sttModel: "volc.bigasr.auc_turbo",
    streamingSttModel: "",
    ttsModel: "seed-tts-1.1",
    voice: "zh_female_cancan_mars_bigtts"
  },
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    streamingUrl: "",
    sttModel: "gpt-4o-mini-transcribe",
    streamingSttModel: "",
    ttsModel: "tts-1",
    voice: "alloy"
  },
  "openai-compatible": {
    label: "\u81ea\u5b9a\u4e49 OpenAI-compatible",
    baseUrl: "https://api.openai.com/v1",
    streamingUrl: "",
    sttModel: "gpt-4o-mini-transcribe",
    streamingSttModel: "",
    ttsModel: "tts-1",
    voice: "alloy"
  }
};

function editableVoiceProfiles(voice: VoiceSettings | undefined): VoiceProviderSavePayload[] {
  if (voice?.profiles?.length) {
    return voice.profiles.map((profile) => ({
      id: profile.id,
      name: profile.name,
      provider: profile.provider,
      baseUrl: profile.baseUrl,
      streamingUrl: profile.streamingUrl,
      workspaceId: profile.workspaceId,
      apiKey: "",
      appId: "",
      secretKey: "",
      batchSttModel: profile.batchSttModel,
      streamingSttModel: profile.streamingSttModel,
      ttsModel: profile.ttsModel,
      voice: profile.voice,
      language: profile.language
    }));
  }
  const provider = voice?.provider || "aliyun";
  const preset = VOICE_PROVIDER_PRESETS[provider];
  return [{
    id: "default",
    name: "Default",
    provider,
    baseUrl: voice?.baseUrl || preset.baseUrl,
    streamingUrl: preset.streamingUrl,
    workspaceId: "",
    apiKey: "",
    appId: "",
    secretKey: "",
    batchSttModel: voice?.sttModel || preset.sttModel,
    streamingSttModel: preset.streamingSttModel,
    ttsModel: voice?.ttsModel || preset.ttsModel,
    voice: voice?.voice || preset.voice,
    language: voice?.language || ""
  }];
}

function clampSidebarWidth(value: number): number {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(value)));
}

function readSidebarWidth(): number {
  try {
    const stored = Number(window.localStorage.getItem(SIDEBAR_WIDTH_KEY));
    return Number.isFinite(stored) ? clampSidebarWidth(stored) : SIDEBAR_DEFAULT_WIDTH;
  } catch {
    return SIDEBAR_DEFAULT_WIDTH;
  }
}

type ProjectSelectResult =
  | { canceled: true; projects: ProjectInfo[] }
  | { canceled: false; project: ProjectInfo; projects: ProjectInfo[] };

type DesktopEditCommand = "undo" | "redo" | "cut" | "copy" | "paste" | "selectAll";
type DesktopWindowAction = "quit" | "reload" | "toggleFullscreen" | "toggleDevTools" | "zoomIn" | "zoomOut" | "zoomReset";
type DesktopHelpDialog = "quickStart" | "about";
type WindowResizeDirection = "n" | "s" | "e" | "w" | "nw" | "ne" | "sw" | "se";

type DesktopAppInfo = {
  name: string;
  version: string;
  electron: string;
  chrome: string;
  node: string;
  platform: string;
  arch: string;
  userData: string;
  logsDir: string;
  backendPort: number;
  backendPid: number | null;
};

type DiagnosticsClientState = {
  generatedAt: string;
  connection: ConnectionState;
  cwd: string;
  workspace: ProjectInfo | null;
  projects: ProjectInfo[];
  config: ConfigStatus | null;
  model: string;
  timelineItems: number;
  streaming: boolean;
  voice: {
    supported: boolean;
    enabled: boolean;
    configured: boolean;
    phase: VoicePhase;
  };
};

type MenuSeparator = { type: "separator"; id: string };
type MenuCommand = {
  id: string;
  label: string;
  shortcut?: string;
  disabled?: boolean;
  title?: string;
  action?: () => void | Promise<void>;
};
type MenuEntry = MenuSeparator | MenuCommand;
type MenuGroup = {
  id: "file" | "edit" | "view" | "help";
  label: string;
  items: MenuEntry[];
};

declare global {
  interface Window {
    octocoderDesktop?: {
      isDesktop: boolean;
      platform: string;
      arch: string;
      selectProject?: () => Promise<ProjectSelectResult>;
      getProjects?: () => Promise<ProjectInfo[]>;
      rememberProject?: (projectPath: string) => Promise<ProjectInfo>;
      removeProject?: (projectPath: string) => Promise<ProjectInfo[]>;
      edit?: (command: DesktopEditCommand) => Promise<void>;
      copyText?: (text: string) => Promise<void>;
      windowAction?: (action: DesktopWindowAction) => Promise<void>;
      openLogsFolder?: () => Promise<{ path: string }>;
      exportDiagnostics?: (state: DiagnosticsClientState) => Promise<{ canceled: boolean; filePath?: string }>;
      getAppInfo?: () => Promise<DesktopAppInfo>;
      resizeWindowStart?: (direction: WindowResizeDirection) => Promise<void>;
      resizeWindowMove?: (deltaX: number, deltaY: number) => Promise<void>;
      resizeWindowEnd?: () => Promise<void>;
    };
  }
}

type AppState = {
  connection: ConnectionState;
  session: string;
  cwd: string;
  workspace: ProjectInfo | null;
  commands: CommandInfo[];
  projects: ProjectInfo[];
  timeline: TimelineItem[];
  streaming: boolean;
  usage: Usage;
  selectedId: string | null;
  config: ConfigStatus | null;
};

type AppAction =
  | { type: "socket_open" }
  | { type: "socket_close" }
  | { type: "select"; id: string | null }
  | { type: "new_task" }
  | { type: "default_chat" }
  | { type: "send_user"; content: string }
  | { type: "server"; message: ServerMessage }
  | { type: "notice"; kind: "system" | "error" | "done"; content: string }
  | { type: "projects_loaded"; projects: ProjectInfo[] }
  | { type: "project_removed"; path: string; projects: ProjectInfo[] }
  | { type: "permission_status"; permissionId: string; status: "allow" | "allowAlways" | "deny" };

const initialState: AppState = {
  connection: "connecting",
  session: "",
  cwd: "",
  workspace: null,
  commands: [],
  projects: [],
  timeline: [],
  streaming: false,
  usage: { inputTokens: 0, outputTokens: 0 },
  selectedId: null,
  config: null
};

function lastItem<TValue>(items: TValue[]): TValue | undefined {
  return items.length ? items[items.length - 1] : undefined;
}

function appendItem(state: AppState, item: TimelineItem): AppState {
  return { ...state, timeline: [...state.timeline, item], selectedId: state.selectedId || item.id };
}

function normalizePath(value: string): string {
  const normalized = value.replace(/[\\/]+$/, "");
  return window.octocoderDesktop?.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function samePath(a: string, b: string): boolean {
  return Boolean(a && b && normalizePath(a) === normalizePath(b));
}

function projectNameFromPath(projectPath: string): string {
  const parts = projectPath.split(/[\\/]/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : projectPath || T.appName;
}

function mergeProjects(projects: ProjectInfo[], project: ProjectInfo): ProjectInfo[] {
  return [project, ...projects.filter((item) => !samePath(item.path, project.path))];
}

function updateLastAssistant(state: AppState, text: string, streaming: boolean): AppState {
  const items = [...state.timeline];
  const last = lastItem(items);
  if (last?.type === "assistant" && last.streaming) {
    items[items.length - 1] = { ...last, content: last.content + text, streaming };
    return { ...state, timeline: items };
  }
  return appendItem(state, {
    id: makeId("assistant"),
    type: "assistant",
    content: text,
    streaming,
    createdAt: Date.now()
  });
}

function finalizeAssistant(state: AppState): AppState {
  const timeline = state.timeline.map((item) =>
    item.type === "assistant" && item.streaming ? { ...item, streaming: false } : item
  );
  return { ...state, timeline };
}

function updateLastThinking(state: AppState, text: string): AppState {
  const items = [...state.timeline];
  const last = lastItem(items);
  if (last?.type === "thinking") {
    items[items.length - 1] = { ...last, content: last.content + text };
    return { ...state, timeline: items };
  }
  return appendItem(state, {
    id: makeId("thinking"),
    type: "thinking",
    content: text,
    createdAt: Date.now()
  });
}

function reduceServerMessage(state: AppState, message: ServerMessage): AppState {
  switch (message.type) {
    case "connected":
      return {
        ...state,
        connection: "connected",
        session: message.data.session,
        cwd: message.data.cwd
      };
    case "project_opened": {
      const project = {
        name: message.data.name,
        path: message.data.path,
        lastOpened: Date.now()
      };
      return {
        ...state,
        session: message.data.session,
        cwd: message.data.path,
        workspace: project,
        streaming: false,
        selectedId: null,
        timeline: [],
        projects: mergeProjects(state.projects, project)
      };
    }
    case "commands":
      return { ...state, commands: message.data || [] };
    case "config_status":
      return { ...state, config: message.data, cwd: message.data.cwd || state.cwd };
    case "system":
      return appendItem(state, {
        id: makeId("system"),
        type: "system",
        content: message.data.message,
        createdAt: Date.now()
      });
    case "clear":
      return { ...state, timeline: [], selectedId: null, streaming: false };
    case "command_done":
      return { ...state, streaming: false };
    case "replay_user":
      return appendItem(state, {
        id: makeId("user"),
        type: "user",
        content: message.data.content,
        createdAt: Date.now()
      });
    case "replay_assistant":
      return appendItem(state, {
        id: makeId("assistant"),
        type: "assistant",
        content: message.data.content,
        streaming: false,
        createdAt: Date.now()
      });
    case "stream_text":
      return updateLastAssistant(state, message.data.text, true);
    case "stream_end":
      return finalizeAssistant(state);
    case "thinking_text":
      return updateLastThinking(state, message.data.text);
    case "tool_use":
      return appendItem(state, {
        id: makeId("tool"),
        type: "tool",
        toolId: message.data.toolId,
        toolName: message.data.toolName,
        args: message.data.args,
        output: "",
        status: "running",
        createdAt: Date.now()
      });
    case "tool_result": {
      const timeline = state.timeline.map((item) => {
        if (item.type !== "tool") return item;
        const sameId = item.toolId && item.toolId === message.data.toolId;
        const fallback = !item.toolId && item.toolName === message.data.toolName && item.status === "running";
        if (!sameId && !fallback) return item;
        return {
          ...item,
          output: message.data.output || "",
          elapsed: message.data.elapsed,
          status: message.data.isError ? ("error" as ToolStatus) : ("ok" as ToolStatus)
        };
      });
      return { ...state, timeline };
    }
    case "permission_request":
      return appendItem(state, {
        id: makeId("permission"),
        type: "permission",
        permissionId: message.data.id,
        toolName: message.data.toolName,
        description: message.data.description,
        status: "pending",
        createdAt: Date.now()
      });
    case "loop_complete":
      return appendItem(
        { ...finalizeAssistant(state), streaming: false },
        {
          id: makeId("done"),
          type: "done",
          content: `Done in ${message.data.elapsed.toFixed(1)}s across ${message.data.totalTurns} turn(s).`,
          createdAt: Date.now()
        }
      );
    case "usage":
      return { ...state, usage: message.data };
    case "error":
      return appendItem(
        { ...state, streaming: false },
        {
          id: makeId("error"),
          type: "error",
          content: message.data.message,
          createdAt: Date.now()
        }
      );
    case "compact":
      return appendItem(state, {
        id: makeId("compact"),
        type: "compact",
        content: message.data.message,
        createdAt: Date.now()
      });
    case "retry":
      return appendItem(state, {
        id: makeId("retry"),
        type: "retry",
        content: `${message.data.reason} (${Math.round(message.data.waitMs / 1000)}s)`,
        createdAt: Date.now()
      });
    case "turn_complete":
    case "pong":
      return state;
    default:
      return state;
  }
}

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "socket_open":
      return { ...state, connection: "connected" };
    case "socket_close":
      return { ...state, connection: state.connection === "connected" ? "reconnecting" : "disconnected" };
    case "select":
      return { ...state, selectedId: action.id };
    case "new_task":
      return { ...state, timeline: [], selectedId: null, streaming: false };
    case "default_chat":
      return { ...state, workspace: null, timeline: [], selectedId: null, streaming: false };
    case "send_user":
      return appendItem(
        { ...state, streaming: true },
        {
          id: makeId("user"),
          type: "user",
          content: action.content,
          createdAt: Date.now()
        }
      );
    case "server":
      return reduceServerMessage(state, action.message);
    case "notice":
      return appendItem(state, {
        id: makeId(action.kind),
        type: action.kind,
        content: action.content,
        createdAt: Date.now()
      });
    case "projects_loaded":
      return { ...state, projects: action.projects };
    case "project_removed": {
      const removingActive = Boolean(state.workspace && samePath(state.workspace.path, action.path));
      return {
        ...state,
        projects: action.projects,
        workspace: removingActive ? null : state.workspace,
        timeline: removingActive ? [] : state.timeline,
        selectedId: removingActive ? null : state.selectedId,
        streaming: removingActive ? false : state.streaming
      };
    }
    case "permission_status":
      return {
        ...state,
        timeline: state.timeline.map((item) =>
          item.type === "permission" && item.permissionId === action.permissionId
            ? { ...item, status: action.status }
            : item
        )
      };
    default:
      return state;
  }
}

export function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [input, setInput] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(readSidebarWidth);
  const [helpDialog, setHelpDialog] = useState<DesktopHelpDialog | null>(null);
  const [appInfo, setAppInfo] = useState<DesktopAppInfo | null>(null);
  const socketRef = useRef<OctoCoderSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const voice = useVoiceAgent({
    socketRef,
    config: state.config?.voice || null,
    agentBusy: state.streaming,
    onTranscript: (text) => {
      setInput(text);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    },
    onAutoSubmitted: (text) => dispatch({ type: "send_user", content: text }),
    onError: (message) => dispatch({ type: "notice", kind: "error", content: message })
  });
  const voiceHandlersRef = useRef({
    onMessage: voice.handleServerMessage,
    onAudio: voice.handleVoiceAudio,
    onDisconnect: voice.handleDisconnect
  });
  voiceHandlersRef.current = {
    onMessage: voice.handleServerMessage,
    onAudio: voice.handleVoiceAudio,
    onDisconnect: voice.handleDisconnect
  };

  useEffect(() => {
    const socket = new OctoCoderSocket({
      onOpen: () => {
        dispatch({ type: "socket_open" });
        socket.send({ type: "config_get", data: {} });
      },
      onClose: () => {
        voiceHandlersRef.current.onDisconnect();
        dispatch({ type: "socket_close" });
      },
      onMessage: (message) => {
        voiceHandlersRef.current.onMessage(message);
        dispatch({ type: "server", message });
      },
      onVoiceAudio: (metadata, data) => voiceHandlersRef.current.onAudio(metadata, data)
    });
    socketRef.current = socket;
    socket.connect();
    return () => socket.disconnect();
  }, []);

  useEffect(() => {
    window.octocoderDesktop?.getProjects?.()
      .then((projects) => dispatch({ type: "projects_loaded", projects }))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    window.octocoderDesktop?.getAppInfo?.()
      .then((info) => setAppInfo(info))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
    } catch {
      // localStorage may be unavailable in restricted contexts.
    }
  }, [sidebarWidth]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [state.timeline]);

  useEffect(() => {
    if (state.config && !state.config.ready) {
      setSettingsOpen(true);
    }
  }, [state.config]);

  const selected = useMemo(() => {
    return state.timeline.find((item) => item.id === state.selectedId) || lastItem(state.timeline) || null;
  }, [state.timeline, state.selectedId]);

  const startNewTask = () => {
    voice.handleDisconnect();
    dispatch({ type: "new_task" });
    setInput("");
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const focusChat = () => {
    if (state.workspace) {
      socketRef.current?.send({ type: "project_clear", data: {} });
    }
    dispatch({ type: "default_chat" });
    voice.handleDisconnect();
    setInput("");
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const sendMessage = () => {
    const content = input.trim();
    if (!content || state.streaming || !state.config?.ready) return;
    const voiceRequestId = voice.pendingTranscriptRequestId;
    const sent = socketRef.current?.send({
      type: "user_message",
      data: {
        content,
        source: voiceRequestId ? "voice" : "text",
        voiceRequestId: voiceRequestId || undefined
      }
    });
    if (!sent) return;
    if (voiceRequestId) voice.markTranscriptSubmitted();
    dispatch({ type: "send_user", content });
    setInput("");
  };

  const openProject = async (project: ProjectInfo) => {
    if (state.streaming) return;
    try {
      const saved = await window.octocoderDesktop?.rememberProject?.(project.path);
      if (saved) {
        dispatch({ type: "projects_loaded", projects: mergeProjects(state.projects, saved) });
      }
    } catch {
      // The backend will return the useful validation error.
    }
    socketRef.current?.send({ type: "project_open", data: { path: project.path } });
  };

  const openProjectPicker = async () => {
    if (state.streaming) return;
    const desktop = window.octocoderDesktop;
    if (!desktop?.selectProject) {
      dispatch({
        type: "server",
        message: {
          type: "error",
          data: { message: "Project picker is only available in the OctoCoder desktop app." }
        }
      });
      return;
    }

    try {
      const result = await desktop.selectProject();
      dispatch({ type: "projects_loaded", projects: result.projects });
      if (!result.canceled) {
        socketRef.current?.send({ type: "project_open", data: { path: result.project.path } });
      }
    } catch (error) {
      dispatch({
        type: "server",
        message: {
          type: "error",
          data: { message: error instanceof Error ? error.message : String(error) }
        }
      });
    }
  };

  const removeProject = async (project: ProjectInfo) => {
    if (state.streaming) return;
    const fallback = state.projects.filter((item) => !samePath(item.path, project.path));
    let projects = fallback;
    try {
      projects = await window.octocoderDesktop?.removeProject?.(project.path) ?? fallback;
    } catch {
      projects = fallback;
    }
    dispatch({ type: "project_removed", path: project.path, projects });
    if (state.workspace && samePath(state.workspace.path, project.path)) {
      socketRef.current?.send({ type: "project_clear", data: {} });
    }
  };

  const sendPermission = (id: string, response: "allow" | "allowAlways" | "deny") => {
    const message: ClientMessage = { type: "permission_response", data: { id, response } };
    socketRef.current?.send(message);
    dispatch({ type: "permission_status", permissionId: id, status: response });
  };

  const cancel = () => {
    socketRef.current?.send({ type: "cancel", data: {} });
  };

  const saveConfig = (payload: ConfigSavePayload) => {
    socketRef.current?.send({ type: "config_save", data: payload });
  };

  const runEditCommand = async (command: DesktopEditCommand) => {
    try {
      if (window.octocoderDesktop?.edit) {
        await window.octocoderDesktop.edit(command);
        return;
      }
      document.execCommand(command);
    } catch (error) {
      dispatch({ type: "notice", kind: "error", content: `${T.actionFailed}: ${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const runWindowAction = async (action: DesktopWindowAction) => {
    try {
      if (window.octocoderDesktop?.windowAction) {
        await window.octocoderDesktop.windowAction(action);
        return;
      }
      if (action === "reload") window.location.reload();
      if (action === "quit") window.close();
    } catch (error) {
      dispatch({ type: "notice", kind: "error", content: `${T.actionFailed}: ${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const clearInput = () => {
    voice.discardTranscriptOrigin();
    setInput("");
    window.setTimeout(() => inputRef.current?.focus(), 0);
  };

  const clearConversation = () => {
    if (state.streaming) return;
    socketRef.current?.send({ type: "user_message", data: { content: "/clear" } });
    dispatch({ type: "server", message: { type: "clear", data: null } });
  };

  const copyLastReply = async () => {
    const reply = [...state.timeline]
      .reverse()
      .find((item) => item.type === "assistant" && item.content.trim());
    if (!reply || reply.type !== "assistant") {
      dispatch({ type: "notice", kind: "system", content: T.noAssistantReply });
      return;
    }
    try {
      if (window.octocoderDesktop?.copyText) {
        await window.octocoderDesktop.copyText(reply.content);
      } else {
        await navigator.clipboard.writeText(reply.content);
      }
      dispatch({ type: "notice", kind: "done", content: T.copiedLastReply });
    } catch (error) {
      dispatch({ type: "notice", kind: "error", content: `${T.actionFailed}: ${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const checkConfig = () => {
    dispatch({ type: "notice", kind: "system", content: T.checkingConfig });
    socketRef.current?.send({ type: "config_get", data: {} });
    setSettingsOpen(true);
  };

  const openLogsFolder = async () => {
    try {
      const result = await window.octocoderDesktop?.openLogsFolder?.();
      dispatch({ type: "notice", kind: "done", content: result?.path ? `${T.logsOpened} ${result.path}` : T.logsOpened });
    } catch (error) {
      dispatch({ type: "notice", kind: "error", content: `${T.actionFailed}: ${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const exportDiagnostics = async () => {
    try {
      const result = await window.octocoderDesktop?.exportDiagnostics?.({
        generatedAt: new Date().toISOString(),
        connection: state.connection,
        cwd: state.cwd,
        workspace: state.workspace,
        projects: state.projects,
        config: state.config,
        model: state.config?.provider?.model || T.modelNotConfigured,
        timelineItems: state.timeline.length,
        streaming: state.streaming,
        voice: {
          supported: voice.supported,
          enabled: Boolean(state.config?.voice?.enabled),
          configured: Boolean(state.config?.voice?.configured),
          phase: voice.phase
        }
      });
      if (result && !result.canceled && result.filePath) {
        dispatch({ type: "notice", kind: "done", content: `${T.diagnosticsExported}: ${result.filePath}` });
      }
    } catch (error) {
      dispatch({ type: "notice", kind: "error", content: `${T.actionFailed}: ${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const menus: MenuGroup[] = [
    {
      id: "file",
      label: T.fileMenu,
      items: [
        { id: "file.newTask", label: T.newTask, shortcut: "Ctrl+N", action: startNewTask },
        { id: "file.openProject", label: T.openProjectFolder, shortcut: "Ctrl+O", disabled: state.streaming, action: openProjectPicker },
        { type: "separator", id: "file.sep.recent" },
        { id: "file.recent.label", label: T.recentProjects, disabled: true },
        ...(state.projects.length
          ? state.projects.slice(0, 8).map((project): MenuCommand => ({
              id: `file.recent.${project.path}`,
              label: project.name,
              title: project.path,
              disabled: state.streaming,
              action: () => openProject(project)
            }))
          : [{ id: "file.recent.empty", label: T.noRecentProjects, disabled: true } as MenuCommand]),
        { type: "separator", id: "file.sep.workspace" },
        { id: "file.defaultChat", label: T.defaultChat, disabled: state.streaming, action: focusChat },
        { id: "file.settings", label: T.settings, shortcut: "Ctrl+,", action: () => setSettingsOpen(true) },
        { type: "separator", id: "file.sep.quit" },
        { id: "file.quit", label: T.quit, action: () => void runWindowAction("quit") }
      ]
    },
    {
      id: "edit",
      label: T.editMenu,
      items: [
        { id: "edit.undo", label: T.undo, shortcut: "Ctrl+Z", action: () => void runEditCommand("undo") },
        { id: "edit.redo", label: T.redo, shortcut: "Ctrl+Y", action: () => void runEditCommand("redo") },
        { type: "separator", id: "edit.sep.clipboard" },
        { id: "edit.cut", label: T.cut, shortcut: "Ctrl+X", action: () => void runEditCommand("cut") },
        { id: "edit.copy", label: T.copy, shortcut: "Ctrl+C", action: () => void runEditCommand("copy") },
        { id: "edit.paste", label: T.paste, shortcut: "Ctrl+V", action: () => void runEditCommand("paste") },
        { id: "edit.selectAll", label: T.selectAll, shortcut: "Ctrl+A", action: () => void runEditCommand("selectAll") },
        { type: "separator", id: "edit.sep.octocoder" },
        { id: "edit.copyLastReply", label: T.copyLastReply, shortcut: "Ctrl+Shift+C", action: () => void copyLastReply() },
        { id: "edit.clearInput", label: T.clearInput, action: clearInput },
        { id: "edit.clearConversation", label: T.clearConversation, disabled: state.streaming, action: clearConversation }
      ]
    },
    {
      id: "view",
      label: T.viewMenu,
      items: [
        { id: "view.sidebar", label: T.toggleSidebar, shortcut: "Ctrl+B", action: () => setSidebarCollapsed((value) => !value) },
        { type: "separator", id: "view.sep.zoom" },
        { id: "view.zoomIn", label: T.zoomIn, shortcut: "Ctrl++", action: () => void runWindowAction("zoomIn") },
        { id: "view.zoomOut", label: T.zoomOut, shortcut: "Ctrl+-", action: () => void runWindowAction("zoomOut") },
        { id: "view.zoomReset", label: T.zoomReset, shortcut: "Ctrl+0", action: () => void runWindowAction("zoomReset") },
        { type: "separator", id: "view.sep.window" },
        { id: "view.fullscreen", label: T.fullscreen, shortcut: "F11", action: () => void runWindowAction("toggleFullscreen") },
        { id: "view.reload", label: T.reloadUi, shortcut: "Ctrl+R", action: () => void runWindowAction("reload") },
        { id: "view.devTools", label: T.devTools, shortcut: "Ctrl+Shift+I", action: () => void runWindowAction("toggleDevTools") }
      ]
    },
    {
      id: "help",
      label: T.helpMenu,
      items: [
        { id: "help.quickStart", label: T.quickStart, action: () => setHelpDialog("quickStart") },
        { id: "help.checkConfig", label: T.checkConfig, action: checkConfig },
        { type: "separator", id: "help.sep.diagnostics" },
        { id: "help.openLogs", label: T.openLogsFolder, action: () => void openLogsFolder() },
        { id: "help.exportDiagnostics", label: T.exportDiagnostics, action: () => void exportDiagnostics() },
        { type: "separator", id: "help.sep.about" },
        { id: "help.about", label: T.about, action: () => setHelpDialog("about") }
      ]
    }
  ];

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const mod = event.ctrlKey || event.metaKey;
      if (!mod && event.key === "F11") {
        event.preventDefault();
        void runWindowAction("toggleFullscreen");
        return;
      }
      if (!mod) return;
      if (key === "n") {
        event.preventDefault();
        startNewTask();
      } else if (key === "o") {
        event.preventDefault();
        void openProjectPicker();
      } else if (key === "b") {
        event.preventDefault();
        setSidebarCollapsed((value) => !value);
      } else if (event.key === ",") {
        event.preventDefault();
        setSettingsOpen(true);
      } else if (key === "=" || event.key === "+") {
        event.preventDefault();
        void runWindowAction("zoomIn");
      } else if (key === "-") {
        event.preventDefault();
        void runWindowAction("zoomOut");
      } else if (key === "0") {
        event.preventDefault();
        void runWindowAction("zoomReset");
      } else if (key === "r") {
        event.preventDefault();
        void runWindowAction("reload");
      } else if (event.shiftKey && key === "i") {
        event.preventDefault();
        void runWindowAction("toggleDevTools");
      } else if (event.shiftKey && key === "c") {
        event.preventDefault();
        void copyLastReply();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  return (
    <div className={`app-frame ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
      <WindowResizeHandles />
      <AppChrome
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
        menus={menus}
      />
      <div
        className={`app-shell ${sidebarCollapsed ? "collapsed" : ""}`}
        style={sidebarCollapsed ? undefined : { gridTemplateColumns: `${sidebarWidth}px 5px minmax(640px, 1fr)` }}
      >
        {!sidebarCollapsed && (
          <Sidebar
            state={state}
            onNewTask={startNewTask}
            onChat={focusChat}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenProject={openProject}
            onRemoveProject={removeProject}
            onPickProject={openProjectPicker}
          />
        )}
        {!sidebarCollapsed && <SidebarResizeHandle width={sidebarWidth} onResize={setSidebarWidth} />}
        <main className="workspace">
          <TopBar state={state} onOpenSettings={() => setSettingsOpen(true)} />
          <section className="timeline" aria-label="Conversation timeline">
            {state.timeline.length === 0 ? (
              <EmptyState
                workspace={state.workspace}
                ready={Boolean(state.config?.ready)}
                onOpenSettings={() => setSettingsOpen(true)}
                onPickProject={openProjectPicker}
              />
            ) : (
              state.timeline.map((item) => (
                <TimelineCard
                  key={item.id}
                  item={item}
                  selected={item.id === selected?.id}
                  onSelect={() => dispatch({ type: "select", id: item.id })}
                  onPermission={sendPermission}
                />
              ))
            )}
            <div ref={bottomRef} />
          </section>
          <Composer
            inputRef={inputRef}
            value={input}
            model={state.config?.provider?.model || T.modelNotConfigured}
            disabled={state.streaming || state.connection !== "connected" || !state.config?.ready}
            streaming={state.streaming}
            voicePhase={voice.phase}
            voiceCaption={voice.caption}
            voiceElapsed={voice.elapsedSeconds}
            voiceMode={state.config?.voice?.mode || "hold"}
            continuousEnabled={voice.continuousEnabled}
            voiceAvailable={Boolean(
              voice.supported &&
              state.config?.voice?.enabled &&
              state.config.voice.streamingConfigured &&
              state.connection === "connected" &&
              (state.config.voice.mode === "continuous" || !state.streaming)
            )}
            onChange={setInput}
            onSubmit={sendMessage}
            onCancel={cancel}
            onStartRecording={() => void voice.startRecording()}
            onStopRecording={() => void voice.stopRecording()}
            onCancelRecording={voice.cancelRecording}
            onToggleContinuous={voice.toggleContinuous}
            onStopPlayback={voice.stopPlayback}
          />
        </main>
      </div>
      {settingsOpen && (
        <SettingsDialog config={state.config} onClose={() => setSettingsOpen(false)} onSave={saveConfig} />
      )}
      {helpDialog && (
        <HelpDialog kind={helpDialog} appInfo={appInfo} onClose={() => setHelpDialog(null)} />
      )}
    </div>
  );
}

function WindowResizeHandles() {
  const sessionRef = useRef<{ pointerId: number; startX: number; startY: number } | null>(null);
  const directions: WindowResizeDirection[] = ["n", "s", "e", "w", "nw", "ne", "sw", "se"];

  const startResize = (direction: WindowResizeDirection, event: ReactPointerEvent<HTMLDivElement>) => {
    if (!window.octocoderDesktop?.resizeWindowStart) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    sessionRef.current = {
      pointerId: event.pointerId,
      startX: event.screenX,
      startY: event.screenY
    };
    void window.octocoderDesktop.resizeWindowStart(direction);
  };

  const moveResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const session = sessionRef.current;
    if (!session || session.pointerId !== event.pointerId) return;
    event.preventDefault();
    void window.octocoderDesktop?.resizeWindowMove?.(
      event.screenX - session.startX,
      event.screenY - session.startY
    );
  };

  const endResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const session = sessionRef.current;
    if (!session || session.pointerId !== event.pointerId) return;
    event.preventDefault();
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture may already be released when the OS takes over.
    }
    sessionRef.current = null;
    void window.octocoderDesktop?.resizeWindowEnd?.();
  };

  return (
    <>
      {directions.map((direction) => (
        <div
          className={`window-resize-handle ${direction}`}
          key={direction}
          onPointerDown={(event) => startResize(direction, event)}
          onPointerMove={moveResize}
          onPointerUp={endResize}
          onPointerCancel={endResize}
        />
      ))}
    </>
  );
}

function SidebarResizeHandle({
  width,
  onResize
}: {
  width: number;
  onResize: (width: number) => void;
}) {
  const dragRef = useRef<{ pointerId: number; startX: number; startWidth: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.screenX,
      startWidth: width
    };
    setDragging(true);
  };

  const moveDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    onResize(clampSidebarWidth(drag.startWidth + event.screenX - drag.startX));
  };

  const endDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Pointer capture can already be gone after rapid window interactions.
    }
    dragRef.current = null;
    setDragging(false);
  };

  return (
    <div
      className={`sidebar-resize-handle ${dragging ? "dragging" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-valuemin={SIDEBAR_MIN_WIDTH}
      aria-valuemax={SIDEBAR_MAX_WIDTH}
      aria-valuenow={width}
      tabIndex={0}
      onPointerDown={startDrag}
      onPointerMove={moveDrag}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          onResize(clampSidebarWidth(width - 12));
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          onResize(clampSidebarWidth(width + 12));
        }
      }}
    />
  );
}

function AppChrome({
  sidebarCollapsed,
  onToggleSidebar,
  menus
}: {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  menus: MenuGroup[];
}) {
  const [openMenu, setOpenMenu] = useState<MenuGroup["id"] | null>(null);
  const chromeRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const close = (event: PointerEvent) => {
      if (chromeRef.current && !chromeRef.current.contains(event.target as Node)) {
        setOpenMenu(null);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenu(null);
    };
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return (
    <header ref={chromeRef} className="app-chrome" aria-label="Application chrome">
      <div className="app-chrome-actions">
        <button
          className={`app-chrome-button ${sidebarCollapsed ? "active" : ""}`}
          type="button"
          aria-pressed={sidebarCollapsed}
          title={T.toggleSidebar}
          onClick={onToggleSidebar}
        >
          <PanelLeft size={16} />
        </button>
        <button className="app-chrome-button muted" type="button" title={T.back} disabled>
          <ArrowLeft size={17} />
        </button>
        <button className="app-chrome-button muted" type="button" title={T.forward} disabled>
          <ArrowRight size={17} />
        </button>
      </div>
      <nav className="app-menu-labels" aria-label="Application menu">
        {menus.map((menu) => (
          <div className="app-menu-root" key={menu.id}>
            <button
              className={`app-menu-trigger ${openMenu === menu.id ? "active" : ""}`}
              type="button"
              onClick={() => setOpenMenu((current) => (current === menu.id ? null : menu.id))}
            >
              {menu.label}
            </button>
            {openMenu === menu.id && (
              <div className="app-menu-popover" role="menu">
                {menu.items.map((item) => {
                  if ("type" in item) {
                    return <div className="app-menu-separator" key={item.id} role="separator" />;
                  }
                  return (
                    <button
                      className="app-menu-item"
                      type="button"
                      role="menuitem"
                      key={item.id}
                      disabled={item.disabled}
                      title={item.title}
                      onClick={() => {
                        if (item.disabled) return;
                        setOpenMenu(null);
                        void item.action?.();
                      }}
                    >
                      <span>{item.label}</span>
                      {item.shortcut && <kbd>{item.shortcut}</kbd>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </nav>
    </header>
  );
}

function Sidebar({
  state,
  onNewTask,
  onChat,
  onOpenSettings,
  onOpenProject,
  onRemoveProject,
  onPickProject
}: {
  state: AppState;
  onNewTask: () => void;
  onChat: () => void;
  onOpenSettings: () => void;
  onOpenProject: (project: ProjectInfo) => void;
  onRemoveProject: (project: ProjectInfo) => void;
  onPickProject: () => void;
}) {
  const activeTitle = state.timeline.find((item) => item.type === "user")?.content || T.startInProject;
  const projects = state.workspace
    ? [state.workspace, ...state.projects.filter((item) => !samePath(item.path, state.workspace?.path || ""))]
    : state.projects;

  return (
    <aside className="sidebar">
      <div className="brand">
        <strong>{T.appName}</strong>
      </div>

      <nav className="side-nav" aria-label="Primary">
        <NavItem icon={<SquarePen size={17} />} label={T.newTask} onClick={onNewTask} />
        <NavItem icon={<MessagesSquare size={17} />} label={T.chat} onClick={onChat} active={!state.workspace} />
      </nav>

      <div className="side-section side-grow">
        <div className="project-section-head">
          <div className="project-section-title">
            <span>{T.project}</span>
            <ChevronDown size={15} />
          </div>
          <button className="chrome-button" type="button" onClick={onPickProject} title={T.chooseProjectFolder}>
            <Plus size={17} />
          </button>
        </div>
        {projects.length ? (
          projects.map((project) => (
            <ProjectGroup
              key={project.path}
              project={project}
              active={Boolean(state.workspace && samePath(project.path, state.workspace.path))}
              activeTitle={state.workspace && samePath(project.path, state.workspace.path) ? activeTitle : T.openProject}
              onOpen={() => onOpenProject(project)}
              onRemove={() => onRemoveProject(project)}
            />
          ))
        ) : (
          <button className="project-empty" type="button" onClick={onPickProject}>
            <Folder size={17} />
            <span>{T.chooseProjectFolder}</span>
          </button>
        )}
      </div>

      <div className="side-footer">
        <div className="user-chip" aria-label="User">
          <CircleUserRound size={19} />
          <span>{T.notSignedIn}</span>
        </div>
        <button className={`download-chip ${state.config?.ready ? "ready" : ""}`} type="button" onClick={onOpenSettings} title={T.settings}>
          <Settings size={15} />
        </button>
      </div>
    </aside>
  );
}

function ProjectGroup({
  project,
  activeTitle,
  active,
  onOpen,
  onRemove
}: {
  project: ProjectInfo;
  activeTitle: string;
  active?: boolean;
  onOpen: () => void;
  onRemove: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="project-group">
      <div className="project-name-row">
        <button className="project-name" type="button" onClick={onOpen} title={project.path}>
          <Folder size={17} />
          <span>{project.name}</span>
        </button>
        <button
          className="project-menu-button"
          type="button"
          title={T.workspaceActions}
          onClick={(event) => {
            event.stopPropagation();
            setMenuOpen((value) => !value);
          }}
        >
          <MoreHorizontal size={16} />
        </button>
        {menuOpen && (
          <div className="project-menu" role="menu">
            <button
              type="button"
              role="menuitem"
              onClick={(event) => {
                event.stopPropagation();
                setMenuOpen(false);
                onRemove();
              }}
            >
              <Trash2 size={15} />
              <span>{T.removeWorkspace}</span>
            </button>
          </div>
        )}
      </div>
      <button className={`project-task ${active ? "active" : ""}`} type="button" onClick={onOpen} title={project.path}>
        <span>{activeTitle}</span>
      </button>
    </div>
  );
}

function NavItem({
  icon,
  label,
  active,
  onClick
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button className={`nav-item ${active ? "active" : ""}`} type="button" onClick={onClick}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function TopBar({ state, onOpenSettings }: { state: AppState; onOpenSettings: () => void }) {
  const title = state.timeline.find((item) => item.type === "user")?.content || (state.workspace ? `${state.workspace.name} ${T.project}` : T.chat);

  return (
    <header className="topbar">
      <div className="topbar-title">
        {state.workspace ? <Folder size={18} /> : <MessagesSquare size={18} />}
        <span title={state.workspace?.path || state.cwd || T.defaultWorkspace}>{title}</span>
      </div>
      <button className="chrome-button framed" type="button" onClick={onOpenSettings} title={T.settings}>
        <Settings size={17} />
      </button>
    </header>
  );
}

function EmptyState({
  workspace,
  ready,
  onOpenSettings,
  onPickProject
}: {
  workspace: ProjectInfo | null;
  ready: boolean;
  onOpenSettings: () => void;
  onPickProject: () => void;
}) {
  return (
    <div className="empty-state">
      <div className="empty-title">{ready ? `${workspace?.name || T.appName} ${T.ready}` : T.settingsRequired}</div>
      <p>{ready ? T.readyHint : T.settingsHint}</p>
      <div className="command-grid">
        <button className="command-chip" type="button" onClick={onPickProject}>
          <Folder size={15} />
          <span>{T.chooseProject}</span>
        </button>
        {!ready && (
          <button className="send-button" type="button" onClick={onOpenSettings}>
            <Settings size={16} />
            {T.settings}
          </button>
        )}
      </div>
    </div>
  );
}

function HelpDialog({
  kind,
  appInfo,
  onClose
}: {
  kind: DesktopHelpDialog;
  appInfo: DesktopAppInfo | null;
  onClose: () => void;
}) {
  const isAbout = kind === "about";

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label={isAbout ? T.about : T.quickStart}>
      <section className="help-dialog">
        <header className="settings-head">
          <div>
            <strong>{isAbout ? T.about : T.quickStartTitle}</strong>
            <span>{isAbout ? appInfo?.version || "0.1.0" : T.appName}</span>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title={T.closeSettings}>
            <X size={17} />
          </button>
        </header>
        <div className="help-body">
          <p>{isAbout ? T.aboutBody : T.quickStartBody}</p>
          {isAbout && appInfo && (
            <dl className="about-grid">
              <dt>Version</dt>
              <dd>{appInfo.version}</dd>
              <dt>Electron</dt>
              <dd>{appInfo.electron}</dd>
              <dt>Chrome</dt>
              <dd>{appInfo.chrome}</dd>
              <dt>Node</dt>
              <dd>{appInfo.node}</dd>
              <dt>Platform</dt>
              <dd>{`${appInfo.platform}-${appInfo.arch}`}</dd>
              <dt>Backend</dt>
              <dd>{appInfo.backendPort ? `127.0.0.1:${appInfo.backendPort}` : "-"}</dd>
              <dt>User Data</dt>
              <dd>{appInfo.userData}</dd>
            </dl>
          )}
        </div>
      </section>
    </div>
  );
}

function TimelineCard({
  item,
  selected,
  onSelect,
  onPermission
}: {
  item: TimelineItem;
  selected: boolean;
  onSelect: () => void;
  onPermission: (id: string, response: "allow" | "allowAlways" | "deny") => void;
}) {
  if (item.type === "user") {
    return (
      <article className={`timeline-card user-card ${selected ? "selected" : ""}`} onClick={onSelect}>
        <div className="card-body preserve">{item.content}</div>
      </article>
    );
  }

  if (item.type === "assistant") {
    return (
      <article className={`timeline-card assistant-card ${selected ? "selected" : ""}`} onClick={onSelect}>
        <div className="card-body preserve">
          {item.content}
          {item.streaming && <span className="caret" />}
        </div>
      </article>
    );
  }

  if (item.type === "thinking") {
    return (
      <details className={`thinking-card ${selected ? "selected" : ""}`} open onClick={onSelect}>
        <summary>
          <ChevronDown size={15} />
          Thinking
        </summary>
        <pre>{item.content}</pre>
      </details>
    );
  }

  if (item.type === "tool") {
    const preview = toolPreview(item.args);
    return (
      <article className={`tool-card ${selected ? "selected" : ""}`} onClick={onSelect}>
        <div className="tool-card-head">
          <div className="tool-name">
            <Hammer size={16} />
            <strong>{item.toolName}</strong>
            {preview && <span>{preview}</span>}
          </div>
          <ToolStatusBadge status={item.status} elapsed={item.elapsed} />
        </div>
        <details>
          <summary>Arguments</summary>
          <pre>{stringifyJson(item.args) || "{}"}</pre>
        </details>
        {item.output && (
          <details open={item.status === "error"}>
            <summary>Output</summary>
            <pre>{item.output}</pre>
          </details>
        )}
      </article>
    );
  }

  if (item.type === "permission") {
    return (
      <article className={`permission-card ${selected ? "selected" : ""}`} onClick={onSelect}>
        <div className="permission-title">
          <KeyRound size={17} />
          <strong>{item.toolName}</strong>
          <span>{item.status}</span>
        </div>
        <p>{item.description}</p>
        {item.status === "pending" && (
          <div className="permission-actions">
            <button type="button" className="primary" onClick={() => onPermission(item.permissionId, "allow")}>
              <Check size={15} />
              Allow
            </button>
            <button type="button" onClick={() => onPermission(item.permissionId, "allowAlways")}>
              Always
            </button>
            <button type="button" className="danger" onClick={() => onPermission(item.permissionId, "deny")}>
              <X size={15} />
              Deny
            </button>
          </div>
        )}
      </article>
    );
  }

  const icon = item.type === "error" ? <AlertTriangle size={16} /> : item.type === "done" ? <Check size={16} /> : <Circle size={12} />;
  return (
    <article className={`notice-card ${item.type} ${selected ? "selected" : ""}`} onClick={onSelect}>
      {icon}
      <span>{item.content}</span>
    </article>
  );
}

function ToolStatusBadge({ status, elapsed }: { status: "running" | "ok" | "error"; elapsed?: number }) {
  if (status === "running") {
    return (
      <span className="status-badge running">
        <Loader2 size={14} />
        Running
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="status-badge error">
        <OctagonX size={14} />
        {formatElapsed(elapsed) || "Error"}
      </span>
    );
  }
  return (
    <span className="status-badge ok">
      <Check size={14} />
      {formatElapsed(elapsed) || "Done"}
    </span>
  );
}

function Composer({
  inputRef,
  value,
  model,
  disabled,
  streaming,
  voicePhase,
  voiceCaption,
  voiceElapsed,
  voiceMode,
  continuousEnabled,
  voiceAvailable,
  onChange,
  onSubmit,
  onCancel,
  onStartRecording,
  onStopRecording,
  onCancelRecording,
  onToggleContinuous,
  onStopPlayback
}: {
  inputRef: RefObject<HTMLTextAreaElement>;
  value: string;
  model: string;
  disabled: boolean;
  streaming: boolean;
  voicePhase: VoicePhase;
  voiceCaption: string;
  voiceElapsed: number;
  voiceMode: "hold" | "continuous";
  continuousEnabled: boolean;
  voiceAvailable: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onCancelRecording: () => void;
  onToggleContinuous: () => void;
  onStopPlayback: () => void;
}) {
  const voiceStatus = voicePhase === "requesting_permission"
    ? T.requestingMicrophone
    : voicePhase === "recording"
      ? `${T.recording} ${Math.floor(voiceElapsed / 60)}:${String(voiceElapsed % 60).padStart(2, "0")}`
      : voicePhase === "transcribing"
        ? T.transcribing
        : voicePhase === "connecting"
          ? "正在连接实时识别"
          : voicePhase === "listening"
            ? "持续聆听中"
            : voicePhase === "queued"
              ? "已排队"
              : voicePhase === "analyzing"
                ? "正在分析"
                : voicePhase === "executing"
                  ? "正在执行"
                  : voicePhase === "waiting_approval"
                    ? "等待审批"
        : voicePhase === "speaking"
          ? T.speaking
          : "";

  return (
    <footer className="composer">
      <textarea
        ref={inputRef}
        value={value}
        disabled={disabled}
        placeholder={disabled ? T.disabledPlaceholder : T.inputPlaceholder}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            onSubmit();
          }
        }}
      />
      {voiceCaption && <div className="voice-caption" aria-live="polite">{voiceCaption}</div>}
      <div className="composer-actions">
        <span className="model-chip" title={model}>
          {model}
          <ChevronDown size={14} />
        </span>
        <div className="composer-right">
          {voiceStatus && <span className={`voice-status ${voicePhase}`}>{voiceStatus}</span>}
          {voicePhase === "speaking" ? (
            <button type="button" className="composer-icon voice-button active" onClick={onStopPlayback} title={T.stopPlayback} aria-label={T.stopPlayback}>
              <VolumeX size={17} />
            </button>
          ) : (
            <>
              <button
                key="voice-trigger"
                type="button"
                className={`composer-icon voice-button ${continuousEnabled ? "continuous" : ""} ${voiceMode === "hold" && (voicePhase === "requesting_permission" || voicePhase === "connecting" || voicePhase === "recording") ? "recording" : ""}`}
                disabled={!voiceAvailable || (voiceMode === "hold"
                  ? !["idle", "error", "requesting_permission", "connecting", "recording"].includes(voicePhase)
                  : voicePhase === "requesting_permission")}
                onClick={voiceMode === "continuous" ? onToggleContinuous : undefined}
                onPointerDown={voiceMode === "hold" ? (event) => {
                  if (event.button !== 0) return;
                  event.preventDefault();
                  event.currentTarget.setPointerCapture(event.pointerId);
                  onStartRecording();
                } : undefined}
                onPointerUp={voiceMode === "hold" ? (event) => {
                  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                    event.currentTarget.releasePointerCapture(event.pointerId);
                  }
                  onStopRecording();
                } : undefined}
                onPointerCancel={voiceMode === "hold" ? onCancelRecording : undefined}
                onKeyDown={voiceMode === "hold" ? (event) => {
                  if ((event.key === " " || event.key === "Enter") && !event.repeat) {
                    event.preventDefault();
                    onStartRecording();
                  }
                } : undefined}
                onKeyUp={voiceMode === "hold" ? (event) => {
                  if (event.key === " " || event.key === "Enter") {
                    event.preventDefault();
                    onStopRecording();
                  }
                } : undefined}
                title={voiceAvailable ? (voiceMode === "hold" ? "按住说话" : continuousEnabled ? "停止连续对话" : "开始连续对话") : T.voiceUnavailable}
                aria-label={voiceAvailable ? (voiceMode === "hold" ? "按住说话" : "切换连续对话") : T.voiceUnavailable}
              >
                {voicePhase === "requesting_permission" || voicePhase === "connecting" ? <Loader2 size={17} /> : continuousEnabled ? <Square size={14} /> : <Mic size={17} />}
              </button>
              {voiceMode === "hold" && (voicePhase === "requesting_permission" || voicePhase === "connecting" || voicePhase === "recording") && (
                <button type="button" className="composer-icon voice-button cancel-voice" onClick={onCancelRecording} title={T.cancelRecording} aria-label={T.cancelRecording}>
                  <X size={15} />
                </button>
              )}
            </>
          )}
          {streaming ? (
            <button type="button" className="round-send stop-button" onClick={onCancel} title={T.cancel} aria-label={T.cancel}>
              <Square size={16} />
            </button>
          ) : (
            <button type="button" className="round-send send-button" disabled={disabled || !value.trim()} onClick={onSubmit} aria-label="Send">
              <Send size={16} />
            </button>
          )}
        </div>
      </div>
    </footer>
  );
}

function SettingsDialog({
  config,
  onClose,
  onSave
}: {
  config: ConfigStatus | null;
  onClose: () => void;
  onSave: (payload: ConfigSavePayload) => void;
}) {
  const provider = config?.provider;
  const initialProfiles = editableVoiceProfiles(config?.voice);
  const initialPrimaryId = config?.voice?.primaryAsrProfile || initialProfiles[0].id;
  const [form, setForm] = useState<ConfigSavePayload>({
    name: provider?.name || "deepseek",
    protocol: provider?.protocol || "openai-compat",
    baseUrl: provider?.baseUrl || "https://api.deepseek.com/v1",
    model: provider?.model || "deepseek-chat",
    apiKey: "",
    thinking: provider?.thinking || false,
    contextWindow: provider?.contextWindow || 0,
    maxOutputTokens: provider?.maxOutputTokens || 0,
    permissionMode: "default",
    voice: {
      provider: config?.voice?.provider || "openai-compatible",
      enabled: config?.voice?.enabled || false,
      baseUrl: config?.voice?.baseUrl || "https://api.openai.com/v1",
      apiKey: "",
      appId: "",
      secretKey: "",
      sttModel: config?.voice?.sttModel || "gpt-4o-mini-transcribe",
      ttsModel: config?.voice?.ttsModel || "tts-1",
      voice: config?.voice?.voice || "alloy",
      language: config?.voice?.language || "",
      autoSubmit: config?.voice?.autoSubmit ?? true,
      mode: config?.voice?.mode || "hold",
      primaryAsrProfile: initialPrimaryId,
      fallbackAsrProfiles: config?.voice?.fallbackAsrProfiles || [],
      ttsEnabled: config?.voice?.ttsEnabled || false,
      ttsProfile: config?.voice?.ttsProfile || initialPrimaryId,
      statusAnnouncements: config?.voice?.statusAnnouncements || false,
      continuousSilenceMs: config?.voice?.continuousSilenceMs || 900,
      profiles: initialProfiles
    }
  });
  const [selectedVoiceProfileId, setSelectedVoiceProfileId] = useState(initialPrimaryId);

  useEffect(() => {
    const profiles = editableVoiceProfiles(config?.voice);
    const primaryId = config?.voice?.primaryAsrProfile || profiles[0].id;
    setForm((current) => ({
      ...current,
      name: provider?.name || current.name,
      protocol: provider?.protocol || current.protocol,
      baseUrl: provider?.baseUrl || current.baseUrl,
      model: provider?.model || current.model,
      thinking: provider?.thinking || false,
      contextWindow: provider?.contextWindow || 0,
      maxOutputTokens: provider?.maxOutputTokens || 0,
      voice: {
        ...current.voice,
        provider: config?.voice?.provider || current.voice.provider,
        enabled: config?.voice?.enabled || false,
        baseUrl: config?.voice?.baseUrl || current.voice.baseUrl,
        sttModel: config?.voice?.sttModel || current.voice.sttModel,
        ttsModel: config?.voice?.ttsModel || current.voice.ttsModel,
        voice: config?.voice?.voice || current.voice.voice,
        language: config?.voice?.language || "",
        autoSubmit: config?.voice?.autoSubmit ?? true,
        mode: config?.voice?.mode || "hold",
        primaryAsrProfile: primaryId,
        fallbackAsrProfiles: config?.voice?.fallbackAsrProfiles || [],
        ttsEnabled: config?.voice?.ttsEnabled || false,
        ttsProfile: config?.voice?.ttsProfile || primaryId,
        statusAnnouncements: config?.voice?.statusAnnouncements || false,
        continuousSilenceMs: config?.voice?.continuousSilenceMs || 900,
        profiles
      }
    }));
    setSelectedVoiceProfileId(primaryId);
  }, [config?.voice, provider]);

  const update = <K extends keyof ConfigSavePayload>(key: K, value: ConfigSavePayload[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const updateVoice = <K extends keyof ConfigSavePayload["voice"]>(key: K, value: ConfigSavePayload["voice"][K]) => {
    setForm((current) => ({ ...current, voice: { ...current.voice, [key]: value } }));
  };

  const updateVoiceProfile = <K extends keyof VoiceProviderSavePayload>(
    key: K,
    value: VoiceProviderSavePayload[K]
  ) => {
    setForm((current) => ({
      ...current,
      voice: {
        ...current.voice,
        profiles: current.voice.profiles.map((profile) =>
          profile.id === selectedVoiceProfileId ? { ...profile, [key]: value } : profile
        )
      }
    }));
  };

  const selectVoiceProvider = (providerId: VoiceProviderId) => {
    const preset = VOICE_PROVIDER_PRESETS[providerId];
    setForm((current) => ({ ...current, voice: {
      ...current.voice,
      profiles: current.voice.profiles.map((profile) => profile.id === selectedVoiceProfileId ? {
        ...profile,
        provider: providerId,
        baseUrl: preset.baseUrl,
        streamingUrl: preset.streamingUrl,
        batchSttModel: preset.sttModel,
        streamingSttModel: preset.streamingSttModel,
        ttsModel: preset.ttsModel,
        voice: preset.voice
      } : profile)
    }}));
  };

  const addVoiceProfile = () => {
    const id = `profile-${Date.now()}`;
    const preset = VOICE_PROVIDER_PRESETS.siliconflow;
    const profile: VoiceProviderSavePayload = {
      id,
      name: "New Provider",
      provider: "siliconflow",
      baseUrl: preset.baseUrl,
      streamingUrl: "",
      workspaceId: "",
      apiKey: "",
      appId: "",
      secretKey: "",
      batchSttModel: preset.sttModel,
      streamingSttModel: "",
      ttsModel: preset.ttsModel,
      voice: preset.voice,
      language: ""
    };
    setForm((current) => ({ ...current, voice: {
      ...current.voice,
      profiles: [...current.voice.profiles, profile]
    }}));
    setSelectedVoiceProfileId(id);
  };

  const removeVoiceProfile = () => {
    if (form.voice.profiles.length <= 1) return;
    const remaining = form.voice.profiles.filter((profile) => profile.id !== selectedVoiceProfileId);
    const nextId = remaining[0].id;
    setForm((current) => ({ ...current, voice: {
      ...current.voice,
      profiles: remaining,
      primaryAsrProfile: current.voice.primaryAsrProfile === selectedVoiceProfileId ? nextId : current.voice.primaryAsrProfile,
      fallbackAsrProfiles: current.voice.fallbackAsrProfiles.filter((id) => id !== selectedVoiceProfileId),
      ttsProfile: current.voice.ttsProfile === selectedVoiceProfileId ? nextId : current.voice.ttsProfile
    }}));
    setSelectedVoiceProfileId(nextId);
  };

  const moveVoiceProfile = (direction: -1 | 1) => {
    setForm((current) => {
      const profiles = [...current.voice.profiles];
      const index = profiles.findIndex((profile) => profile.id === selectedVoiceProfileId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= profiles.length) return current;
      [profiles[index], profiles[target]] = [profiles[target], profiles[index]];
      const fallbackSet = new Set(current.voice.fallbackAsrProfiles);
      return { ...current, voice: {
        ...current.voice,
        profiles,
        fallbackAsrProfiles: profiles.filter((profile) => fallbackSet.has(profile.id)).map((profile) => profile.id)
      }};
    });
  };

  const selectedVoiceProfile = form.voice.profiles.find(
    (profile) => profile.id === selectedVoiceProfileId
  ) || form.voice.profiles[0];
  const primaryVoiceProfile = form.voice.profiles.find(
    (profile) => profile.id === form.voice.primaryAsrProfile
  );
  const storedPrimary = config?.voice?.profiles.find(
    (profile) => profile.id === form.voice.primaryAsrProfile
  );
  const storedTts = config?.voice?.profiles.find(
    (profile) => profile.id === form.voice.ttsProfile
  );

  const voiceCanSave = !form.voice.enabled || Boolean(
    primaryVoiceProfile &&
    primaryVoiceProfile.baseUrl.trim() &&
    primaryVoiceProfile.streamingUrl.trim() &&
    primaryVoiceProfile.batchSttModel.trim() &&
    primaryVoiceProfile.streamingSttModel.trim() &&
    (primaryVoiceProfile.apiKey.trim() || storedPrimary?.apiKeyConfigured) &&
    (!form.voice.ttsEnabled || Boolean(
      form.voice.ttsProfile &&
      form.voice.profiles.some((profile) =>
        profile.id === form.voice.ttsProfile && profile.ttsModel.trim() && profile.voice.trim()
      ) &&
      (form.voice.profiles.find((profile) => profile.id === form.voice.ttsProfile)?.apiKey.trim() || storedTts?.apiKeyConfigured)
    ))
  );
  const canSave = Boolean(
    form.name.trim() &&
    form.baseUrl.trim() &&
    form.model.trim() &&
    (form.apiKey.trim() || provider?.apiKeyConfigured) &&
    voiceCanSave
  );

  return (
    <div className="dialog-backdrop" role="dialog" aria-modal="true" aria-label="Settings">
      <section className="settings-dialog">
        <header className="settings-head">
          <div>
            <strong>{T.settings}</strong>
            <span>{config?.configPath || "Waiting for backend"}</span>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title={T.closeSettings}>
            <X size={17} />
          </button>
        </header>

        {config?.error && (
          <div className="settings-alert error">
            <AlertTriangle size={16} />
            <span>{config.error}</span>
          </div>
        )}
        {config?.ready && (
          <div className="settings-alert ok">
            <Check size={16} />
            <span>{config.message || T.configVerified}</span>
          </div>
        )}

        <div className="settings-grid">
          <label>
            <span>Name</span>
            <input value={form.name} onChange={(event) => update("name", event.target.value)} />
          </label>

          <label>
            <span>Protocol</span>
            <select value={form.protocol} onChange={(event) => update("protocol", event.target.value as ConfigSavePayload["protocol"])}>
              <option value="openai-compat">OpenAI Compatible</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
            </select>
          </label>

          <label className="wide">
            <span>Base URL</span>
            <input value={form.baseUrl} onChange={(event) => update("baseUrl", event.target.value)} />
          </label>

          <label>
            <span>Model</span>
            <input value={form.model} onChange={(event) => update("model", event.target.value)} />
          </label>

          <label>
            <span>API Key</span>
            <input
              type="password"
              value={form.apiKey}
              placeholder={provider?.apiKeyConfigured ? "Already saved" : ""}
              onChange={(event) => update("apiKey", event.target.value)}
            />
          </label>

          <label>
            <span>Context Window</span>
            <input
              type="number"
              min={0}
              value={form.contextWindow || ""}
              onChange={(event) => update("contextWindow", Number(event.target.value || 0))}
            />
          </label>

          <label>
            <span>Max Output</span>
            <input
              type="number"
              min={0}
              value={form.maxOutputTokens || ""}
              onChange={(event) => update("maxOutputTokens", Number(event.target.value || 0))}
            />
          </label>

          <label>
            <span>Permission Mode</span>
            <select
              value={form.permissionMode}
              onChange={(event) => update("permissionMode", event.target.value as ConfigSavePayload["permissionMode"])}
            >
              <option value="default">Default</option>
              <option value="acceptEdits">Accept Edits</option>
              <option value="plan">Plan</option>
              <option value="bypassPermissions">Bypass Permissions</option>
            </select>
          </label>

          <label className="check-row">
            <input type="checkbox" checked={form.thinking} onChange={(event) => update("thinking", event.target.checked)} />
            <span>Thinking</span>
          </label>

          <div className="settings-section-title">
            <strong>{T.voiceSettings}</strong>
            <span>{"\u591a\u5382\u5bb6\u8bed\u97f3\u8bc6\u522b\u4e0e\u5408\u6210"}</span>
          </div>

          <label className="check-row">
            <input type="checkbox" checked={form.voice.enabled} onChange={(event) => updateVoice("enabled", event.target.checked)} />
            <span>{T.enableVoice}</span>
          </label>

          <label>
            <span>输入模式</span>
            <select disabled={!form.voice.enabled} value={form.voice.mode} onChange={(event) => updateVoice("mode", event.target.value as "hold" | "continuous")}>
              <option value="hold">按住说话</option>
              <option value="continuous">连续对话</option>
            </select>
          </label>

          <div className="voice-profile-toolbar wide">
            <label>
              <span>Provider Profile</span>
              <select value={selectedVoiceProfileId} onChange={(event) => setSelectedVoiceProfileId(event.target.value)}>
                {form.voice.profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
              </select>
            </label>
            <button type="button" className="icon-button" onClick={addVoiceProfile} title="新增 Provider"><Plus size={15} /></button>
            <button type="button" className="icon-button" onClick={() => moveVoiceProfile(-1)} title="上移"><ArrowUp size={15} /></button>
            <button type="button" className="icon-button" onClick={() => moveVoiceProfile(1)} title="下移"><ArrowDown size={15} /></button>
            <button type="button" className="icon-button" disabled={form.voice.profiles.length <= 1} onClick={removeVoiceProfile} title="移除 Provider"><Trash2 size={15} /></button>
          </div>

          <label>
            <span>Profile 名称</span>
            <input value={selectedVoiceProfile.name} onChange={(event) => updateVoiceProfile("name", event.target.value)} />
          </label>

          <label>
            <span>Provider</span>
            <select value={selectedVoiceProfile.provider} onChange={(event) => selectVoiceProvider(event.target.value as VoiceProviderId)}>
              {(Object.entries(VOICE_PROVIDER_PRESETS) as Array<[VoiceProviderId, (typeof VOICE_PROVIDER_PRESETS)[VoiceProviderId]]>).map(([id, preset]) => (
                <option key={id} value={id}>{preset.label}</option>
              ))}
            </select>
          </label>

          <label className="wide">
            <span>Batch API Base URL</span>
            <input disabled={!form.voice.enabled} value={selectedVoiceProfile.baseUrl} onChange={(event) => updateVoiceProfile("baseUrl", event.target.value)} />
          </label>

          <label className="wide">
            <span>Realtime WebSocket URL</span>
            <input disabled={!form.voice.enabled || selectedVoiceProfile.provider !== "aliyun"} value={selectedVoiceProfile.streamingUrl} onChange={(event) => updateVoiceProfile("streamingUrl", event.target.value)} />
          </label>

          <label>
            <span>API Key / Access Token</span>
            <input
              type="password"
              disabled={!form.voice.enabled}
              value={selectedVoiceProfile.apiKey}
              placeholder={config?.voice?.profiles.find((profile) => profile.id === selectedVoiceProfile.id)?.apiKeyConfigured ? "Already saved" : ""}
              onChange={(event) => updateVoiceProfile("apiKey", event.target.value)}
            />
          </label>

          {selectedVoiceProfile.provider === "aliyun" && (
            <label>
              <span>Workspace ID（可选）</span>
              <input
                disabled={!form.voice.enabled}
                value={selectedVoiceProfile.workspaceId}
                onChange={(event) => updateVoiceProfile("workspaceId", event.target.value)}
              />
            </label>
          )}

          {selectedVoiceProfile.provider === "volcengine" && (
            <>
              <label>
                <span>App ID</span>
                <input
                  disabled={!form.voice.enabled}
                  value={selectedVoiceProfile.appId}
                  placeholder={config?.voice?.profiles.find((profile) => profile.id === selectedVoiceProfile.id)?.appIdConfigured ? "Already saved" : ""}
                  onChange={(event) => updateVoiceProfile("appId", event.target.value)}
                />
              </label>
              <label>
                <span>Secret Key（可选）</span>
                <input type="password" disabled={!form.voice.enabled} value={selectedVoiceProfile.secretKey} onChange={(event) => updateVoiceProfile("secretKey", event.target.value)} />
              </label>
            </>
          )}

          <label>
            <span>语言（可选）</span>
            <input disabled={!form.voice.enabled} value={selectedVoiceProfile.language} placeholder="zh" onChange={(event) => updateVoiceProfile("language", event.target.value)} />
          </label>

          <label>
            <span>Batch ASR Model</span>
            <input disabled={!form.voice.enabled} value={selectedVoiceProfile.batchSttModel} onChange={(event) => updateVoiceProfile("batchSttModel", event.target.value)} />
          </label>

          <label>
            <span>Realtime ASR Model</span>
            <input disabled={!form.voice.enabled || selectedVoiceProfile.provider !== "aliyun"} value={selectedVoiceProfile.streamingSttModel} onChange={(event) => updateVoiceProfile("streamingSttModel", event.target.value)} />
          </label>

          <label>
            <span>主 ASR Profile</span>
            <select disabled={!form.voice.enabled} value={form.voice.primaryAsrProfile} onChange={(event) => updateVoice("primaryAsrProfile", event.target.value)}>
              {form.voice.profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
            </select>
          </label>

          <label>
            <span>备用 ASR（按 Profile 顺序）</span>
            <select multiple disabled={!form.voice.enabled} value={form.voice.fallbackAsrProfiles} onChange={(event) => updateVoice(
              "fallbackAsrProfiles",
              Array.from(event.target.selectedOptions).map((option) => option.value)
            )}>
              {form.voice.profiles.filter((profile) => profile.id !== form.voice.primaryAsrProfile).map((profile) => (
                <option key={profile.id} value={profile.id}>{profile.name}</option>
              ))}
            </select>
          </label>

          {form.voice.mode === "continuous" && (
            <label>
              <span>静音结束阈值（ms）</span>
              <input type="number" min={300} max={6000} disabled={!form.voice.enabled} value={form.voice.continuousSilenceMs} onChange={(event) => updateVoice("continuousSilenceMs", Number(event.target.value))} />
            </label>
          )}

          <label className="check-row">
            <input type="checkbox" checked={form.voice.ttsEnabled} disabled={!form.voice.enabled} onChange={(event) => updateVoice("ttsEnabled", event.target.checked)} />
            <span>启用语音播报（可选）</span>
          </label>

          <label>
            <span>TTS Profile</span>
            <select disabled={!form.voice.enabled || !form.voice.ttsEnabled} value={form.voice.ttsProfile} onChange={(event) => updateVoice("ttsProfile", event.target.value)}>
              {form.voice.profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}</option>)}
            </select>
          </label>

          <label>
            <span>TTS Model</span>
            <input disabled={!form.voice.enabled || !form.voice.ttsEnabled} value={selectedVoiceProfile.ttsModel} onChange={(event) => updateVoiceProfile("ttsModel", event.target.value)} />
          </label>

          <label>
            <span>Voice</span>
            <input disabled={!form.voice.enabled || !form.voice.ttsEnabled} value={selectedVoiceProfile.voice} onChange={(event) => updateVoiceProfile("voice", event.target.value)} />
          </label>

          <label className="check-row">
            <input type="checkbox" checked={form.voice.statusAnnouncements} disabled={!form.voice.enabled || !form.voice.ttsEnabled} onChange={(event) => updateVoice("statusAnnouncements", event.target.checked)} />
            <span>播报任务状态</span>
          </label>
        </div>

        <footer className="settings-actions">
          <button type="button" onClick={onClose}>
            {T.cancel}
          </button>
          <button className="send-button" type="button" disabled={!canSave} onClick={() => onSave(form)}>
            <Check size={16} />
            {T.saveVerify}
          </button>
        </footer>
      </section>
    </div>
  );
}
