# 来源：公众号@小林coding
# 后端八股网站：xiaolincoding.com
# Agent网站：xiaolinnote.com
# 简历模版：jianli.xiaolinnote.com
"""OctoCoder 的配置校验逻辑。"""

from __future__ import annotations

VALID_PROTOCOLS = {"anthropic", "openai", "openai-compat"}

VALID_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "plan",
    "bypassPermissions",
}

VALID_TEAMMATE_MODES = {"", "in-process"}

VALID_VOICE_PROVIDERS = {
    "openai",
    "siliconflow",
    "aliyun",
    "volcengine",
    "openai-compatible",
}

VOICE_PROVIDER_DEFAULTS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "batch_stt_model": "gpt-4o-mini-transcribe",
        "streaming_url": "",
        "streaming_stt_model": "",
        "tts_model": "tts-1",
        "voice": "alloy",
    },
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "batch_stt_model": "FunAudioLLM/SenseVoiceSmall",
        "streaming_url": "",
        "streaming_stt_model": "",
        "tts_model": "FunAudioLLM/CosyVoice2-0.5B",
        "voice": "FunAudioLLM/CosyVoice2-0.5B:anna",
    },
    "aliyun": {
        "base_url": "https://dashscope.aliyuncs.com",
        "batch_stt_model": "qwen3-asr-flash",
        "streaming_url": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
        "streaming_stt_model": "qwen-audio-3.0-asr-flash-streaming",
        "tts_model": "qwen-audio-3.0-tts-flash",
        "voice": "longanhuan_v3.6",
    },
    "volcengine": {
        "base_url": "https://openspeech.bytedance.com",
        "batch_stt_model": "volc.bigasr.auc_turbo",
        "streaming_url": "",
        "streaming_stt_model": "",
        "tts_model": "seed-tts-1.1",
        "voice": "zh_female_cancan_mars_bigtts",
    },
    "openai-compatible": {
        "base_url": "https://api.openai.com/v1",
        "batch_stt_model": "gpt-4o-mini-transcribe",
        "streaming_url": "",
        "streaming_stt_model": "",
        "tts_model": "tts-1",
        "voice": "alloy",
    },
}

DEFAULT_CONTEXT_WINDOW = 200_000

# 内置的"模型名子串 -> context window（最大输入 token 数）"映射表，
# 是 context window 回退链的第 3 层（见 ProviderConfig.get_context_window）。
# 按从最具体到最通用排序，第一个子串命中即生效。值仅为合理起始点，
# 模型更新/重命名后可能过时。如果值不准确，在配置中设置 context_window 覆盖（最高优先级）。
MODEL_CONTEXT_WINDOWS: list[tuple[str, int]] = [
    ("1m", 1_000_000),       # 也覆盖 "-1m" 后缀（如 claude-...-1m）
    ("gpt-4.1", 1_000_000),  # GPT-4.1 系列的 window 为 1M
    ("gpt-4o", 128_000),
    ("gpt-4-turbo", 128_000),
    ("o1", 200_000),         # OpenAI 推理模型 o1 / o3 / o4
    ("o3", 200_000),
    ("o4", 200_000),
    ("gpt-3.5", 16_385),
    ("claude", 200_000),
]


def lookup_model_context_window(model: str) -> int:
    """通过子串匹配（第 3 层），返回内置映射表中该模型对应的
    context window；没有匹配则返回 0。"""
    m = model.lower()
    for substr, window in MODEL_CONTEXT_WINDOWS:
        if substr in m:
            return window
    return 0


class ConfigError(Exception):
    pass


