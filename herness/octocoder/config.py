# 来源：公众号@小林coding
# 后端八股网站：xiaolincoding.com
# Agent网站：xiaolinnote.com
# 简历模版：jianli.xiaolinnote.com
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .validator import (
    ConfigError,
    DEFAULT_CONTEXT_WINDOW,
    VALID_PERMISSION_MODES,
    VALID_PROTOCOLS,
    VALID_TEAMMATE_MODES,
    lookup_model_context_window,
    validate_config_structure,
)


_ENV_KEY_MAP = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openai-compat": "OPENAI_API_KEY",
}

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


@dataclass
class ProviderConfig:
    name: str
    protocol: str
    base_url: str
    model: str
    api_key: str = ""
    thinking: bool = False
    # 0 表示"未设置" — get_context_window() 通过四层 fallback 解析真实窗口大小。
    # 正数表示配置文件里显式指定的覆盖值。
    context_window: int = 0
    max_output_tokens: int = 0
    # 运行时 cache，存放从 provider 的 /v1/models 端点自动拉取的 context window
    # （get_context_window 的第 2 层）。通过 set_fetched_context_window() 写入一次；
    # 0 表示"尚未拉取"。不会持久化。
    _fetched_context_window: int = field(default=0, repr=False)

    def resolve_api_key(self) -> str:
        if self.api_key:
            return self.api_key
        env_var = _ENV_KEY_MAP.get(self.protocol, "")
        return os.environ.get(env_var, "")

    def set_fetched_context_window(self, window: int) -> None:
        """记录从 provider 自动拉取到的 context window（第 2 层）。

        非正数会被忽略，这样一次失败的拉取就不会污染 cache。在解析
        context window 时，每个 provider 只会调用一次。
        """
        if window > 0:
            self._fetched_context_window = window

    def get_context_window(self) -> int:
        """通过四层 fallback 解析模型的 context window，按优先级从高到低：

          1. 配置文件提供的 context_window（> 0）——显式覆盖，永远优先。
          2. 从 provider 的 /v1/models 端点自动拉取并通过 set_fetched_context_window
             缓存的值（只有 anthropic 协议的 provider 才会设置它；拉取失败或缺失时
             保持为 0 并跳过）。
          3. 内置的「模型名 -> window」映射表（按子串匹配）。
          4. 保守的默认值（claude -> 200000，其他 -> 128000）。
        """
        if self.context_window > 0:
            return self.context_window
        if self._fetched_context_window > 0:
            return self._fetched_context_window
        window = lookup_model_context_window(self.model)
        if window > 0:
            return window
        if "claude" in self.model.lower():
            return DEFAULT_CONTEXT_WINDOW
        return 128_000

    def get_max_output_tokens(self) -> int:
        if self.max_output_tokens > 0:
            return self.max_output_tokens
        if self.thinking:
            return 64000
        return 8192


def resolve_env_vars(value: str) -> str:
    return _ENV_VAR_RE.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)


def build_child_env(declared_env: dict[str, str] | None) -> dict[str, str]:
    env: dict[str, str] = {}
    path = os.environ.get("PATH", "")
    if path:
        env["PATH"] = path
    for key, value in (declared_env or {}).items():
        env[key] = resolve_env_vars(value)
    return env


@dataclass
class MCPServerConfig:
    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


    @property
    def is_stdio(self) -> bool:
        return self.command is not None


@dataclass
class WorktreeConfig:
    symlink_directories: list[str] = field(default_factory=lambda: ["node_modules", ".venv", "vendor"])
    stale_cleanup_interval: int = 3600
    stale_cutoff_hours: int = 24


@dataclass
class SandboxAppConfig:
    """沙箱相关的配置项。"""
    enabled: bool = False         # 是否启用 OS 级沙箱
    auto_allow: bool = False      # 是否自动放行命令（沙箱兜底）
    network_enabled: bool = False  # 沙箱内是否允许网络访问


@dataclass
class VoiceProviderProfile:
    """One independently configured speech-provider account."""

    id: str = "default"
    name: str = "Default"
    provider: str = "openai-compatible"
    base_url: str = "https://api.openai.com/v1"
    streaming_url: str = ""
    workspace_id: str = ""
    api_key: str = ""
    app_id: str = ""
    secret_key: str = ""
    batch_stt_model: str = "gpt-4o-mini-transcribe"
    streaming_stt_model: str = ""
    tts_model: str = "tts-1"
    voice: str = "alloy"
    language: str = ""

    def resolve_api_key(self) -> str:
        return self.api_key or os.environ.get("OCTOCODER_VOICE_API_KEY", "")

    def resolve_app_id(self) -> str:
        return self.app_id or os.environ.get("OCTOCODER_VOICE_APP_ID", "")

    def resolve_secret_key(self) -> str:
        return self.secret_key or os.environ.get("OCTOCODER_VOICE_SECRET_KEY", "")

    @property
    def batch_asr_configured(self) -> bool:
        return bool(
            self.base_url
            and self.resolve_api_key()
            and self.batch_stt_model
            and (self.provider != "volcengine" or self.resolve_app_id())
        )

    @property
    def streaming_asr_configured(self) -> bool:
        return bool(
            self.provider == "aliyun"
            and self.streaming_url
            and self.resolve_api_key()
            and self.streaming_stt_model
        )

    @property
    def tts_configured(self) -> bool:
        return bool(
            self.base_url
            and self.resolve_api_key()
            and self.tts_model
            and self.voice
            and (self.provider != "volcengine" or self.resolve_app_id())
        )


