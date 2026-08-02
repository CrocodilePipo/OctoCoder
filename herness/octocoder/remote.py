# 来源：公众号@小林coding
# 后端八股网站：xiaolincoding.com
# Agent网站：xiaolinnote.com
# 简历模版：jianli.xiaolinnote.com

"""
Remote Control 服务器：通过 WebSocket 桥接 Agent 事件和 Web UI。

使用 websockets 库提供 HTTP（静态 HTML）+ WebSocket 服务，
让用户在浏览器中与 OctoCoder Agent 交互。
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Any

import yaml
import websockets
from websockets.asyncio.server import Server as WSServer, ServerConnection
from websockets.http11 import Request, Response

from octocoder.agent import (
    Agent,
    CompactNotification,
    ErrorEvent,
    HookEvent,
    LoopComplete,
    PermissionRequest,
    PermissionResponse,
    RetryEvent,
    StreamText,
    ThinkingText,
    ToolResultEvent,
    ToolUseEvent,
    TurnComplete,
    UsageEvent,
)
from octocoder.client import NetworkError, create_client, resolve_context_window
from octocoder.commands import CommandContext, CommandRegistry, CommandType
from octocoder.commands.handlers import register_all_commands
from octocoder.commands.parser import parse_command
from octocoder.config import (
    ConfigError,
    MCPServerConfig,
    ProviderConfig,
    VoiceConfig,
    load_config,
)
from octocoder.conversation import ConversationManager
from octocoder.hooks import HookConfigError, HookEngine, load_hooks
from octocoder.mcp import MCPManager
from octocoder.memory import MemoryManager, load_instructions
from octocoder.memory.session import Session, SessionManager
from octocoder.permissions import (
    DangerousCommandDetector,
    PathSandbox,
    PermissionChecker,
    PermissionMode,
    RuleEngine,
)
from octocoder.skills.loader import SkillLoader
from octocoder.tools import ToolRegistry, create_default_registry
from octocoder.tools.impl.tool_search import ToolSearchTool
from octocoder.tools.load_skill import LoadSkill
from octocoder.validator import validate_config_structure
from octocoder.voice import (
    MAX_RECORDING_BYTES,
    MAX_RECORDING_SECONDS,
    RealtimeVoiceSession,
    TTSProvider,
    TranscriptionEvent,
    VoiceProvider,
    VoiceProviderError,
    VoiceUpload,
    create_streaming_asr_provider,
    create_tts_provider,
    create_voice_provider,
    extract_speakable_text,
    split_speakable_text,
)
from octocoder.web_content import INDEX_HTML

log = logging.getLogger(__name__)


class RemoteServer:
    """Remote Control 核心：桥接 Agent 事件和 WebSocket 客户端。"""

    def __init__(
        self,
        providers: list[ProviderConfig],
        mcp_servers: list[MCPServerConfig] | None = None,
        hook_engine: HookEngine | None = None,
        addr: str = "127.0.0.1",
        port: int = 18888,
    ) -> None:
        self.providers = providers
        self._mcp_server_configs = mcp_servers or []
        self.hook_engine = hook_engine
        self.addr = addr
        self.port = port
        self.config_error = ""
        self.config_message = ""
        self.config_dir = Path.cwd()
        self.work_dir = str(Path.cwd())
        self.voice_config = VoiceConfig()

        # WebSocket 连接池（支持多客户端广播）
        self._connections: set[ServerConnection] = set()
        self._send_locks: dict[ServerConnection, asyncio.Lock] = {}

        # Agent 相关状态
        self.agent: Agent | None = None
        self.conversation: ConversationManager | None = None
        self.registry: ToolRegistry | None = None
        self.session_id: str = ""
        self._streaming = False
        self._cancel_event: asyncio.Event | None = None

        # Voice recording and provider state, isolated per WebSocket connection.
        self.voice_provider: VoiceProvider | None = None
        self.tts_provider: TTSProvider | None = None
        self._voice_uploads: dict[ServerConnection, VoiceUpload] = {}
        self._voice_streams: dict[ServerConnection, RealtimeVoiceSession] = {}
        self._pending_voice_binary: dict[ServerConnection, dict[str, Any]] = {}
        self._voice_tasks: dict[ServerConnection, set[asyncio.Task[None]]] = {}
        self._voice_finish_tasks: dict[ServerConnection, asyncio.Task[None]] = {}
        self._pending_voice_turn: tuple[ServerConnection, str, str] | None = None
        self._voice_phases: dict[tuple[ServerConnection, str], str] = {}
        self._voice_playback_tasks: dict[ServerConnection, asyncio.Task[None]] = {}
        self._pending_perm_voice: dict[str, tuple[ServerConnection, str]] = {}

        # 权限请求的 pending 队列：id -> Future
        self._pending_perms: dict[str, asyncio.Future[PermissionResponse]] = {}

        # 命令注册表
        self.command_registry = CommandRegistry()
        register_all_commands(self.command_registry)

        # MCP 相关
        self.mcp_manager: MCPManager | None = None
        self._mcp_task: asyncio.Task[None] | None = None
        self._mcp_instructions: str = ""

        # Skill 加载器
        self.skill_loader: SkillLoader | None = None

        # Memory / Session
        self.memory_manager: MemoryManager | None = None
        self.session_manager: SessionManager | None = None
        self.session: Session | None = None

    def _config_path(self) -> Path:
        return self.config_dir / ".octocoder" / "config.yaml"

    def _read_config_file(self) -> dict[str, Any]:
        path = self._config_path()
        if not path.exists():
            return {}
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}

    def _load_runtime_config(self) -> None:
        config_path = self._config_path()
        config = load_config(config_path) if config_path.exists() else load_config()
        hooks = load_hooks(config.raw_hooks)
        self.providers = config.providers
        self._mcp_server_configs = config.mcp_servers
        self.hook_engine = HookEngine(hooks) if hooks else None
        self.voice_config = config.voice
        self.voice_provider = (
            create_voice_provider(config.voice)
            if config.voice.enabled and config.voice.configured
            else None
        )
        tts_profile = config.voice.selected_tts_profile
        self.tts_provider = (
            create_tts_provider(tts_profile)
            if config.voice.enabled and config.voice.tts_configured and tts_profile is not None
            else None
        )

    def _provider_status(self) -> dict[str, Any]:
        provider = self.providers[0] if self.providers else None
        raw = self._read_config_file()
        raw_provider = {}
        raw_providers = raw.get("providers") if isinstance(raw, dict) else None
        if isinstance(raw_providers, list) and raw_providers and isinstance(raw_providers[0], dict):
            raw_provider = raw_providers[0]

        return {
            "name": provider.name if provider else str(raw_provider.get("name", "deepseek")),
            "protocol": provider.protocol if provider else str(raw_provider.get("protocol", "openai-compat")),
            "baseUrl": provider.base_url if provider else str(raw_provider.get("base_url", "https://api.deepseek.com/v1")),
            "model": provider.model if provider else str(raw_provider.get("model", "deepseek-chat")),
            "apiKeyConfigured": bool(provider.resolve_api_key()) if provider else bool(raw_provider.get("api_key", "")),
            "thinking": bool(provider.thinking) if provider else bool(raw_provider.get("thinking", False)),
            "contextWindow": int(provider.context_window) if provider else int(raw_provider.get("context_window", 0) or 0),
            "maxOutputTokens": int(provider.max_output_tokens) if provider else int(raw_provider.get("max_output_tokens", 0) or 0),
        }

    def _config_status(self) -> dict[str, Any]:
        return {
            "ready": self.agent is not None,
            "configured": bool(self.providers),
            "error": self.config_error,
            "message": self.config_message,
            "configPath": str(self._config_path()),
            "cwd": self.work_dir,
            "provider": self._provider_status(),
            "voice": self._voice_status(),
        }

    def _voice_status(self) -> dict[str, Any]:
        raw = self._read_config_file()
        raw_voice = raw.get("voice") if isinstance(raw, dict) else None
        fallback = raw_voice if isinstance(raw_voice, dict) else {}
        config = self.voice_config
        declared = config.declared
        primary = config.primary_profile
        tts_profile = config.selected_tts_profile
        profiles = [
            {
                "id": profile.id,
                "name": profile.name,
                "provider": profile.provider,
                "baseUrl": profile.base_url,
                "streamingUrl": profile.streaming_url,
                "workspaceId": profile.workspace_id,
                "apiKeyConfigured": bool(profile.resolve_api_key()),
                "appIdConfigured": bool(profile.resolve_app_id()),
                "secretKeyConfigured": bool(profile.resolve_secret_key()),
                "batchSttModel": profile.batch_stt_model,
                "streamingSttModel": profile.streaming_stt_model,
                "ttsModel": profile.tts_model,
                "voice": profile.voice,
                "language": profile.language,
                "batchAsrConfigured": profile.batch_asr_configured,
                "streamingAsrConfigured": profile.streaming_asr_configured,
                "ttsConfigured": profile.tts_configured,
            }
            for profile in config.profiles
        ]
        return {
            "provider": primary.provider if declared else str(fallback.get("provider", "openai-compatible")),
            "enabled": bool(config.enabled if declared else fallback.get("enabled", False)),
            "configured": bool(config.configured),
            "streamingConfigured": bool(config.streaming_configured),
            "ttsEnabled": bool(config.tts_enabled),
            "ttsConfigured": bool(config.tts_configured),
            "baseUrl": primary.base_url if declared else str(fallback.get("base_url", "https://api.openai.com/v1")),
            "apiKeyConfigured": bool(primary.resolve_api_key() or fallback.get("api_key", "")),
            "appIdConfigured": bool(primary.resolve_app_id() or fallback.get("app_id", "")),
            "secretKeyConfigured": bool(primary.resolve_secret_key() or fallback.get("secret_key", "")),
            "sttModel": primary.batch_stt_model if declared else str(fallback.get("stt_model", "gpt-4o-mini-transcribe")),
            "ttsModel": tts_profile.tts_model if tts_profile else "",
            "voice": tts_profile.voice if tts_profile else "",
            "language": primary.language if declared else str(fallback.get("language", "")),
            "autoSubmit": bool(config.auto_submit if declared else fallback.get("auto_submit", False)),
            "mode": config.mode,
            "primaryAsrProfile": config.primary_asr_profile,
            "fallbackAsrProfiles": list(config.fallback_asr_profiles),
            "ttsProfile": config.tts_profile,
            "statusAnnouncements": bool(config.status_announcements),
            "continuousSilenceMs": config.continuous_silence_ms,
            "profiles": profiles,
        }

    async def _try_start_agent(self) -> bool:
        try:
            self._load_runtime_config()
            self._init_agent()
        except (ConfigError, HookConfigError, Exception) as exc:
            self.agent = None
            self.conversation = None
            self.registry = None
            self.session_id = ""
            self.config_error = str(exc)
            return False

        self.config_error = ""
        if not self.config_message:
            self.config_message = "Configuration loaded."
        self._start_mcp_background()
        return True

    def _start_mcp_background(self) -> None:
        if self._mcp_task is not None and not self._mcp_task.done():
            return
        if not self._mcp_server_configs or self.registry is None:
            return
        self._mcp_task = asyncio.create_task(self._init_mcp_background())

    async def _init_mcp_background(self) -> None:
        try:
            await self._init_mcp()
            await self._broadcast({"type": "commands", "data": self._build_command_list()})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("MCP initialization failed: %s", exc)
            await self._broadcast({
                "type": "system",
                "data": {"message": f"MCP initialization failed: {exc}"},
            })

    async def _restart_agent(self) -> bool:
        self._streaming = False
        await self._cancel_all_voice_sessions()
        if self._mcp_task is not None and not self._mcp_task.done():
            self._mcp_task.cancel()
            try:
                await self._mcp_task
            except asyncio.CancelledError:
                pass
        self._mcp_task = None
        if self.mcp_manager is not None:
            await self.mcp_manager.shutdown()
        self.mcp_manager = None
        self._mcp_instructions = ""
        self._pending_perms.clear()
        self.agent = None
        self.conversation = None
        self.registry = None
        self.session_id = ""
        return await self._try_start_agent()

    async def _cancel_all_voice_sessions(self) -> None:
        streams = list(self._voice_streams.values())
        self._voice_streams.clear()
        self._pending_voice_binary.clear()
        self._voice_uploads.clear()
        self._voice_finish_tasks.clear()
        self._pending_voice_turn = None
        playback_connections = list(self._voice_playback_tasks)
        for task in self._voice_playback_tasks.values():
            task.cancel()
        self._voice_playback_tasks.clear()
        self._voice_phases.clear()
        if streams:
            await asyncio.gather(
                *(stream.cancel() for stream in streams),
                return_exceptions=True,
            )
        for websocket in playback_connections:
            if websocket in self._connections:
                await self._send_json(websocket, {
                    "type": "voice_audio_cancel",
                    "data": {"requestId": ""},
                })

    @staticmethod
    def _existing_voice_profiles(existing_voice: dict[str, Any]) -> dict[str, dict[str, Any]]:
        profiles = existing_voice.get("profiles")
        if isinstance(profiles, list):
            return {
                str(profile.get("id", "")): profile
                for profile in profiles
                if isinstance(profile, dict) and str(profile.get("id", ""))
            }
        return {"default": existing_voice} if existing_voice else {}

    def _profile_voice_payload(
        self,
        voice_data: dict[str, Any],
        existing_voice: dict[str, Any],
    ) -> dict[str, Any]:
        incoming = voice_data.get("profiles")
        if not isinstance(incoming, list) or not incoming:
            raise ConfigError("At least one voice provider profile is required")
        existing_by_id = self._existing_voice_profiles(existing_voice)
        profiles: list[dict[str, Any]] = []
        for index, item in enumerate(incoming):
            if not isinstance(item, dict):
                raise ConfigError(f"Voice profile #{index + 1} must be a mapping")
            profile_id = str(item.get("id", "")).strip()
            if not profile_id:
                raise ConfigError(f"Voice profile #{index + 1} ID is required")
            saved = existing_by_id.get(profile_id, {})
            profiles.append(
                {
                    "id": profile_id,
                    "name": str(item.get("name", profile_id)).strip() or profile_id,
                    "provider": str(item.get("provider", "openai-compatible")).strip(),
                    "base_url": str(item.get("baseUrl", "")).strip(),
                    "streaming_url": str(item.get("streamingUrl", "")).strip(),
                    "workspace_id": str(
                        item.get("workspaceId", saved.get("workspace_id", ""))
                    ).strip(),
                    "api_key": str(item.get("apiKey", "")).strip()
                    or str(saved.get("api_key", "")).strip(),
                    "app_id": str(item.get("appId", "")).strip()
                    or str(saved.get("app_id", "")).strip(),
                    "secret_key": str(item.get("secretKey", "")).strip()
                    or str(saved.get("secret_key", "")).strip(),
                    "batch_stt_model": str(
                        item.get("batchSttModel", item.get("sttModel", ""))
                    ).strip(),
                    "streaming_stt_model": str(item.get("streamingSttModel", "")).strip(),
                    "tts_model": str(item.get("ttsModel", "")).strip(),
                    "voice": str(item.get("voice", "")).strip(),
                    "language": str(item.get("language", "")).strip(),
                }
            )
        primary = str(voice_data.get("primaryAsrProfile", profiles[0]["id"])).strip()
        tts_enabled = bool(voice_data.get("ttsEnabled", False))
        tts_profile = str(voice_data.get("ttsProfile", primary if tts_enabled else "")).strip()
        return {
            "enabled": bool(voice_data.get("enabled", False)),
            "mode": str(voice_data.get("mode", "hold")).strip() or "hold",
            "primary_asr_profile": primary,
            "fallback_asr_profiles": list(voice_data.get("fallbackAsrProfiles", [])),
            "tts_enabled": tts_enabled,
            "tts_profile": tts_profile,
            "status_announcements": bool(voice_data.get("statusAnnouncements", False)),
            "continuous_silence_ms": int(voice_data.get("continuousSilenceMs", 900) or 900),
            "auto_submit": bool(voice_data.get("autoSubmit", True)),
            "profiles": profiles,
        }

    def _write_config(self, data: dict[str, Any]) -> None:
        path = self._config_path()
        raw = self._read_config_file()
        if not isinstance(raw, dict):
            raw = {}

        existing_provider: dict[str, Any] = {}
        existing_providers = raw.get("providers")
        if isinstance(existing_providers, list) and existing_providers and isinstance(existing_providers[0], dict):
            existing_provider = existing_providers[0]

        api_key = str(data.get("apiKey", "")).strip() or str(existing_provider.get("api_key", "")).strip()
        if not api_key:
            raise ConfigError("API key is required")

        provider = {
            "name": str(data.get("name", "default")).strip() or "default",
            "protocol": str(data.get("protocol", "openai-compat")).strip(),
            "base_url": str(data.get("baseUrl", "")).strip(),
            "model": str(data.get("model", "")).strip(),
            "api_key": api_key,
            "thinking": bool(data.get("thinking", False)),
        }

        if not provider["base_url"]:
            raise ConfigError("Base URL is required")
        if not provider["model"]:
            raise ConfigError("Model is required")

        context_window = int(data.get("contextWindow", 0) or 0)
        max_output_tokens = int(data.get("maxOutputTokens", 0) or 0)
        if context_window > 0:
            provider["context_window"] = context_window
        if max_output_tokens > 0:
            provider["max_output_tokens"] = max_output_tokens

        raw["providers"] = [provider]
        raw["permission_mode"] = str(data.get("permissionMode", raw.get("permission_mode", "default")) or "default")

        voice_data = data.get("voice")
        if isinstance(voice_data, dict):
            existing_voice = raw.get("voice")
            if not isinstance(existing_voice, dict):
                existing_voice = {}
            if "profiles" in voice_data:
                raw["voice"] = self._profile_voice_payload(voice_data, existing_voice)
                validate_config_structure(raw)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                load_config(path)
                return
            voice_key = str(voice_data.get("apiKey", "")).strip() or str(
                existing_voice.get("api_key", "")
            ).strip()
            app_id = str(voice_data.get("appId", "")).strip() or str(
                existing_voice.get("app_id", "")
            ).strip()
            secret_key = str(voice_data.get("secretKey", "")).strip() or str(
                existing_voice.get("secret_key", "")
            ).strip()
            voice = {
                "provider": str(
                    voice_data.get(
                        "provider",
                        existing_voice.get("provider", "openai-compatible"),
                    )
                ).strip(),
                "enabled": bool(voice_data.get("enabled", False)),
                "base_url": str(voice_data.get("baseUrl", "https://api.openai.com/v1")).strip(),
                "api_key": voice_key,
                "app_id": app_id,
                "secret_key": secret_key,
                "stt_model": str(voice_data.get("sttModel", "gpt-4o-mini-transcribe")).strip(),
                "tts_model": str(voice_data.get("ttsModel", "tts-1")).strip(),
                "voice": str(voice_data.get("voice", "alloy")).strip(),
                "language": str(voice_data.get("language", "")).strip(),
                "auto_submit": bool(voice_data.get("autoSubmit", False)),
            }
            if voice["enabled"] and not (voice_key or os.environ.get("OCTOCODER_VOICE_API_KEY", "")):
                raise ConfigError("Voice API key is required when voice is enabled")
            if (
                voice["enabled"]
                and voice["provider"] == "volcengine"
                and not (app_id or os.environ.get("OCTOCODER_VOICE_APP_ID", ""))
            ):
                raise ConfigError("Voice App ID is required for Volcengine")
            raw["voice"] = voice

        validate_config_structure(raw)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
        load_config(path)

    async def _handle_config_save(self, data: dict[str, Any]) -> None:
        try:
            self._write_config(data)
            self.config_message = "Configuration saved and verified."
            self.config_error = ""
            await self._restart_agent()
            if self.agent is None and not self.config_error:
                self.config_error = "Configuration saved, but OctoCoder did not become ready."
        except Exception as exc:
            self.config_error = str(exc)
            self.config_message = ""
        await self._broadcast({"type": "config_status", "data": self._config_status()})

    def _project_info(self) -> dict[str, str]:
        path = Path(self.work_dir)
        return {
            "name": path.name or str(path),
            "path": str(path),
        }

    async def _handle_project_open(self, data: dict[str, Any]) -> None:
        if self._streaming:
            await self._broadcast({
                "type": "error",
                "data": {"message": "Wait for the current task to finish before switching projects."},
            })
            return

        raw_path = str(data.get("path", "")).strip()
        try:
            path = Path(raw_path).expanduser().resolve()
            if not path.exists() or not path.is_dir():
                raise ConfigError(f"Project folder does not exist: {raw_path}")

            self.work_dir = str(path)
            self.config_message = f"Project opened: {path}"
            self.config_error = ""
            await self._restart_agent()
        except Exception as exc:
            self.config_error = str(exc)
            await self._broadcast({
                "type": "error",
                "data": {"message": f"Failed to open project: {exc}"},
            })
            await self._broadcast({"type": "config_status", "data": self._config_status()})
            return

        info = self._project_info()
        await self._broadcast({
            "type": "project_opened",
            "data": {
                **info,
                "session": self.session_id,
            },
        })
        await self._broadcast({
            "type": "connected",
            "data": {
                "session": self.session_id,
                "cwd": self.work_dir,
            },
        })
        await self._broadcast({"type": "commands", "data": self._build_command_list()})
        await self._broadcast({"type": "config_status", "data": self._config_status()})
        await self._broadcast({
            "type": "system",
            "data": {"message": f"Working directory switched to {self.work_dir}"},
        })

    async def _handle_project_clear(self) -> None:
        if self._streaming:
            await self._broadcast({
                "type": "error",
                "data": {"message": "Wait for the current task to finish before clearing the workspace."},
            })
            return

        self.work_dir = str(self.config_dir)
        self.config_message = "Workspace cleared. Using default working directory."
        self.config_error = ""
        await self._restart_agent()
        await self._broadcast({
            "type": "connected",
            "data": {
                "session": self.session_id,
                "cwd": self.work_dir,
            },
        })
        await self._broadcast({"type": "commands", "data": self._build_command_list()})
        await self._broadcast({"type": "config_status", "data": self._config_status()})
        await self._broadcast({
            "type": "system",
            "data": {"message": f"Using default working directory: {self.work_dir}"},
        })

    # ------------------------------------------------------------------
    # 启动入口
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """启动 HTTP + WebSocket 服务器。"""
        # 初始化 Agent
        await self._try_start_agent()

        # 初始化 MCP（如果有配置）
        await self._init_mcp()

        print(f"\n  Remote UI: http://localhost:{self.port}\n")

        # websockets 的 serve 支持 process_request 回调来处理普通 HTTP
        async with websockets.serve(
            self._ws_handler,
            self.addr,
            self.port,
            process_request=self._process_http_request,
            max_size=4 * 1024 * 1024,  # 4MB 消息上限
        ):
            # 服务器启动后永久阻塞
            await asyncio.Future()

    # ------------------------------------------------------------------
    # HTTP 请求处理（为 / 路径提供前端 HTML）
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Start HTTP/WebSocket first, then initialize Agent and MCP in the background."""
        server = await websockets.serve(
            self._ws_handler,
            self.addr,
            self.port,
            process_request=self._process_http_request,
            max_size=4 * 1024 * 1024,
        )

        print(f"\n  Remote UI: http://localhost:{self.port}\n", flush=True)
        init_task = asyncio.create_task(self._try_start_agent())

        try:
            await server.serve_forever()
        except asyncio.CancelledError:
            server.close()
            await server.wait_closed()
            raise
        finally:
            if not init_task.done():
                init_task.cancel()
                try:
                    await init_task
                except asyncio.CancelledError:
                    pass
            if self._mcp_task is not None and not self._mcp_task.done():
                self._mcp_task.cancel()
                try:
                    await self._mcp_task
                except asyncio.CancelledError:
                    pass
            if self.mcp_manager is not None:
                await self.mcp_manager.shutdown()

    def _process_http_request(
        self, connection: ServerConnection, request: Request
    ) -> Response | None:
        """拦截 HTTP 请求，对 / 路径返回 HTML 页面。
        返回 None 表示继续走 WebSocket 升级流程。
        """
        path = request.path.split("?", 1)[0]

        if path == "/api/status":
            provider = self.providers[0] if self.providers else None
            return self._json_response({
                "session": self.session_id,
                "cwd": self.work_dir,
                "streaming": self._streaming,
                "provider": {
                    "name": provider.name if provider else "",
                    "protocol": provider.protocol if provider else "",
                    "model": provider.model if provider else "",
                },
                "config": self._config_status(),
                "commands": self._build_command_list(),
            })

        if path == "/api/commands":
            return self._json_response(self._build_command_list())

        if request.path != "/ws":
            return self._serve_client_asset(path)
        # /ws 路径 → 继续 WebSocket 升级
        return None

    def _serve_client_asset(self, request_path: str) -> Response:
        dist = self._client_dist_dir()
        if dist is not None:
            relative = request_path.lstrip("/") or "index.html"
            target = (dist / relative).resolve()
            if self._is_relative_to(target, dist) and target.is_file():
                return self._file_response(target)

            index = dist / "index.html"
            if index.is_file():
                return self._file_response(index)

        if request_path == "/":
            return Response(
                200,
                "OK",
                websockets.Headers({"Content-Type": "text/html; charset=utf-8"}),
                INDEX_HTML.encode("utf-8"),
            )
        return Response(404, "Not Found", websockets.Headers(), b"404 Not Found")

    def _client_dist_dir(self) -> Path | None:
        root = Path(__file__).resolve().parents[2]
        dist = root / "client" / "dist"
        return dist if dist.is_dir() else None

    @staticmethod
    def _is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _file_response(path: Path) -> Response:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix == ".js":
            content_type = "text/javascript"
        elif path.suffix == ".css":
            content_type = "text/css"
        elif path.suffix == ".html":
            content_type = "text/html; charset=utf-8"
        return Response(
            200,
            "OK",
            websockets.Headers({"Content-Type": content_type}),
            path.read_bytes(),
        )

    @staticmethod
    def _json_response(data: Any) -> Response:
        return Response(
            200,
            "OK",
            websockets.Headers({"Content-Type": "application/json; charset=utf-8"}),
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
        )

    # ------------------------------------------------------------------
    # WebSocket 连接处理
    # ------------------------------------------------------------------

    async def _ws_handler(self, websocket: ServerConnection) -> None:
        """处理单个 WebSocket 连接的全生命周期。"""
        self._connections.add(websocket)
        try:
            # 连接建立时推送会话信息
            await self._broadcast({
                "type": "connected",
                "data": {
                    "session": self.session_id,
                    "cwd": self.work_dir,
                },
            })

            # 推送命令列表
            await self._broadcast({
                "type": "commands",
                "data": self._build_command_list(),
            })

            # 消息循环
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                if msg_type == "user_message":
                    content = data.get("content", "").strip()
                    if content:
                        # 在后台任务中处理，不阻塞 WebSocket 读循环
                        asyncio.create_task(self._handle_user_message(content))

                elif msg_type == "permission_response":
                    self._handle_permission_response(data)

                elif msg_type == "cancel":
                    if self._cancel_event is not None:
                        self._cancel_event.set()

                elif msg_type == "ping":
                    # 应用层保活
                    await self._broadcast({"type": "pong", "data": None})

        except websockets.ConnectionClosed:
            pass
        finally:
            self._connections.discard(websocket)

    # ------------------------------------------------------------------
    # Agent 初始化（复刻 TUI 的 _select_provider 流程）
    # ------------------------------------------------------------------

    async def _ws_handler(self, websocket: ServerConnection) -> None:
        """Handle one WebSocket client, including binary voice frames."""
        self._connections.add(websocket)
        self._send_locks.setdefault(websocket, asyncio.Lock())
        try:
            await self._send_json(websocket, {
                "type": "connected",
                "data": {
                    "session": self.session_id,
                    "cwd": self.work_dir,
                },
            })
            await self._send_json(websocket, {
                "type": "commands",
                "data": self._build_command_list(),
            })
            await self._send_json(websocket, {
                "type": "config_status",
                "data": self._config_status(),
            })

            async for raw in websocket:
                if isinstance(raw, bytes):
                    await self._handle_voice_binary(websocket, raw)
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                if msg_type == "user_message":
                    content = str(data.get("content", "")).strip()
                    if content:
                        asyncio.create_task(self._handle_user_message(
                            content,
                            source=str(data.get("source", "text")),
                            voice_request_id=str(data.get("voiceRequestId", "")),
                            requester=websocket,
                        ))
                elif msg_type == "permission_response":
                    self._handle_permission_response(data)
                elif msg_type == "cancel":
                    if self._cancel_event is not None:
                        self._cancel_event.set()
                elif msg_type == "config_get":
                    await self._send_json(websocket, {
                        "type": "config_status",
                        "data": self._config_status(),
                    })
                elif msg_type == "config_save":
                    asyncio.create_task(self._handle_config_save(data))
                elif msg_type == "project_open":
                    asyncio.create_task(self._handle_project_open(data))
                elif msg_type == "project_clear":
                    asyncio.create_task(self._handle_project_clear())
                elif msg_type == "voice_record_start":
                    await self._handle_voice_start(websocket, data)
                elif msg_type == "voice_record_stop":
                    await self._handle_voice_stop(websocket, data)
                elif msg_type == "voice_record_cancel":
                    await self._handle_voice_cancel(websocket, data)
                elif msg_type == "voice_stream_start":
                    await self._handle_voice_stream_start(websocket, data)
                elif msg_type == "voice_stream_chunk":
                    await self._handle_voice_stream_chunk(websocket, data)
                elif msg_type == "voice_stream_finish":
                    await self._handle_voice_stream_finish(websocket, data)
                elif msg_type == "voice_stream_cancel":
                    await self._handle_voice_stream_cancel(websocket, data)
                elif msg_type == "voice_playback_interrupt":
                    await self._handle_voice_playback_interrupt(websocket, data)
                elif msg_type == "ping":
                    await self._send_json(websocket, {"type": "pong", "data": None})
        except websockets.ConnectionClosed:
            pass
        finally:
            self._connections.discard(websocket)
            self._voice_uploads.pop(websocket, None)
            self._pending_voice_binary.pop(websocket, None)
            self._voice_finish_tasks.pop(websocket, None)
            playback = self._voice_playback_tasks.pop(websocket, None)
            if playback is not None:
                playback.cancel()
            self._voice_phases = {
                key: value for key, value in self._voice_phases.items() if key[0] is not websocket
            }
            stream = self._voice_streams.pop(websocket, None)
            if stream is not None:
                await stream.cancel()
            for task in self._voice_tasks.pop(websocket, set()):
                task.cancel()
            self._send_locks.pop(websocket, None)

    def _track_voice_task(
        self,
        websocket: ServerConnection,
        coro: Any,
    ) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        tasks = self._voice_tasks.setdefault(websocket, set())
        tasks.add(task)

        def done(completed: asyncio.Task[None]) -> None:
            tasks.discard(completed)
            if not tasks:
                self._voice_tasks.pop(websocket, None)
            try:
                completed.result()
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("Voice background task failed")

        task.add_done_callback(done)
        return task

    async def _handle_voice_start(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> None:
        request_id = str(data.get("requestId", "")).strip()
        mime_type = str(data.get("mimeType", "")).strip() or "audio/webm"
        if not request_id:
            await self._send_voice_error(websocket, "", "Voice request ID is required")
            return
        if not self.voice_config.enabled or self.voice_provider is None:
            await self._send_voice_error(
                websocket,
                request_id,
                "Voice is disabled or not configured. Open Settings to configure it.",
            )
            return
        if self._streaming:
            await self._send_voice_error(
                websocket,
                request_id,
                "Wait for the current task to finish before recording another task.",
            )
            return
        if not mime_type.lower().startswith("audio/"):
            await self._send_voice_error(websocket, request_id, "Unsupported recording format")
            return
        if websocket in self._voice_uploads:
            await self._send_voice_error(websocket, request_id, "A recording is already active")
            return
        self._voice_uploads[websocket] = VoiceUpload(
            request_id=request_id,
            mime_type=mime_type,
            started_at=time.monotonic(),
        )
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": request_id, "phase": "recording"},
        })

    async def _handle_voice_binary(
        self,
        websocket: ServerConnection,
        payload: bytes,
    ) -> None:
        pending = self._pending_voice_binary.pop(websocket, None)
        if pending is not None:
            request_id = str(pending["requestId"])
            stream = self._voice_streams.get(websocket)
            if stream is None or stream.request_id != request_id:
                await self._send_voice_error(websocket, request_id, "No matching voice stream is active")
                return
            if len(payload) != pending["byteLength"]:
                await self._fail_voice_stream(
                    websocket,
                    stream,
                    "Audio frame length does not match its metadata",
                )
                return
            try:
                stream.append_chunk(int(pending["sequence"]), payload)
            except VoiceProviderError as exc:
                await self._fail_voice_stream(websocket, stream, str(exc))
            return

        upload = self._voice_uploads.get(websocket)
        if upload is None:
            await self._send_voice_error(websocket, "", "Received audio without an active recording")
            return
        if len(upload.payload) + len(payload) > MAX_RECORDING_BYTES:
            self._voice_uploads.pop(websocket, None)
            await self._send_voice_error(
                websocket,
                upload.request_id,
                "Recording exceeds the 16 MiB limit",
            )
            return
        upload.payload.extend(payload)

    async def _handle_voice_stream_start(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> asyncio.Task[None] | None:
        request_id = str(data.get("requestId", "")).strip()
        mode = str(data.get("mode", "hold")).strip().lower()
        audio_format = str(data.get("format", "pcm_s16le")).strip().lower()
        try:
            sample_rate = int(data.get("sampleRate", 16000))
            channels = int(data.get("channels", 1))
        except (TypeError, ValueError):
            sample_rate = 0
            channels = 0
        if not request_id:
            await self._send_voice_error(websocket, "", "Voice request ID is required")
            return None
        if not self.voice_config.enabled or not self.voice_config.streaming_configured:
            await self._send_voice_error(
                websocket,
                request_id,
                "Realtime voice is disabled or not configured. Open Settings to configure streaming ASR.",
            )
            return None
        if mode not in {"hold", "continuous"}:
            await self._send_voice_error(websocket, request_id, "Unsupported voice input mode")
            return None
        if audio_format != "pcm_s16le" or sample_rate != 16000 or channels != 1:
            await self._send_voice_error(
                websocket,
                request_id,
                "Realtime voice requires mono pcm_s16le audio at 16000 Hz",
            )
            return None
        if websocket in self._voice_uploads or websocket in self._voice_streams:
            await self._send_voice_error(websocket, request_id, "A voice recording is already active")
            return None
        try:
            provider = create_streaming_asr_provider(self.voice_config.primary_profile)
        except VoiceProviderError as exc:
            await self._send_voice_error(websocket, request_id, str(exc))
            return None

        async def on_partial(event: TranscriptionEvent) -> None:
            if self._voice_streams.get(websocket) is not session:
                return
            await self._send_json(websocket, {
                "type": "voice_transcript_partial",
                "data": {
                    "requestId": request_id,
                    "text": event.text,
                    "sentenceId": event.sentence_id,
                    "revision": event.revision,
                    "final": event.type == "final",
                },
            })

        session = RealtimeVoiceSession(
            self.voice_config,
            provider,
            request_id,
            mode=mode,
            on_partial=on_partial,
        )
        self._voice_streams[websocket] = session
        return self._track_voice_task(
            websocket,
            self._start_voice_stream(websocket, session),
        )

    async def _start_voice_stream(
        self,
        websocket: ServerConnection,
        session: RealtimeVoiceSession,
    ) -> None:
        try:
            await session.start()
        except VoiceProviderError as exc:
            if self._voice_streams.get(websocket) is session:
                self._voice_streams.pop(websocket, None)
            await session.cancel()
            await self._send_voice_error(websocket, session.request_id, str(exc))
            return
        if self._voice_streams.get(websocket) is not session:
            await session.cancel()
            return
        await self._send_json(websocket, {
            "type": "voice_stream_ready",
            "data": {
                "requestId": session.request_id,
                "mode": session.mode,
                "format": "pcm_s16le",
                "sampleRate": 16000,
                "channels": 1,
            },
        })
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": session.request_id, "phase": "listening"},
        })

    async def _handle_voice_stream_chunk(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> None:
        request_id = str(data.get("requestId", "")).strip()
        stream = self._voice_streams.get(websocket)
        if stream is None or stream.request_id != request_id:
            await self._send_voice_error(websocket, request_id, "No matching voice stream is active")
            return
        if websocket in self._pending_voice_binary:
            await self._fail_voice_stream(
                websocket,
                stream,
                "Previous audio frame payload was not received",
            )
            return
        try:
            sequence = int(data.get("sequence"))
            byte_length = int(data.get("byteLength"))
        except (TypeError, ValueError):
            await self._fail_voice_stream(websocket, stream, "Invalid audio frame metadata")
            return
        if byte_length <= 0 or byte_length > 64 * 1024 or byte_length % 2:
            await self._fail_voice_stream(websocket, stream, "Invalid audio frame length")
            return
        self._pending_voice_binary[websocket] = {
            "requestId": request_id,
            "sequence": sequence,
            "byteLength": byte_length,
        }

    async def _handle_voice_stream_finish(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> asyncio.Task[None] | None:
        request_id = str(data.get("requestId", "")).strip()
        stream = self._voice_streams.get(websocket)
        if stream is None or stream.request_id != request_id:
            await self._send_voice_error(websocket, request_id, "No matching voice stream is active")
            return None
        if websocket in self._pending_voice_binary:
            await self._fail_voice_stream(websocket, stream, "Audio frame payload is incomplete")
            return None
        existing = self._voice_finish_tasks.get(websocket)
        if existing is not None:
            return existing
        task = self._track_voice_task(
            websocket,
            self._finish_voice_stream(websocket, stream),
        )
        self._voice_finish_tasks[websocket] = task

        def clear_finish(completed: asyncio.Task[None]) -> None:
            if self._voice_finish_tasks.get(websocket) is completed:
                self._voice_finish_tasks.pop(websocket, None)

        task.add_done_callback(clear_finish)
        return task

    async def _finish_voice_stream(
        self,
        websocket: ServerConnection,
        session: RealtimeVoiceSession,
    ) -> None:
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": session.request_id, "phase": "transcribing"},
        })
        try:
            result = await session.finish()
            agent_busy = self._streaming
            queued = False
            if agent_busy and session.mode == "continuous" and self._pending_voice_turn is None:
                submitted = session.mark_submitted()
                self._pending_voice_turn = (
                    websocket,
                    session.request_id,
                    result.text,
                )
                queued = submitted
            elif agent_busy:
                submitted = False
            else:
                submitted = session.mark_submitted()
            await self._send_json(websocket, {
                "type": "voice_transcript",
                "data": {
                    "requestId": session.request_id,
                    "text": result.text,
                    "submitted": submitted,
                    "provider": result.provider,
                    "profileId": result.profile_id,
                    "fallbackUsed": result.fallback_used,
                },
            })
            if queued:
                await self._send_voice_phase(websocket, session.request_id, "queued")
            elif agent_busy:
                await self._send_voice_error(
                    websocket,
                    session.request_id,
                    "OctoCoder is busy. Continuous mode can queue one pending voice task.",
                )
            elif submitted:
                await self._handle_user_message(
                    result.text,
                    source="voice",
                    voice_request_id=session.request_id,
                    requester=websocket,
                )
        except VoiceProviderError as exc:
            await self._send_voice_error(websocket, session.request_id, str(exc))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("Realtime voice transcription failed")
            await self._send_voice_error(
                websocket,
                session.request_id,
                f"Realtime voice transcription failed: {str(exc)[:500]}",
            )
        finally:
            if self._voice_streams.get(websocket) is session:
                self._voice_streams.pop(websocket, None)
            self._pending_voice_binary.pop(websocket, None)
            await session.cancel()

    async def _handle_voice_stream_cancel(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> None:
        request_id = str(data.get("requestId", "")).strip()
        stream = self._voice_streams.get(websocket)
        if stream is not None and (not request_id or stream.request_id == request_id):
            self._voice_streams.pop(websocket, None)
            self._pending_voice_binary.pop(websocket, None)
            request_id = stream.request_id
            await stream.cancel()
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": request_id, "phase": "idle"},
        })

    async def _fail_voice_stream(
        self,
        websocket: ServerConnection,
        stream: RealtimeVoiceSession,
        message: str,
    ) -> None:
        if self._voice_streams.get(websocket) is stream:
            self._voice_streams.pop(websocket, None)
        self._pending_voice_binary.pop(websocket, None)
        await stream.cancel()
        await self._send_voice_error(websocket, stream.request_id, message)

    async def _handle_voice_stop(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> asyncio.Task[None] | None:
        request_id = str(data.get("requestId", "")).strip()
        upload = self._voice_uploads.get(websocket)
        if upload is None or upload.request_id != request_id:
            await self._send_voice_error(websocket, request_id, "No matching recording is active")
            return None
        self._voice_uploads.pop(websocket, None)
        elapsed = time.monotonic() - upload.started_at
        if elapsed > MAX_RECORDING_SECONDS:
            await self._send_voice_error(
                websocket,
                request_id,
                "Recording exceeds the 120 second limit",
            )
            return None
        if not upload.payload:
            await self._send_voice_error(websocket, request_id, "Recording is empty")
            return None
        return self._track_voice_task(
            websocket,
            self._transcribe_voice_upload(websocket, upload),
        )

    async def _handle_voice_cancel(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> None:
        request_id = str(data.get("requestId", "")).strip()
        upload = self._voice_uploads.get(websocket)
        if upload is not None and (not request_id or upload.request_id == request_id):
            self._voice_uploads.pop(websocket, None)
            request_id = upload.request_id
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": request_id, "phase": "idle"},
        })

    async def _transcribe_voice_upload(
        self,
        websocket: ServerConnection,
        upload: VoiceUpload,
    ) -> None:
        provider = self.voice_provider
        if provider is None:
            await self._send_voice_error(websocket, upload.request_id, "Voice is not configured")
            return
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": upload.request_id, "phase": "transcribing"},
        })
        filename = self._voice_filename(upload.mime_type)
        try:
            transcript = await provider.transcribe(
                bytes(upload.payload),
                filename=filename,
                content_type=upload.mime_type,
                language=self.voice_config.language,
            )
        except VoiceProviderError as exc:
            await self._send_voice_error(websocket, upload.request_id, str(exc))
            return
        except Exception as exc:
            log.exception("Voice transcription failed")
            await self._send_voice_error(
                websocket,
                upload.request_id,
                f"Voice transcription failed: {exc}",
            )
            return

        submitted = bool(self.voice_config.auto_submit)
        await self._send_json(websocket, {
            "type": "voice_transcript",
            "data": {
                "requestId": upload.request_id,
                "text": transcript,
                "submitted": submitted,
            },
        })
        if submitted:
            await self._handle_user_message(
                transcript,
                source="voice",
                voice_request_id=upload.request_id,
                requester=websocket,
            )

    @staticmethod
    def _voice_filename(mime_type: str) -> str:
        normalized = mime_type.lower()
        if "mp4" in normalized or "m4a" in normalized:
            return "recording.m4a"
        if "ogg" in normalized:
            return "recording.ogg"
        if "wav" in normalized:
            return "recording.wav"
        if "mpeg" in normalized or "mp3" in normalized:
            return "recording.mp3"
        return "recording.webm"

    def _init_agent(self) -> None:
        """初始化 Agent 及相关子系统。"""
        provider = self.providers[0]
        work_dir = self.work_dir
        home = Path.home()

        # 权限系统
        checker = PermissionChecker(
            detector=DangerousCommandDetector(),
            sandbox=PathSandbox(work_dir),
            rule_engine=RuleEngine(
                user_rules_path=home / ".octocoder" / "permissions.yaml",
                project_rules_path=Path(work_dir) / ".octocoder" / "permissions.yaml",
                local_rules_path=Path(work_dir) / ".octocoder" / "permissions.local.yaml",
            ),
            mode=PermissionMode.DEFAULT,
        )

        # 加载自定义指令和记忆
        instructions = load_instructions(work_dir)
        self.memory_manager = MemoryManager(work_dir)
        self.session_manager = SessionManager(work_dir)
        self.session = self.session_manager.create()
        self.session_id = self.session.session_id

        # 创建 LLM 客户端
        client = create_client(provider)

        # 工具注册表
        self.registry = create_default_registry()
        self.registry.register(ToolSearchTool(self.registry, protocol=provider.protocol))

        # Skill 加载
        self.skill_loader = SkillLoader(work_dir)
        self.skill_loader.load_all()
        load_skill_tool = LoadSkill()
        self.registry.register(load_skill_tool)

        # 创建 Agent
        self.agent = Agent(
            client=client,
            registry=self.registry,
            protocol=provider.protocol,
            work_dir=work_dir,
            permission_checker=checker,
            context_window=provider.get_context_window(),
            instructions_content=instructions,
            memory_manager=self.memory_manager,
            hook_engine=self.hook_engine,
        )
        self.agent.session_id = self.session_id

        # 连接 Skill 到 Agent
        load_skill_tool.set_loader(self.skill_loader)
        load_skill_tool.set_agent(self.agent)

        catalog = self.skill_loader.get_catalog()
        if catalog:
            lines = ["You can use the following Skills:", ""]
            for name, desc in catalog:
                lines.append(f"- {name}: {desc}")
            lines.append("")
            lines.append("If the user's request matches a Skill, call LoadSkill to activate it.")
            self.agent.set_skill_catalog("\n".join(lines))

        # 初始化对话管理器
        self.conversation = ConversationManager()

        log.info("Agent initialized: session=%s, model=%s", self.session_id, provider.model)

    # ------------------------------------------------------------------
    # MCP 初始化
    # ------------------------------------------------------------------

    async def _init_mcp(self) -> None:
        """连接所有配置的 MCP 服务器，注册工具。"""
        if not self._mcp_server_configs or self.registry is None:
            return

        manager = MCPManager()
        manager.load_configs(self._mcp_server_configs)
        connect_result = await manager.register_all_tools(self.registry)
        self.mcp_manager = manager

        for err in connect_result.errors:
            log.warning("MCP error: %s", err)

        # 构建 MCP 指令（首次发送消息时注入 conversation）
        if connect_result.servers:
            parts = []
            for srv_info in connect_result.servers:
                section = f"## {srv_info.name}\n"
                if srv_info.instructions:
                    section += srv_info.instructions
                else:
                    tool_names = [
                        t.name for t in self.registry.list_tools()
                        if t.name.startswith(f"mcp__{srv_info.name}__")
                    ]
                    if tool_names:
                        section += "Available tools: " + ", ".join(tool_names)
                parts.append(section)
            self._mcp_instructions = (
                "# MCP Server Instructions\n\n"
                "The following MCP servers have provided instructions "
                "for how to use their tools and resources:\n\n"
                + "\n\n".join(parts)
            )

    # ------------------------------------------------------------------
    # 用户消息处理
    # ------------------------------------------------------------------

    async def _handle_user_message(
        self,
        content: str,
        *,
        source: str = "text",
        voice_request_id: str = "",
        requester: ServerConnection | None = None,
        _network_attempt: int = 0,
    ) -> None:
        """处理来自 Web UI 的用户消息或斜杠命令。"""
        if self._streaming:
            return

        if self.agent is None or self.conversation is None:
            await self._broadcast({
                "type": "error",
                "data": {"message": "Open Settings and save a valid configuration before sending a task."},
            })
            return

        # 斜杠命令
        if content.startswith("/"):
            await self._handle_slash_command(content)
            return

        # 普通消息 → 发给 Agent
        self._streaming = True
        assert self.conversation is not None
        assert self.agent is not None

        history_checkpoint = copy.deepcopy(self.conversation.history)
        conversation_checkpoint = (
            self.conversation.env_injected,
            self.conversation.ltm_injected,
            self.conversation.last_input_tokens,
            self.conversation.baseline_tokens,
            self.conversation.anchor_count,
        )
        mcp_checkpoint = self._mcp_instructions

        def restore_failed_turn() -> None:
            assert self.conversation is not None
            self.conversation.history = history_checkpoint
            (
                self.conversation.env_injected,
                self.conversation.ltm_injected,
                self.conversation.last_input_tokens,
                self.conversation.baseline_tokens,
                self.conversation.anchor_count,
            ) = conversation_checkpoint
            self._mcp_instructions = mcp_checkpoint

        self.conversation.add_user_message(content)

        # 首次注入 MCP 指令
        if self._mcp_instructions:
            self.conversation.add_system_reminder(self._mcp_instructions)
            self._mcp_instructions = ""

        # 创建取消事件
        self._cancel_event = asyncio.Event()
        start_time = time.monotonic()
        stream_buf = ""
        turn_text = ""
        turn_used_tools = False
        final_voice_text = ""
        loop_completed = False
        run_failed = False
        was_cancelled = False
        any_tool_started = False
        retry_network = False

        if source == "voice" and requester is not None and voice_request_id:
            await self._send_voice_phase(requester, voice_request_id, "analyzing")

        try:
            async for event in self.agent.run(self.conversation):
                # 检查取消信号
                if self._cancel_event.is_set():
                    was_cancelled = True
                    break

                if isinstance(event, StreamText):
                    stream_buf += event.text
                    turn_text += event.text
                    await self._broadcast({
                        "type": "stream_text",
                        "data": {"text": event.text},
                    })

                elif isinstance(event, ThinkingText):
                    await self._broadcast({
                        "type": "thinking_text",
                        "data": {"text": event.text},
                    })

                elif isinstance(event, ToolUseEvent):
                    any_tool_started = True
                    turn_used_tools = True
                    if source == "voice" and requester is not None and voice_request_id:
                        await self._send_voice_phase(requester, voice_request_id, "executing")
                    await self._broadcast({
                        "type": "tool_use",
                        "data": {
                            "toolId": event.tool_id,
                            "toolName": event.tool_name,
                            "args": event.arguments,
                        },
                    })

                elif isinstance(event, ToolResultEvent):
                    if source == "voice" and requester is not None and voice_request_id:
                        await self._send_voice_phase(requester, voice_request_id, "executing")
                    # 如果之前有累积的流式文本，先结束它
                    if stream_buf:
                        await self._broadcast({
                            "type": "stream_end",
                            "data": {"text": stream_buf},
                        })
                        stream_buf = ""
                    await self._broadcast({
                        "type": "tool_result",
                        "data": {
                            "toolId": event.tool_id,
                            "toolName": event.tool_name,
                            "output": event.output,
                            "isError": event.is_error,
                            "elapsed": event.elapsed,
                        },
                    })

                elif isinstance(event, PermissionRequest):
                    # 生成唯一 ID，等待 Web 端回复
                    perm_id = f"perm_{time.time_ns()}"
                    self._pending_perms[perm_id] = event.future
                    if source == "voice" and requester is not None and voice_request_id:
                        self._pending_perm_voice[perm_id] = (requester, voice_request_id)
                    if source == "voice" and requester is not None and voice_request_id:
                        await self._send_voice_phase(
                            requester,
                            voice_request_id,
                            "waiting_approval",
                        )
                    await self._broadcast({
                        "type": "permission_request",
                        "data": {
                            "id": perm_id,
                            "toolName": event.tool_name,
                            "description": event.description,
                        },
                    })

                elif isinstance(event, TurnComplete):
                    if turn_text.strip() and not turn_used_tools:
                        final_voice_text = turn_text
                    if stream_buf:
                        await self._broadcast({
                            "type": "stream_end",
                            "data": {"text": stream_buf},
                        })
                        stream_buf = ""
                    turn_text = ""
                    turn_used_tools = False
                    await self._broadcast({
                        "type": "turn_complete",
                        "data": {"turn": event.turn},
                    })

                elif isinstance(event, LoopComplete):
                    if turn_text.strip() and not turn_used_tools:
                        final_voice_text = turn_text
                    if stream_buf:
                        await self._broadcast({
                            "type": "stream_end",
                            "data": {"text": stream_buf},
                        })
                        stream_buf = ""
                    loop_completed = True
                    elapsed = time.monotonic() - start_time
                    await self._broadcast({
                        "type": "loop_complete",
                        "data": {
                            "totalTurns": event.total_turns,
                            "elapsed": elapsed,
                        },
                    })

                elif isinstance(event, UsageEvent):
                    await self._broadcast({
                        "type": "usage",
                        "data": {
                            "inputTokens": event.input_tokens,
                            "outputTokens": event.output_tokens,
                        },
                    })

                elif isinstance(event, ErrorEvent):
                    run_failed = True
                    await self._broadcast({
                        "type": "error",
                        "data": {"message": event.message},
                    })

                elif isinstance(event, CompactNotification):
                    await self._broadcast({
                        "type": "compact",
                        "data": {"message": event.message},
                    })

                elif isinstance(event, RetryEvent):
                    if source == "voice" and requester is not None and voice_request_id:
                        await self._send_voice_phase(requester, voice_request_id, "analyzing")
                    await self._broadcast({
                        "type": "retry",
                        "data": {
                            "reason": event.reason,
                            "waitMs": int(event.wait * 1000),
                        },
                    })

                elif isinstance(event, HookEvent):
                    status = "ok" if event.success else "error"
                    await self._broadcast({
                        "type": "system",
                        "data": {
                            "message": f"Hook [{event.hook_id}] {status}: {event.output}"
                        },
                    })

        except asyncio.CancelledError:
            was_cancelled = True
            await self._broadcast({
                "type": "error",
                "data": {"message": "Operation cancelled"},
            })
        except NetworkError as exc:
            run_failed = True
            if not any_tool_started:
                restore_failed_turn()
            if not any_tool_started and _network_attempt < 2:
                retry_network = True
                wait = 0.5 * (2 ** _network_attempt)
                await self._broadcast({
                    "type": "retry",
                    "data": {
                        "reason": f"模型连接中断，正在重试（{_network_attempt + 1}/2）",
                        "waitMs": int(wait * 1000),
                    },
                })
            else:
                await self._broadcast({
                    "type": "error",
                    "data": {
                        "message": f"模型连接中断，自动重试后仍未恢复：{exc}",
                    },
                })
        except Exception as exc:
            run_failed = True
            if not any_tool_started:
                restore_failed_turn()
            log.exception("Agent run error")
            await self._broadcast({
                "type": "error",
                "data": {"message": str(exc)},
            })
        finally:
            self._streaming = False
            self._cancel_event = None
            if not retry_network and (
                source == "voice"
                and voice_request_id
                and requester is not None
                and requester in self._connections
                and loop_completed
                and not run_failed
                and not was_cancelled
                and final_voice_text.strip()
            ):
                self._start_voice_response(
                    requester,
                    voice_request_id,
                    final_voice_text,
                )
            elif (
                not retry_network
                and source == "voice"
                and requester is not None
                and voice_request_id
            ):
                await self._send_voice_phase(requester, voice_request_id, "idle")
            if not retry_network:
                self._start_pending_voice_turn()

        if retry_network:
            wait = 0.5 * (2 ** _network_attempt)
            await asyncio.sleep(wait)
            await self._handle_user_message(
                content,
                source=source,
                voice_request_id=voice_request_id,
                requester=requester,
                _network_attempt=_network_attempt + 1,
            )

    async def _send_voice_phase(
        self,
        websocket: ServerConnection,
        request_id: str,
        phase: str,
    ) -> None:
        key = (websocket, request_id)
        if self._voice_phases.get(key) == phase:
            return
        self._voice_phases[key] = phase
        await self._send_json(websocket, {
            "type": "voice_status",
            "data": {"requestId": request_id, "phase": phase},
        })
        announcements = {
            "analyzing": "正在分析",
            "executing": "正在执行",
            "waiting_approval": "等待审批",
        }
        announcement = announcements.get(phase)
        if (
            announcement
            and self.voice_config.status_announcements
            and self.tts_provider is not None
        ):
            self._start_voice_playback(
                websocket,
                request_id,
                announcement,
                kind="status",
            )
        if phase == "idle":
            self._voice_phases.pop(key, None)

    def _start_pending_voice_turn(self) -> asyncio.Task[None] | None:
        pending = self._pending_voice_turn
        if pending is None or self._streaming:
            return None
        self._pending_voice_turn = None
        websocket, request_id, text = pending
        return self._track_voice_task(
            websocket,
            self._handle_user_message(
                text,
                source="voice",
                voice_request_id=request_id,
                requester=websocket,
            ),
        )

    async def _synthesize_voice_response(
        self,
        websocket: ServerConnection,
        request_id: str,
        markdown: str,
    ) -> None:
        provider = self.tts_provider
        if provider is None:
            await self._send_voice_phase(websocket, request_id, "idle")
            return
        await self._send_json(websocket, {
            "type": "voice_audio_cancel",
            "data": {"requestId": request_id},
        })
        speakable = extract_speakable_text(markdown)
        segments = split_speakable_text(speakable)
        if not segments:
            await self._send_voice_phase(websocket, request_id, "idle")
            return
        await self._send_voice_phase(websocket, request_id, "speaking")
        try:
            for index, segment in enumerate(segments):
                audio = await provider.synthesize(segment)
                await self._send_voice_audio(
                    websocket,
                    request_id=request_id,
                    audio_id=f"voice_{time.time_ns()}",
                    mime_type=audio.content_type,
                    index=index,
                    total=len(segments),
                    payload=audio.data,
                    group_id=request_id,
                    kind="response",
                )
                await asyncio.sleep(0)
        except VoiceProviderError as exc:
            await self._send_voice_error(websocket, request_id, str(exc))
            return
        except Exception as exc:
            log.exception("Voice synthesis failed")
            await self._send_voice_error(
                websocket,
                request_id,
                f"Voice synthesis failed: {exc}",
            )
            return
        await self._send_voice_phase(websocket, request_id, "idle")

    def _start_voice_playback(
        self,
        websocket: ServerConnection,
        request_id: str,
        text: str,
        *,
        kind: str,
    ) -> asyncio.Task[None] | None:
        if self.tts_provider is None:
            return None
        return self._track_voice_playback(
            websocket,
            self._synthesize_voice_text(websocket, request_id, text, kind=kind),
        )

    def _start_voice_response(
        self,
        websocket: ServerConnection,
        request_id: str,
        markdown: str,
    ) -> asyncio.Task[None] | None:
        if self.tts_provider is None:
            asyncio.create_task(self._send_voice_phase(websocket, request_id, "idle"))
            return None
        return self._track_voice_playback(
            websocket,
            self._synthesize_voice_response(websocket, request_id, markdown),
        )

    def _track_voice_playback(
        self,
        websocket: ServerConnection,
        coro: Any,
    ) -> asyncio.Task[None]:
        existing = self._voice_playback_tasks.pop(websocket, None)
        if existing is not None and not existing.done():
            existing.cancel()
        task = self._track_voice_task(websocket, coro)
        self._voice_playback_tasks[websocket] = task

        def clear(completed: asyncio.Task[None]) -> None:
            if self._voice_playback_tasks.get(websocket) is completed:
                self._voice_playback_tasks.pop(websocket, None)

        task.add_done_callback(clear)
        return task

    async def _synthesize_voice_text(
        self,
        websocket: ServerConnection,
        request_id: str,
        text: str,
        *,
        kind: str,
    ) -> None:
        provider = self.tts_provider
        if provider is None:
            return
        try:
            await self._send_json(websocket, {
                "type": "voice_audio_cancel",
                "data": {"requestId": request_id},
            })
            audio = await provider.synthesize(text)
            await self._send_voice_audio(
                websocket,
                request_id=request_id,
                audio_id=f"voice_{time.time_ns()}",
                mime_type=audio.content_type,
                index=0,
                total=1,
                payload=audio.data,
                group_id=request_id,
                kind=kind,
            )
        except asyncio.CancelledError:
            raise
        except VoiceProviderError as exc:
            await self._send_voice_error(websocket, request_id, str(exc))
        except Exception as exc:
            log.exception("Voice announcement synthesis failed")
            await self._send_voice_error(
                websocket,
                request_id,
                f"Voice synthesis failed: {str(exc)[:500]}",
            )

    async def _handle_voice_playback_interrupt(
        self,
        websocket: ServerConnection,
        data: dict[str, Any],
    ) -> None:
        request_id = str(data.get("requestId", "")).strip()
        task = self._voice_playback_tasks.pop(websocket, None)
        if task is not None and not task.done():
            task.cancel()
        await self._send_json(websocket, {
            "type": "voice_audio_cancel",
            "data": {"requestId": request_id},
        })

    # ------------------------------------------------------------------
    # 斜杠命令处理
    # ------------------------------------------------------------------

    async def _handle_slash_command(self, input_text: str) -> None:
        """分发斜杠命令。"""
        name, args, is_command = parse_command(input_text)
        if not is_command or not name:
            return

        cmd = self.command_registry.find(name)
        if cmd is None:
            await self._broadcast({
                "type": "error",
                "data": {"message": f"Unknown command: /{name} — type /help to see available commands"},
            })
            await self._broadcast({"type": "command_done", "data": None})
            return

        # 需要参数但没给
        if not args and cmd.arg_prompt:
            await self._broadcast({
                "type": "system",
                "data": {"message": cmd.arg_prompt},
            })
            await self._broadcast({"type": "command_done", "data": None})
            return

        if cmd.type == CommandType.LOCAL:
            # 本地命令直接执行
            ctx = self._build_command_context(args)
            try:
                await cmd.handler(ctx)
            except Exception as exc:
                await self._broadcast({
                    "type": "error",
                    "data": {"message": f"Command error: {exc}"},
                })
            await self._broadcast({"type": "command_done", "data": None})

        elif cmd.type == CommandType.LOCAL_UI:
            # UI 命令需要特殊处理
            if name == "clear":
                self.conversation = ConversationManager()
                if self.agent is not None:
                    self.agent.clear_active_skills()
                await self._broadcast({"type": "clear", "data": None})

            elif name == "compact":
                await self._handle_compact()
                return

            else:
                await self._broadcast({
                    "type": "system",
                    "data": {"message": f"/{name} is not fully supported in remote mode."},
                })

            await self._broadcast({"type": "command_done", "data": None})

        elif cmd.type == CommandType.PROMPT:
            # Prompt 类命令：handler 返回 prompt 文本，注入给 agent
            ctx = self._build_command_context(args)
            try:
                await cmd.handler(ctx)
            except Exception as exc:
                await self._broadcast({
                    "type": "error",
                    "data": {"message": f"Command error: {exc}"},
                })
                await self._broadcast({"type": "command_done", "data": None})

    def _build_command_context(self, args: str) -> CommandContext:
        """构建命令上下文。"""
        return CommandContext(
            args=args,
            agent=self.agent,
            conversation=self.conversation,
            session=self.session,
            session_manager=self.session_manager,
            memory_manager=self.memory_manager,
            ui=self,  # type: ignore[arg-type]
            config={
                "registry": self.command_registry,
            },
        )

    async def _handle_compact(self) -> None:
        """处理 /compact 命令。"""
        if self.agent is None or self.conversation is None:
            await self._broadcast({
                "type": "error",
                "data": {"message": "Compact requires an active agent."},
            })
            await self._broadcast({"type": "command_done", "data": None})
            return

        await self._broadcast({
            "type": "system",
            "data": {"message": "Compacting conversation..."},
        })

        result = await self.agent.manual_compact(self.conversation)
        if isinstance(result, CompactNotification):
            await self._broadcast({
                "type": "system",
                "data": {"message": result.message},
            })
        elif isinstance(result, ErrorEvent):
            await self._broadcast({
                "type": "error",
                "data": {"message": result.message},
            })

        await self._broadcast({"type": "command_done", "data": None})

    # ------------------------------------------------------------------
    # UIController 协议实现（供命令系统回调）
    # ------------------------------------------------------------------

    def add_system_message(self, text: str) -> None:
        """同步接口 — 在事件循环中调度广播。"""
        asyncio.ensure_future(self._broadcast({
            "type": "system",
            "data": {"message": text},
        }))

    def send_user_message(self, text: str) -> None:
        """同步接口 — 注入用户消息并触发 agent。"""
        asyncio.create_task(self._handle_user_message(text))

    def set_plan_mode(self, enabled: bool) -> None:
        if self.agent is None:
            return
        if enabled:
            self.agent.set_permission_mode(PermissionMode.PLAN)
        else:
            self.agent.set_permission_mode(PermissionMode.DEFAULT)

    def get_token_count(self) -> tuple[int, int]:
        if self.agent:
            return self.agent.total_input_tokens, self.agent.total_output_tokens
        return 0, 0

    def refresh_status(self) -> None:
        pass  # Remote 模式不需要刷新 TUI 状态栏

    # ------------------------------------------------------------------
    # 权限响应处理
    # ------------------------------------------------------------------

    def _handle_permission_response(self, data: dict[str, Any]) -> None:
        """处理来自 Web UI 的权限回复。"""
        perm_id = data.get("id", "")
        response_str = data.get("response", "deny")

        future = self._pending_perms.pop(perm_id, None)
        voice_context = self._pending_perm_voice.pop(perm_id, None)
        if future is None or future.done():
            return

        # 映射字符串到枚举
        mapping = {
            "allow": PermissionResponse.ALLOW,
            "deny": PermissionResponse.DENY,
            "allowAlways": PermissionResponse.ALLOW_ALWAYS,
        }
        response = mapping.get(response_str, PermissionResponse.DENY)
        future.set_result(response)
        if voice_context is not None:
            websocket, request_id = voice_context
            asyncio.create_task(self._send_voice_phase(websocket, request_id, "executing"))

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    async def _send_json(
        self,
        websocket: ServerConnection,
        msg: dict[str, Any],
    ) -> None:
        lock = self._send_locks.setdefault(websocket, asyncio.Lock())
        async with lock:
            await websocket.send(json.dumps(msg, ensure_ascii=False))

    async def _send_voice_audio(
        self,
        websocket: ServerConnection,
        *,
        request_id: str,
        audio_id: str,
        mime_type: str,
        index: int,
        total: int,
        payload: bytes,
        group_id: str = "",
        kind: str = "response",
    ) -> None:
        metadata = {
            "type": "voice_audio_start",
            "data": {
                "requestId": request_id,
                "audioId": audio_id,
                "mimeType": mime_type,
                "index": index,
                "total": total,
                "groupId": group_id or request_id,
                "kind": kind,
            },
        }
        lock = self._send_locks.setdefault(websocket, asyncio.Lock())
        async with lock:
            await websocket.send(json.dumps(metadata, ensure_ascii=False))
            await websocket.send(payload)

    async def _send_voice_error(
        self,
        websocket: ServerConnection,
        request_id: str,
        message: str,
    ) -> None:
        await self._send_json(websocket, {
            "type": "voice_error",
            "data": {"requestId": request_id, "message": message},
        })

    def _build_command_list(self) -> list[dict[str, str]]:
        """构建命令列表，推送给前端用于斜杠命令菜单。"""
        result = []
        for cmd in self.command_registry.list_commands():
            result.append({
                "name": cmd.name,
                "description": cmd.description,
            })
        return result

    async def _broadcast(self, msg: dict[str, Any]) -> None:
        """向所有已连接的 WebSocket 客户端广播消息。"""
        if not self._connections:
            return
        data = json.dumps(msg, ensure_ascii=False)
        # 复制集合避免迭代中修改
        closed = []
        for ws in list(self._connections):
            try:
                lock = self._send_locks.setdefault(ws, asyncio.Lock())
                async with lock:
                    await ws.send(data)
            except websockets.ConnectionClosed:
                closed.append(ws)
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._connections.discard(ws)
            self._voice_uploads.pop(ws, None)
            self._pending_voice_binary.pop(ws, None)
            stream = self._voice_streams.pop(ws, None)
            if stream is not None:
                await stream.cancel()
            playback = self._voice_playback_tasks.pop(ws, None)
            if playback is not None:
                playback.cancel()
            self._send_locks.pop(ws, None)