def validate_providers(raw_providers: list) -> list[dict]:
    """校验 providers 列表，返回清洗后的 provider 字典列表。"""
    if not isinstance(raw_providers, list) or len(raw_providers) == 0:
        raise ConfigError("At least one provider must be configured")

    providers: list[dict] = []
    for i, entry in enumerate(raw_providers):
        if not isinstance(entry, dict):
            raise ConfigError(f"Provider #{i + 1}: must be a mapping")

        missing = [f for f in ("name", "protocol", "base_url", "model") if f not in entry]
        if missing:
            raise ConfigError(f"Provider #{i + 1}: missing fields: {', '.join(missing)}")

        protocol = entry["protocol"]
        if protocol not in VALID_PROTOCOLS:
            raise ConfigError(
                f"Provider #{i + 1}: invalid protocol '{protocol}', "
                f"must be one of: {', '.join(sorted(VALID_PROTOCOLS))}"
            )

        # 默认为 0（"未设置"）而非硬编码的 window 值：0 会让
        # ProviderConfig.get_context_window() 走四层回退链解析
        #（自动拉取 / 映射表 / 默认值）。配置中显式指定的值仍须为正整数，
        # 且作为最高优先级覆盖。
        context_window = entry.get("context_window", 0)
        if not isinstance(context_window, int) or isinstance(context_window, bool) or context_window < 0:
            raise ConfigError(
                f"Provider #{i + 1}: context_window must be a positive integer"
            )

        thinking = entry.get("thinking", False)
        if not isinstance(thinking, bool):
            raise ConfigError(f"Provider #{i + 1}: thinking must be a boolean")

        max_output_tokens = entry.get("max_output_tokens", 0)
        if not isinstance(max_output_tokens, int) or max_output_tokens < 0:
            raise ConfigError(
                f"Provider #{i + 1}: max_output_tokens must be a non-negative integer"
            )

        providers.append(
            {
                "name": entry["name"],
                "protocol": protocol,
                "base_url": entry["base_url"],
                "model": entry["model"],
                "api_key": entry.get("api_key", ""),
                "thinking": thinking,
                "context_window": context_window,
                "max_output_tokens": max_output_tokens,
            }
        )

    return providers


def validate_permission_mode(mode: str) -> str:
    """校验 permission_mode 取值。"""
    if mode not in VALID_PERMISSION_MODES:
        raise ConfigError(
            f"Invalid permission_mode '{mode}', "
            f"must be one of: {', '.join(sorted(VALID_PERMISSION_MODES))}"
        )
    return mode


def validate_mcp_servers(raw_mcp: list | None) -> list[dict]:
    """校验 mcp_servers 配置段，返回清洗后的 server 配置字典列表。"""
    if raw_mcp is None:
        return []

    if not isinstance(raw_mcp, list):
        raise ConfigError("'mcp_servers' must be a list of server configs")

    servers: list[dict] = []
    for i, entry in enumerate(raw_mcp):
        if not isinstance(entry, dict):
            raise ConfigError(f"MCP server #{i + 1}: must be a mapping")
        name = entry.get("name")
        if not name:
            raise ConfigError(f"MCP server #{i + 1}: missing 'name'")
        has_command = "command" in entry
        has_url = "url" in entry
        if has_command and has_url:
            raise ConfigError(
                f"MCP server '{name}': cannot have both 'command' and 'url'"
            )
        if not has_command and not has_url:
            raise ConfigError(
                f"MCP server '{name}': must have either 'command' or 'url'"
            )
        servers.append(
            {
                "name": name,
                "command": entry.get("command"),
                "args": entry.get("args", []),
                "url": entry.get("url"),
                "headers": entry.get("headers", {}),
                "env": entry.get("env", {}),
            }
        )

    return servers


def validate_hooks(raw_hooks: list | None) -> list:
    """校验 hooks 配置段。"""
    if raw_hooks is None:
        return []
    if not isinstance(raw_hooks, list):
        raise ConfigError("'hooks' must be a list of hook definitions")
    return raw_hooks


def validate_bool_field(value: object, field_name: str) -> bool:
    """校验一个布尔类型的配置字段。"""
    if not isinstance(value, bool):
        raise ConfigError(f"'{field_name}' must be a boolean")
    return value


