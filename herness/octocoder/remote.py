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
from octocoder.client import create_client, resolve_context_window
from octocoder.commands import CommandContext, CommandRegistry, CommandType
from octocoder.commands.handlers import register_all_commands
from octocoder.commands.parser import parse_command
from octocoder.config import ConfigError, MCPServerConfig, ProviderConfig, load_config
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

        # WebSocket 连接池（支持多客户端广播）
        self._connections: set[ServerConnection] = set()

        # Agent 相关状态
        self.agent: Agent | None = None
        self.conversation: ConversationManager | None = None
        self.registry: ToolRegistry | None = None
        self.session_id: str = ""
        self._streaming = False
        self._cancel_event: asyncio.Event | None = None

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
        """Handle one WebSocket client."""
        self._connections.add(websocket)
        try:
            await websocket.send(json.dumps({
                "type": "connected",
                "data": {
                    "session": self.session_id,
                    "cwd": self.work_dir,
                },
            }, ensure_ascii=False))
            await websocket.send(json.dumps({
                "type": "commands",
                "data": self._build_command_list(),
            }, ensure_ascii=False))
            await websocket.send(json.dumps({
                "type": "config_status",
                "data": self._config_status(),
            }, ensure_ascii=False))

            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")
                data = msg.get("data", {})

                if msg_type == "user_message":
                    content = str(data.get("content", "")).strip()
                    if content:
                        asyncio.create_task(self._handle_user_message(content))
                elif msg_type == "permission_response":
                    self._handle_permission_response(data)
                elif msg_type == "cancel":
                    if self._cancel_event is not None:
                        self._cancel_event.set()
                elif msg_type == "config_get":
                    await websocket.send(json.dumps({
                        "type": "config_status",
                        "data": self._config_status(),
                    }, ensure_ascii=False))
                elif msg_type == "config_save":
                    asyncio.create_task(self._handle_config_save(data))
                elif msg_type == "project_open":
                    asyncio.create_task(self._handle_project_open(data))
                elif msg_type == "project_clear":
                    asyncio.create_task(self._handle_project_clear())
                elif msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong", "data": None}, ensure_ascii=False))
        except websockets.ConnectionClosed:
            pass
        finally:
            self._connections.discard(websocket)

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

    async def _handle_user_message(self, content: str) -> None:
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

        self.conversation.add_user_message(content)

        # 首次注入 MCP 指令
        if self._mcp_instructions:
            self.conversation.add_system_reminder(self._mcp_instructions)
            self._mcp_instructions = ""

        # 创建取消事件
        self._cancel_event = asyncio.Event()
        start_time = time.monotonic()
        stream_buf = ""

        try:
            async for event in self.agent.run(self.conversation):
                # 检查取消信号
                if self._cancel_event.is_set():
                    break

                if isinstance(event, StreamText):
                    stream_buf += event.text
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
                    await self._broadcast({
                        "type": "tool_use",
                        "data": {
                            "toolId": event.tool_id,
                            "toolName": event.tool_name,
                            "args": event.arguments,
                        },
                    })

                elif isinstance(event, ToolResultEvent):
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
                    await self._broadcast({
                        "type": "permission_request",
                        "data": {
                            "id": perm_id,
                            "toolName": event.tool_name,
                            "description": event.description,
                        },
                    })

                elif isinstance(event, TurnComplete):
                    if stream_buf:
                        await self._broadcast({
                            "type": "stream_end",
                            "data": {"text": stream_buf},
                        })
                        stream_buf = ""
                    await self._broadcast({
                        "type": "turn_complete",
                        "data": {"turn": event.turn},
                    })

                elif isinstance(event, LoopComplete):
                    if stream_buf:
                        await self._broadcast({
                            "type": "stream_end",
                            "data": {"text": stream_buf},
                        })
                        stream_buf = ""
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
            await self._broadcast({
                "type": "error",
                "data": {"message": "Operation cancelled"},
            })
        except Exception as exc:
            log.exception("Agent run error")
            await self._broadcast({
                "type": "error",
                "data": {"message": str(exc)},
            })
        finally:
            self._streaming = False
            self._cancel_event = None

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

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

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
                await ws.send(data)
            except websockets.ConnectionClosed:
                closed.append(ws)
            except Exception:
                closed.append(ws)
        for ws in closed:
            self._connections.discard(ws)