@dataclass
class VoiceConfig:
    """ASR configuration with independently optional text-to-speech."""

    provider: str = "openai-compatible"
    enabled: bool = False
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    app_id: str = ""
    secret_key: str = ""
    stt_model: str = "gpt-4o-mini-transcribe"
    tts_model: str = "tts-1"
    voice: str = "alloy"
    language: str = ""
    auto_submit: bool = False
    mode: str = "hold"
    primary_asr_profile: str = "default"
    fallback_asr_profiles: list[str] = field(default_factory=list)
    tts_enabled: bool = False
    tts_profile: str = ""
    status_announcements: bool = False
    continuous_silence_ms: int = 900
    profiles: list[VoiceProviderProfile] = field(default_factory=list)
    declared: bool = field(default=False, repr=False)
    legacy: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if not self.profiles:
            self.profiles = [
                VoiceProviderProfile(
                    id=self.primary_asr_profile or "default",
                    name="Default",
                    provider=self.provider,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    app_id=self.app_id,
                    secret_key=self.secret_key,
                    batch_stt_model=self.stt_model,
                    tts_model=self.tts_model,
                    voice=self.voice,
                    language=self.language,
                )
            ]
        if not self.primary_asr_profile:
            self.primary_asr_profile = self.profiles[0].id

    def get_profile(self, profile_id: str) -> VoiceProviderProfile | None:
        return next((profile for profile in self.profiles if profile.id == profile_id), None)

    @property
    def primary_profile(self) -> VoiceProviderProfile:
        return self.get_profile(self.primary_asr_profile) or self.profiles[0]

    @property
    def selected_tts_profile(self) -> VoiceProviderProfile | None:
        if not self.tts_enabled:
            return None
        return self.get_profile(self.tts_profile)

    def resolve_api_key(self) -> str:
        return self.primary_profile.resolve_api_key()

    def resolve_app_id(self) -> str:
        return self.primary_profile.resolve_app_id()

    def resolve_secret_key(self) -> str:
        return self.primary_profile.resolve_secret_key()

    @property
    def configured(self) -> bool:
        return self.primary_profile.batch_asr_configured

    @property
    def streaming_configured(self) -> bool:
        return self.primary_profile.streaming_asr_configured

    @property
    def tts_configured(self) -> bool:
        profile = self.selected_tts_profile
        return bool(profile and profile.tts_configured)


@dataclass
class AppConfig:
    providers: list[ProviderConfig]
    permission_mode: str = "default"
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
    raw_hooks: list[dict] = field(default_factory=list)
    enable_fork: bool = False
    enable_verification_agent: bool = False
    worktree: WorktreeConfig = field(default_factory=WorktreeConfig)
    teammate_mode: str = ""
    enable_coordinator_mode: bool = False
    sandbox: SandboxAppConfig = field(default_factory=SandboxAppConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)