def validate_worktree(raw_wt: dict | None) -> dict:
    """校验 worktree 配置段，返回清洗后的配置字典。"""
    defaults = {
        "symlink_directories": ["node_modules", ".venv", "vendor"],
        "stale_cleanup_interval": 3600,
        "stale_cutoff_hours": 24,
    }

    if raw_wt is None:
        return defaults

    if not isinstance(raw_wt, dict):
        raise ConfigError("'worktree' must be a mapping")

    sym = raw_wt.get("symlink_directories", defaults["symlink_directories"])
    if not isinstance(sym, list) or not all(isinstance(s, str) for s in sym):
        raise ConfigError("'worktree.symlink_directories' must be a list of strings")

    interval = raw_wt.get("stale_cleanup_interval", defaults["stale_cleanup_interval"])
    if not isinstance(interval, int) or interval <= 0:
        raise ConfigError("'worktree.stale_cleanup_interval' must be a positive integer")

    cutoff = raw_wt.get("stale_cutoff_hours", defaults["stale_cutoff_hours"])
    if not isinstance(cutoff, int) or cutoff <= 0:
        raise ConfigError("'worktree.stale_cutoff_hours' must be a positive integer")

    return {
        "symlink_directories": sym,
        "stale_cleanup_interval": interval,
        "stale_cutoff_hours": cutoff,
    }


def validate_teammate_mode(mode: object) -> str:
    """校验 teammate_mode 取值。"""
    if not isinstance(mode, str) or mode not in VALID_TEAMMATE_MODES:
        raise ConfigError(
            f"Invalid teammate_mode '{mode}', "
            f"must be one of: {', '.join(repr(m) for m in sorted(VALID_TEAMMATE_MODES))}"
        )
    return mode


def validate_sandbox(raw_sb: dict | None) -> dict:
    """校验 sandbox 配置段，返回清洗后的配置字典。"""
    defaults = {
        "enabled": False,
        "auto_allow": False,
        "network_enabled": False,
    }

    if raw_sb is None:
        return defaults

    if not isinstance(raw_sb, dict):
        raise ConfigError("'sandbox' must be a mapping")

    result = dict(defaults)
    for key in ("enabled", "auto_allow", "network_enabled"):
        if key in raw_sb:
            val = raw_sb[key]
            if not isinstance(val, bool):
                raise ConfigError(f"'sandbox.{key}' must be a boolean")
            result[key] = val

    return result


def _voice_string(mapping: dict, key: str, default: str = "", *, path: str) -> str:
    value = mapping.get(key, default)
    if not isinstance(value, str):
        raise ConfigError(f"'{path}.{key}' must be a string")
    return value.strip()


def _validate_voice_profile(raw: object, index: int) -> dict:
    if not isinstance(raw, dict):
        raise ConfigError(f"'voice.profiles[{index}]' must be a mapping")
    path = f"voice.profiles[{index}]"
    profile_id = _voice_string(raw, "id", path=path)
    if not profile_id:
        raise ConfigError(f"'{path}.id' is required")
    provider = _voice_string(raw, "provider", "openai-compatible", path=path)
    if provider not in VALID_VOICE_PROVIDERS:
        raise ConfigError(
            "Invalid voice provider "
            f"'{provider}', must be one of: {', '.join(sorted(VALID_VOICE_PROVIDERS))}"
        )
    defaults = VOICE_PROVIDER_DEFAULTS[provider]
    profile = {
        "id": profile_id,
        "name": _voice_string(raw, "name", profile_id, path=path) or profile_id,
        "provider": provider,
        "base_url": _voice_string(raw, "base_url", defaults["base_url"], path=path),
        "streaming_url": _voice_string(
            raw, "streaming_url", defaults["streaming_url"], path=path
        ),
        "workspace_id": _voice_string(raw, "workspace_id", path=path),
        "api_key": _voice_string(raw, "api_key", path=path),
        "app_id": _voice_string(raw, "app_id", path=path),
        "secret_key": _voice_string(raw, "secret_key", path=path),
        "batch_stt_model": _voice_string(
            raw,
            "batch_stt_model",
            _voice_string(raw, "stt_model", defaults["batch_stt_model"], path=path),
            path=path,
        ),
        "streaming_stt_model": _voice_string(
            raw, "streaming_stt_model", defaults["streaming_stt_model"], path=path
        ),
        "tts_model": _voice_string(raw, "tts_model", defaults["tts_model"], path=path),
        "voice": _voice_string(raw, "voice", defaults["voice"], path=path),
        "language": _voice_string(raw, "language", path=path),
    }
    if provider == "volcengine" and profile["app_id"] and not profile["app_id"].isdigit():
        raise ConfigError(
            "Volcengine App ID must contain digits only; "
            "App ID and Access Token may be reversed"
        )
    return profile


