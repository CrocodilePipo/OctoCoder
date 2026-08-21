from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from octocoder.agent import (
    Agent,
    CompactNotification,
    ContextEventNotification,
    ErrorEvent,
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
from octocoder.agents.loader import AgentLoader
from octocoder.agents.task_manager import TaskManager
from octocoder.agents.trace import TraceManager
from octocoder.client import create_client, resolve_context_window
from octocoder.config import AppConfig, WorktreeConfig
from octocoder.conversation import ConversationManager, Message
from octocoder.hooks import HookEngine
from octocoder.memory.instructions import load_instructions
from octocoder.memory.session import Session, SessionManager, make_compact_boundary
from octocoder.permissions import (
    DangerousCommandDetector,
    PathSandbox,
    PermissionChecker,
    PermissionMode,
    RuleEngine,
)
from octocoder.teams.manager import TeamManager
from octocoder.tools import create_default_registry
from octocoder.tools.agent_tool import AgentTool
from octocoder.tools.impl.tool_search import ToolSearchTool
from octocoder.tools.team_create import TeamCreateTool
from octocoder.tools.team_delete import TeamDeleteTool
from octocoder.worktree import WorktreeManager


EventSink = Callable[[dict[str, Any]], None]


@dataclass
class TurnResult:
    text: str
    duration_ms: int
    turns: int
    input_tokens: int
    output_tokens: int
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class SessionResumeResult:
    boundary_id: str
    restored_messages: int


class NonInteractiveSession:
    def __init__(
        self,
        *,
        config: AppConfig,
        permission_mode: PermissionMode,
        hook_engine: HookEngine | None,
        event_sink: EventSink | None,
        work_dir: str,
    ) -> None:
        self.config = config
        self.permission_mode = permission_mode
        self.hook_engine = hook_engine
        self.event_sink = event_sink
        self.work_dir = work_dir
        self.provider = config.providers[0]
        self.client: Any = None
        self.agent: Agent
        self.conversation = ConversationManager()
        self.trace_manager: TraceManager
        self.task_manager: TaskManager
        self.team_manager: TeamManager
        self.session_manager: SessionManager
        self.session: Session
        self._persisted_message_ids: set[int] = set()
        self._last_text = ""
        self._closed = False

    @classmethod
    async def create(
        cls,
        config: AppConfig,
        permission_mode: PermissionMode,
        hook_engine: HookEngine | None = None,
        event_sink: EventSink | None = None,
        work_dir: str | None = None,
    ) -> "NonInteractiveSession":
        instance = cls(
            config=config,
            permission_mode=permission_mode,
            hook_engine=hook_engine,
            event_sink=event_sink,
            work_dir=os.path.abspath(work_dir or os.getcwd()),
        )
        await instance._initialize()
        return instance

    async def _initialize(self) -> None:
        provider = self.provider
        self.client = create_client(provider)
        await resolve_context_window(provider)
        home = Path.home()
        checker = PermissionChecker(
            detector=DangerousCommandDetector(),
            sandbox=PathSandbox(self.work_dir),
            rule_engine=RuleEngine(
                user_rules_path=home / ".octocoder" / "permissions.yaml",
                project_rules_path=Path(self.work_dir) / ".octocoder" / "permissions.yaml",
                local_rules_path=Path(self.work_dir) / ".octocoder" / "permissions.local.yaml",
            ),
            mode=self.permission_mode,
        )
        instructions = load_instructions(self.work_dir)
        registry = create_default_registry()
        registry.register(ToolSearchTool(registry, protocol=provider.protocol))
        self.agent = Agent(
            client=self.client,
            registry=registry,
            protocol=provider.protocol,
            work_dir=self.work_dir,
            permission_checker=checker,
            context_window=provider.get_context_window(),
            instructions_content=instructions,
            hook_engine=self.hook_engine,
        )

        worktree_config = self.config.worktree or WorktreeConfig()
        worktree_manager = WorktreeManager(
            repo_root=self.work_dir,
            symlink_directories=worktree_config.symlink_directories,
        )
        self.trace_manager = TraceManager()
        self.task_manager = TaskManager()
        agent_loader = AgentLoader(
            self.work_dir,
            enable_verification=self.config.enable_verification_agent,
        )
        agent_loader.load_all()
        self.team_manager = TeamManager(
            worktree_manager=worktree_manager,
            trace_manager=self.trace_manager,
        )
        registry.register(
            AgentTool(
                agent_loader=agent_loader,
                task_manager=self.task_manager,
                trace_manager=self.trace_manager,
                parent_agent=self.agent,
                enable_fork=self.config.enable_fork,
                provider_config=provider,
                worktree_manager=worktree_manager,
                team_manager=self.team_manager,
            )
        )
        registry.register(
            TeamCreateTool(
                team_manager=self.team_manager,
                parent_agent=self.agent,
                teammate_mode="in-process",
                is_interactive=False,
                enable_coordinator_mode=self.config.enable_coordinator_mode,
            )
        )
        registry.register(
            TeamDeleteTool(team_manager=self.team_manager, parent_agent=self.agent)
        )
        self.agent.notification_fn = self.team_manager.drain_lead_mailbox

        self.session_manager = SessionManager(self.work_dir, observer=self.agent)
        self.session = self.session_manager.create()
        self.agent.session_id = self.session.session_id

    def _emit(self, event: dict[str, Any]) -> None:
        if self.event_sink is not None:
            enriched = dict(event)
            enriched.setdefault("stage_id", getattr(self.agent, "context_stage_id", ""))
            enriched.setdefault(
                "checkpoint_id", getattr(self.agent, "context_checkpoint_id", None)
            )
            self.event_sink(enriched)

    def _sync_session(self) -> None:
        for message in self.conversation.history:
            identity = id(message)
            if identity in self._persisted_message_ids:
                continue
            self.session.append(message)
            self._persisted_message_ids.add(identity)

    def _trace_summary(self, tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "lead_agent_id": "lead",
            "tool_call_count": len(tool_calls),
            "failed_tool_call_count": sum(
                1 for call in tool_calls if call.get("is_error")
            ),
            "agents": [
                {
                    "agent_id": node.agent_id,
                    "parent_agent_id": node.parent_id,
                    "trace_id": node.trace_id,
                    "agent_type": node.agent_type,
                    "status": node.status,
                    "input_tokens": node.input_tokens,
                    "output_tokens": node.output_tokens,
                    "tool_call_count": node.tool_call_count,
                }
                for node in self.trace_manager._nodes.values()
            ],
        }

    async def run_turn(
        self,
        prompt: str,
        stage_id: str = "",
        checkpoint_id: str | None = None,
    ) -> TurnResult:
        if self._closed:
            raise RuntimeError("non-interactive session is closed")
        self.agent.set_context_stage(stage_id, checkpoint_id)
        self.conversation.add_user_message(prompt)
        start = time.monotonic()
        text_buffer = ""
        total_input = self.agent.total_input_tokens
        total_output = self.agent.total_output_tokens
        turns = 0
        tool_calls: list[dict[str, Any]] = []
        errors: list[str] = []

        async for event in self.agent.run(self.conversation):
            if isinstance(event, StreamText):
                text_buffer += event.text
                self._emit({"type": "assistant", "text": event.text})
            elif isinstance(event, ThinkingText):
                self._emit({"type": "thinking", "text": event.text})
            elif isinstance(event, ToolUseEvent):
                tool_calls.append(
                    {"name": event.tool_name, "tool_id": event.tool_id, "is_error": False}
                )
                self._emit(
                    {
                        "type": "tool_use",
                        "tool_name": event.tool_name,
                        "tool_id": event.tool_id,
                        "args": event.arguments,
                    }
                )
            elif isinstance(event, ToolResultEvent):
                for call in reversed(tool_calls):
                    if call["tool_id"] == event.tool_id:
                        call["is_error"] = event.is_error
                        break
                self._emit(
                    {
                        "type": "tool_result",
                        "tool_name": event.tool_name,
                        "tool_id": event.tool_id,
                        "output": event.output,
                        "is_error": event.is_error,
                        "elapsed": round(event.elapsed, 3),
                    }
                )
            elif isinstance(event, UsageEvent):
                total_input = event.input_tokens
                total_output = event.output_tokens
                self._emit(
                    {
                        "type": "usage",
                        "input_tokens": total_input,
                        "output_tokens": total_output,
                    }
                )
            elif isinstance(event, TurnComplete):
                turns = max(turns, event.turn)
                self._emit({"type": "turn_complete", "turn": event.turn})
            elif isinstance(event, LoopComplete):
                turns = max(turns, event.total_turns)
                break
            elif isinstance(event, ErrorEvent):
                errors.append(event.message)
                self._emit({"type": "error", "message": event.message})
            elif isinstance(event, CompactNotification):
                self._emit(
                    {
                        "type": "compact",
                        "message": event.message,
                        "before_tokens": event.before_tokens,
                    }
                )
                if event.boundary is not None:
                    self.session.append_record(
                        make_compact_boundary(
                            event.boundary.summary,
                            event.boundary.keep,
                        )
                    )
                    self._persisted_message_ids.update(
                        id(message) for message in self.conversation.history
                    )
            elif isinstance(event, ContextEventNotification):
                self._emit(
                    {"type": "context", "event_type": event.event_type, **event.payload}
                )
            elif isinstance(event, RetryEvent):
                self._emit({"type": "retry", "reason": event.reason})
            elif isinstance(event, PermissionRequest):
                self._emit(
                    {
                        "type": "permission_request",
                        "tool_name": event.tool_name,
                        "description": event.description,
                    }
                )
                event.future.set_result(PermissionResponse.ALLOW)
                self._emit(
                    {
                        "type": "permission_decision",
                        "tool_name": event.tool_name,
                        "decision": PermissionResponse.ALLOW.value,
                        "source": "non_interactive",
                    }
                )

        self._sync_session()
        self._last_text = text_buffer
        duration_ms = int((time.monotonic() - start) * 1000)
        result = TurnResult(
            text=text_buffer,
            duration_ms=duration_ms,
            turns=turns,
            input_tokens=total_input,
            output_tokens=total_output,
            tool_calls=tool_calls,
            errors=errors,
        )
        self._emit(
            {
                "type": "result",
                "result": text_buffer,
                "duration_ms": duration_ms,
                "num_turns": turns,
                "tool_calls": tool_calls,
                "usage": {
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                },
                "provider": self.provider.name,
                "model": self.provider.model,
                "agent_trace_summary": self._trace_summary(tool_calls),
                "stop_reason": "end_turn" if not errors else "error",
            }
        )
        return result

    async def checkpoint(self, checkpoint_id: str) -> dict[str, Any]:
        tool_use_ids = {
            tool.tool_use_id
            for message in self.conversation.history
            for tool in message.tool_uses
        }
        tool_result_ids = {
            result.tool_use_id
            for message in self.conversation.history
            for result in message.tool_results
        }
        return {
            "id": checkpoint_id,
            "facts": {},
            "active_instructions": [],
            "task_state": {
                "message_count": len(self.conversation.history),
                "current_tokens": self.conversation.current_tokens(),
            },
            "answer": self._last_text,
            "tool_pair_complete": tool_result_ids <= tool_use_ids,
            "source": "agent_probe",
        }

    async def persist_and_resume(self, stage_id: str = "resume") -> SessionResumeResult:
        self._sync_session()
        session_id = self.session.session_id
        return await self.resume_existing(session_id, stage_id)

    async def resume_existing(
        self,
        session_id: str,
        stage_id: str = "resume",
    ) -> SessionResumeResult:
        """Replace the current conversation with a persisted session.

        The newly initialized Agent keeps its own provider/model while the restored
        conversation remains provider-agnostic. This is the process-restart and
        cross-model resume entry point used by evaluation and desktop recovery.
        """
        self._sync_session()
        self.session.close()
        self.agent.set_context_stage(stage_id)
        resumed = self.session_manager.resume(session_id, observer=self.agent)
        if resumed is None:
            raise RuntimeError(f"session {session_id!r} could not be resumed")
        self.session = resumed.session
        self.conversation = ConversationManager()
        self.conversation.history = list(resumed.messages)
        self.conversation.env_injected = any(
            message.content.startswith("<system-reminder>")
            for message in resumed.messages
        )
        self.conversation.ltm_injected = self.conversation.env_injected
        self._persisted_message_ids = {id(message) for message in resumed.messages}
        self.agent.session_id = session_id
        boundary_id = ""
        for event in self.agent._drain_context_events():
            boundary_id = str(event.payload.get("boundary_id", boundary_id))
            self._emit({"type": "context", "event_type": event.event_type, **event.payload})
        return SessionResumeResult(
            boundary_id=boundary_id,
            restored_messages=len(resumed.messages),
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._sync_session()
        self.session.close()
        pending = [task for task in self.task_manager._async_tasks.values() if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._closed = True