def _load_single_file(path: Path) -> AppConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse config {path}: {e}") from e

    validated = validate_config_structure(raw)

    providers = [
        ProviderConfig(
            name=p["name"],
            protocol=p["protocol"],
            base_url=p["base_url"],
            model=p["model"],
            api_key=p["api_key"],
            thinking=p["thinking"],
            context_window=p["context_window"],
            max_output_tokens=p["max_output_tokens"],
        )
        for p in validated["providers"]
    ]

    mcp_servers = [
        MCPServerConfig(
            name=s["name"],
            command=s["command"],
            args=s["args"],
            url=s["url"],
            headers=s["headers"],
            env=s["env"],
        )
        for s in validated["mcp_servers"]
    ]

    wt = validated["worktree"]
    worktree_cfg = WorktreeConfig(
        symlink_directories=wt["symlink_directories"],
        stale_cleanup_interval=wt["stale_cleanup_interval"],
        stale_cutoff_hours=wt["stale_cutoff_hours"],
    )

    sb = validated["sandbox"]
    sandbox_cfg = SandboxAppConfig(
        enabled=sb["enabled"],
        auto_allow=sb["auto_allow"],
        network_enabled=sb["network_enabled"],
    )

    voice = validated["voice"]
    voice_profiles = [
        VoiceProviderProfile(
            id=profile["id"],
            name=profile["name"],
            provider=profile["provider"],
            base_url=profile["base_url"],
            streaming_url=profile["streaming_url"],
            workspace_id=profile["workspace_id"],
            api_key=profile["api_key"],
            app_id=profile["app_id"],
            secret_key=profile["secret_key"],
            batch_stt_model=profile["batch_stt_model"],
            streaming_stt_model=profile["streaming_stt_model"],
            tts_model=profile["tts_model"],
            voice=profile["voice"],
            language=profile["language"],
        )
        for profile in voice["profiles"]
    ]
    voice_cfg = VoiceConfig(
        provider=voice["provider"],
        enabled=voice["enabled"],
        base_url=voice["base_url"],
        api_key=voice["api_key"],
        app_id=voice["app_id"],
        secret_key=voice["secret_key"],
        stt_model=voice["stt_model"],
        tts_model=voice["tts_model"],
        voice=voice["voice"],
        language=voice["language"],
        auto_submit=voice["auto_submit"],
        mode=voice["mode"],
        primary_asr_profile=voice["primary_asr_profile"],
        fallback_asr_profiles=voice["fallback_asr_profiles"],
        tts_enabled=voice["tts_enabled"],
        tts_profile=voice["tts_profile"],
        status_announcements=voice["status_announcements"],
        continuous_silence_ms=voice["continuous_silence_ms"],
        profiles=voice_profiles,
        declared=voice["_declared"],
        legacy=voice["_legacy"],
    )
    if voice_cfg.enabled and not voice_cfg.configured:
        raise ConfigError(
            "Voice API key is required when voice is enabled "
            "(set voice.api_key or OCTOCODER_VOICE_API_KEY)"
        )
    if voice_cfg.tts_enabled and not voice_cfg.tts_configured:
        raise ConfigError(
            "Voice TTS API key is required when TTS is enabled "
            "(set the selected profile api_key or OCTOCODER_VOICE_API_KEY)"
        )

    return AppConfig(
        providers=providers,
        permission_mode=validated["permission_mode"],
        mcp_servers=mcp_servers,
        raw_hooks=validated["hooks"],
        enable_fork=validated["enable_fork"],
        enable_verification_agent=validated["enable_verification_agent"],
        worktree=worktree_cfg,
        teammate_mode=validated["teammate_mode"],
        enable_coordinator_mode=validated["enable_coordinator_mode"],
        sandbox=sandbox_cfg,
        voice=voice_cfg,
    )


def _merge_config(base: AppConfig, override: AppConfig) -> AppConfig:
    if override.providers:
        base.providers = override.providers
    if override.permission_mode != "default":
        base.permission_mode = override.permission_mode

    if override.mcp_servers:
        by_name = {s.name: i for i, s in enumerate(base.mcp_servers)}
        for s in override.mcp_servers:
            if s.name in by_name:
                base.mcp_servers[by_name[s.name]] = s
            else:
                base.mcp_servers.append(s)
                by_name[s.name] = len(base.mcp_servers) - 1

    base.raw_hooks.extend(override.raw_hooks)
    if override.enable_fork:
        base.enable_fork = True
    if override.enable_verification_agent:
        base.enable_verification_agent = True
    if override.teammate_mode:
        base.teammate_mode = override.teammate_mode
    if override.enable_coordinator_mode:
        base.enable_coordinator_mode = True
    # 沙箱配置：后层覆盖前层（任一字段为非默认值即覆盖）
    if override.sandbox.enabled:
        base.sandbox.enabled = True
    if override.sandbox.auto_allow:
        base.sandbox.auto_allow = True
    if override.sandbox.network_enabled:
        base.sandbox.network_enabled = True
    if override.voice.declared:
        base.voice = override.voice
    return base


def load_config(path: Path | None = None) -> AppConfig:
    if path is not None:
        if not path.exists():
            raise ConfigError(f"Config file not found: {path}")
        return _load_single_file(path)

    cwd = Path.cwd()
    home = Path.home()
    candidates = [
        home / ".octocoder" / "config.yaml",
        cwd / ".octocoder" / "config.yaml",
        cwd / ".octocoder" / "config.local.yaml",
    ]

    merged: AppConfig | None = None
    for p in candidates:
        if not p.exists():
            continue
        layer = _load_single_file(p)
        if merged is None:
            merged = layer
        else:
            merged = _merge_config(merged, layer)

    if merged is None:
        raise ConfigError(
            "No config file found. Expected .octocoder/config.yaml "
            "in project or ~/.octocoder/config.yaml"
        )
    return merged