def _legacy_voice_profile(raw_voice: dict) -> dict:
    provider = _voice_string(raw_voice, "provider", "openai-compatible", path="voice")
    if provider not in VALID_VOICE_PROVIDERS:
        raise ConfigError(
            "Invalid voice provider "
            f"'{provider}', must be one of: {', '.join(sorted(VALID_VOICE_PROVIDERS))}"
        )
    defaults = VOICE_PROVIDER_DEFAULTS[provider]
    legacy = {
        "id": "default",
        "name": "Default",
        "provider": provider,
        "base_url": _voice_string(raw_voice, "base_url", defaults["base_url"], path="voice"),
        "streaming_url": _voice_string(
            raw_voice, "streaming_url", defaults["streaming_url"], path="voice"
        ),
        "workspace_id": _voice_string(raw_voice, "workspace_id", path="voice"),
        "api_key": _voice_string(raw_voice, "api_key", path="voice"),
        "app_id": _voice_string(raw_voice, "app_id", path="voice"),
        "secret_key": _voice_string(raw_voice, "secret_key", path="voice"),
        "batch_stt_model": _voice_string(
            raw_voice,
            "batch_stt_model",
            _voice_string(raw_voice, "stt_model", defaults["batch_stt_model"], path="voice"),
            path="voice",
        ),
        "streaming_stt_model": _voice_string(
            raw_voice,
            "streaming_stt_model",
            defaults["streaming_stt_model"],
            path="voice",
        ),
        "tts_model": _voice_string(raw_voice, "tts_model", defaults["tts_model"], path="voice"),
        "voice": _voice_string(raw_voice, "voice", defaults["voice"], path="voice"),
        "language": _voice_string(raw_voice, "language", path="voice"),
    }
    if provider == "volcengine" and legacy["app_id"] and not legacy["app_id"].isdigit():
        raise ConfigError(
            "Volcengine App ID must contain digits only; "
            "App ID and Access Token may be reversed"
        )
    return legacy


def validate_voice(raw_voice: dict | None) -> dict:
    """Validate voice profiles while accepting the legacy single-provider shape."""
    if raw_voice is None:
        raw_voice = {}
        declared = False
    elif not isinstance(raw_voice, dict):
        raise ConfigError("'voice' must be a mapping")
    else:
        declared = True

    for key in ("enabled", "auto_submit", "tts_enabled", "status_announcements"):
        if key in raw_voice and not isinstance(raw_voice[key], bool):
            raise ConfigError(f"'voice.{key}' must be a boolean")

    raw_profiles = raw_voice.get("profiles")
    legacy = raw_profiles is None
    if legacy:
        profiles = [_legacy_voice_profile(raw_voice)]
    else:
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise ConfigError("'voice.profiles' must be a non-empty list")
        profiles = [_validate_voice_profile(entry, index) for index, entry in enumerate(raw_profiles)]

    ids = [profile["id"] for profile in profiles]
    if len(ids) != len(set(ids)):
        raise ConfigError("'voice.profiles' contains duplicate profile IDs")

    mode = _voice_string(raw_voice, "mode", "hold", path="voice")
    if mode not in {"hold", "continuous"}:
        raise ConfigError("'voice.mode' must be 'hold' or 'continuous'")
    primary = _voice_string(raw_voice, "primary_asr_profile", ids[0], path="voice")
    if primary not in ids:
        raise ConfigError("'voice.primary_asr_profile' references an unknown profile")

    raw_fallbacks = raw_voice.get("fallback_asr_profiles", [])
    if not isinstance(raw_fallbacks, list) or any(
        not isinstance(item, str) for item in raw_fallbacks
    ):
        raise ConfigError("'voice.fallback_asr_profiles' must be a list of strings")
    fallbacks = [item.strip() for item in raw_fallbacks if item.strip()]
    if len(fallbacks) != len(set(fallbacks)):
        raise ConfigError("'voice.fallback_asr_profiles' contains duplicate profile IDs")
    if any(item not in ids for item in fallbacks):
        raise ConfigError("'voice.fallback_asr_profiles' references an unknown profile")

    tts_enabled = bool(raw_voice.get("tts_enabled", False if legacy else False))
    # Legacy voice always included TTS; preserve its runtime behavior after loading.
    if legacy and declared:
        tts_enabled = bool(raw_voice.get("tts_enabled", True))
    tts_profile = _voice_string(
        raw_voice, "tts_profile", primary if tts_enabled else "", path="voice"
    )
    if tts_profile and tts_profile not in ids:
        raise ConfigError("'voice.tts_profile' references an unknown profile")
    if tts_enabled and not tts_profile:
        raise ConfigError("'voice.tts_profile' is required when TTS is enabled")

    silence = raw_voice.get("continuous_silence_ms", 900)
    if not isinstance(silence, int) or isinstance(silence, bool) or not 300 <= silence <= 6000:
        raise ConfigError("'voice.continuous_silence_ms' must be an integer from 300 to 6000")

    by_id = {profile["id"]: profile for profile in profiles}
    primary_profile = by_id[primary]
    if bool(raw_voice.get("enabled", False)):
        missing = [
            key
            for key in ("base_url", "batch_stt_model")
            if not primary_profile[key]
        ]
        if missing:
            raise ConfigError("Voice ASR configuration is missing: " + ", ".join(missing))
        if primary_profile["provider"] == "volcengine" and not primary_profile["app_id"]:
            raise ConfigError("Voice configuration is missing: app_id")
    if tts_enabled:
        selected = by_id[tts_profile]
        missing = [key for key in ("base_url", "tts_model", "voice") if not selected[key]]
        if missing:
            raise ConfigError("Voice TTS configuration is missing: " + ", ".join(missing))

    # Compatibility fields let the existing batch adapters run until all call sites use profiles.
    result = {
        "provider": primary_profile["provider"],
        "enabled": bool(raw_voice.get("enabled", False)),
        "base_url": primary_profile["base_url"],
        "api_key": primary_profile["api_key"],
        "app_id": primary_profile["app_id"],
        "secret_key": primary_profile["secret_key"],
        "stt_model": primary_profile["batch_stt_model"],
        "tts_model": by_id[tts_profile]["tts_model"] if tts_profile else "",
        "voice": by_id[tts_profile]["voice"] if tts_profile else "",
        "language": primary_profile["language"],
        "auto_submit": bool(raw_voice.get("auto_submit", False)),
        "mode": mode,
        "primary_asr_profile": primary,
        "fallback_asr_profiles": fallbacks,
        "tts_enabled": tts_enabled,
        "tts_profile": tts_profile,
        "status_announcements": bool(raw_voice.get("status_announcements", False)),
        "continuous_silence_ms": silence,
        "profiles": profiles,
        "_declared": declared,
        "_legacy": legacy and declared,
    }
    return result


def validate_config_structure(raw: object) -> dict:
    """校验的主入口。校验解析后的原始配置，返回清洗后的字典。

    返回的字典包含以下键：
        providers、permission_mode、mcp_servers、hooks、
        enable_fork、enable_verification_agent、worktree、
        teammate_mode、enable_coordinator_mode、sandbox、voice
    """
    if not isinstance(raw, dict) or "providers" not in raw:
        raise ConfigError("Config must contain a 'providers' list")

    return {
        "providers": validate_providers(raw["providers"]),
        "permission_mode": validate_permission_mode(raw.get("permission_mode", "default")),
        "mcp_servers": validate_mcp_servers(raw.get("mcp_servers")),
        "hooks": validate_hooks(raw.get("hooks")),
        "enable_fork": validate_bool_field(raw.get("enable_fork", False), "enable_fork"),
        "enable_verification_agent": validate_bool_field(
            raw.get("enable_verification_agent", False), "enable_verification_agent"
        ),
        "worktree": validate_worktree(raw.get("worktree")),
        "teammate_mode": validate_teammate_mode(raw.get("teammate_mode", "")),
        "enable_coordinator_mode": validate_bool_field(
            raw.get("enable_coordinator_mode", False), "enable_coordinator_mode"
        ),
        "sandbox": validate_sandbox(raw.get("sandbox")),
        "voice": validate_voice(raw.get("voice")),
    }
