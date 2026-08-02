from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from octocoder.config import ConfigError, VoiceConfig, VoiceProviderProfile, load_config
from octocoder.remote import RemoteServer
from octocoder.validator import validate_voice


def _provider() -> dict:
    return {
        "name": "test",
        "protocol": "openai-compat",
        "base_url": "https://example.test/v1",
        "model": "test-model",
        "api_key": "text-secret",
    }


def _write_config(path: Path, extra: dict | None = None) -> Path:
    payload = {"providers": [_provider()]}
    if extra:
        payload.update(extra)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_legacy_config_gets_disabled_voice_defaults(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path / "config.yaml"))
    assert config.voice.enabled is False
    assert config.voice.declared is False
    assert config.voice.base_url == "https://api.openai.com/v1"


def test_enabled_voice_config_loads(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path / "config.yaml",
            {
                "voice": {
                    "enabled": True,
                    "base_url": "https://voice.example/v1/",
                    "api_key": "voice-secret",
                    "stt_model": "stt-model",
                    "tts_model": "tts-model",
                    "voice": "speaker",
                    "language": "zh",
                    "auto_submit": True,
                }
            },
        )
    )
    assert config.voice.configured is True
    assert config.voice.auto_submit is True
    assert config.voice.language == "zh"


def test_profile_asr_only_loads_without_tts(tmp_path: Path) -> None:
    config = load_config(
        _write_config(
            tmp_path / "config.yaml",
            {
                "voice": {
                    "enabled": True,
                    "primary_asr_profile": "aliyun-main",
                    "tts_enabled": False,
                    "profiles": [
                        {
                            "id": "aliyun-main",
                            "name": "Aliyun",
                            "provider": "aliyun",
                            "api_key": "voice-secret",
                            "batch_stt_model": "qwen3-asr-flash",
                            "streaming_stt_model": "qwen-audio-3.0-asr-flash-streaming",
                            "tts_model": "",
                            "voice": "",
                        }
                    ],
                }
            },
        )
    )
    assert config.voice.configured is True
    assert config.voice.streaming_configured is True
    assert config.voice.tts_configured is False
    assert config.voice.selected_tts_profile is None


def test_tts_readiness_is_independent_from_asr() -> None:
    profile = VoiceProviderProfile(api_key="secret", tts_model="", voice="")
    config = VoiceConfig(enabled=True, tts_enabled=False, profiles=[profile])
    assert config.configured is True
    assert config.tts_configured is False
    config.tts_enabled = True
    config.tts_profile = "default"
    assert config.configured is True
    assert config.tts_configured is False


def test_legacy_voice_load_does_not_rewrite_file(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path / "config.yaml",
        {"voice": {"enabled": True, "api_key": "legacy-secret"}},
    )
    before = path.read_bytes()
    config = load_config(path)
    assert config.voice.legacy is True
    assert config.voice.primary_profile.id == "default"
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "voice, message",
    [
        (
            {
                "profiles": [
                    {"id": "same", "provider": "aliyun"},
                    {"id": "same", "provider": "openai"},
                ]
            },
            "duplicate",
        ),
        (
            {
                "profiles": [{"id": "one", "provider": "aliyun"}],
                "primary_asr_profile": "missing",
            },
            "unknown profile",
        ),
        (
            {
                "profiles": [{"id": "one", "provider": "aliyun"}],
                "fallback_asr_profiles": ["missing"],
            },
            "unknown profile",
        ),
        (
            {
                "profiles": [{"id": "one", "provider": "aliyun"}],
                "tts_enabled": True,
                "tts_profile": "missing",
            },
            "unknown profile",
        ),
    ],
)
def test_profile_validation_rejects_invalid_references(voice, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        validate_voice(voice)


@pytest.mark.parametrize(
    "provider,base_url,stt_model,tts_model",
    [
        (
            "siliconflow",
            "https://api.siliconflow.cn/v1",
            "FunAudioLLM/SenseVoiceSmall",
            "FunAudioLLM/CosyVoice2-0.5B",
        ),
        (
            "aliyun",
            "https://dashscope.aliyuncs.com",
            "qwen3-asr-flash",
            "qwen-audio-3.0-tts-flash",
        ),
        (
            "volcengine",
            "https://openspeech.bytedance.com",
            "volc.bigasr.auc_turbo",
            "seed-tts-1.1",
        ),
    ],
)
def test_voice_provider_presets(provider, base_url, stt_model, tts_model) -> None:
    validated = validate_voice({"provider": provider, "enabled": False})
    assert validated["provider"] == provider
    assert validated["base_url"] == base_url
    assert validated["stt_model"] == stt_model
    assert validated["tts_model"] == tts_model


def test_voice_validation_rejects_unknown_provider() -> None:
    with pytest.raises(ConfigError, match="Invalid voice provider"):
        validate_voice({"provider": "unknown"})


def test_enabled_voice_accepts_environment_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOCODER_VOICE_API_KEY", "environment-secret")
    config = load_config(
        _write_config(tmp_path / "config.yaml", {"voice": {"enabled": True}})
    )
    assert config.voice.resolve_api_key() == "environment-secret"
    assert config.voice.configured is True


def test_enabled_voice_requires_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OCTOCODER_VOICE_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="Voice API key"):
        load_config(
            _write_config(tmp_path / "config.yaml", {"voice": {"enabled": True}})
        )


def test_enabled_volcengine_requires_app_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OCTOCODER_VOICE_API_KEY", "test-access-token")
    monkeypatch.delenv("OCTOCODER_VOICE_APP_ID", raising=False)
    with pytest.raises(ConfigError, match="app_id"):
        load_config(
            _write_config(
                tmp_path / "config.yaml",
                {"voice": {"provider": "volcengine", "enabled": True}},
            )
        )


def test_enabled_volcengine_rejects_reversed_credentials() -> None:
    with pytest.raises(ConfigError, match="may be reversed"):
        validate_voice(
            {
                "provider": "volcengine",
                "enabled": True,
                "api_key": "1234567890",
                "app_id": "test-access-token-value",
            }
        )


@pytest.mark.parametrize(
    "raw, message",
    [
        ([], "mapping"),
        ({"enabled": "yes"}, "boolean"),
        ({"auto_submit": 1}, "boolean"),
        ({"stt_model": 42}, "string"),
        ({"enabled": True, "base_url": ""}, "base_url"),
    ],
)
def test_voice_validation_rejects_invalid_values(raw, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        validate_voice(raw)


def test_voice_config_environment_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OCTOCODER_VOICE_API_KEY", "environment-secret")
    config = VoiceConfig(enabled=True)
    assert config.resolve_api_key() == "environment-secret"
    assert config.configured is True


def test_remote_status_redacts_voice_key(tmp_path: Path) -> None:
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    server.voice_config = VoiceConfig(
        enabled=True,
        api_key="super-secret",
        declared=True,
    )
    status = server._config_status()
    assert status["voice"]["provider"] == "openai-compatible"
    assert status["voice"]["apiKeyConfigured"] is True
    assert "super-secret" not in repr(status)


def test_remote_status_redacts_volcengine_credentials(tmp_path: Path) -> None:
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    server.voice_config = VoiceConfig(
        provider="volcengine",
        enabled=True,
        api_key="test-access-token",
        app_id="test-app-id",
        secret_key="test-secret-key",
        declared=True,
    )
    status = server._config_status()
    voice = status["voice"]
    assert voice["apiKeyConfigured"] is True
    assert voice["appIdConfigured"] is True
    assert voice["secretKeyConfigured"] is True
    rendered = repr(status)
    assert "test-access-token" not in rendered
    assert "test-app-id" not in rendered
    assert "test-secret-key" not in rendered


def test_remote_save_preserves_volcengine_credentials(tmp_path: Path) -> None:
    config_dir = tmp_path / ".octocoder"
    config_dir.mkdir()
    _write_config(
        config_dir / "config.yaml",
        {
            "voice": {
                "provider": "volcengine",
                "enabled": True,
                "api_key": "saved-access-token",
                "app_id": "1234567890",
                "secret_key": "saved-secret-key",
            }
        },
    )
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    server._write_config(
        {
            "name": "test",
            "protocol": "openai-compat",
            "baseUrl": "https://example.test/v1",
            "model": "test-model",
            "apiKey": "text-secret",
            "permissionMode": "default",
            "voice": {
                "provider": "volcengine",
                "enabled": True,
                "baseUrl": "https://openspeech.bytedance.com",
                "apiKey": "",
                "appId": "",
                "secretKey": "",
                "sttModel": "volc.bigasr.auc_turbo",
                "ttsModel": "seed-tts-1.1",
                "voice": "zh_female_cancan_mars_bigtts",
                "language": "zh",
                "autoSubmit": False,
            },
        }
    )
    raw = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))
    assert raw["voice"]["api_key"] == "saved-access-token"
    assert raw["voice"]["app_id"] == "1234567890"
    assert raw["voice"]["secret_key"] == "saved-secret-key"


def test_remote_save_preserves_existing_voice_key(tmp_path: Path) -> None:
    config_dir = tmp_path / ".octocoder"
    config_dir.mkdir()
    _write_config(
        config_dir / "config.yaml",
        {
            "voice": {
                "provider": "siliconflow",
                "enabled": True,
                "api_key": "preserved-secret",
            }
        },
    )
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    server._write_config(
        {
            "name": "test",
            "protocol": "openai-compat",
            "baseUrl": "https://example.test/v1",
            "model": "test-model",
            "apiKey": "text-secret",
            "permissionMode": "default",
            "voice": {
                "enabled": True,
                "baseUrl": "https://voice.example/v1",
                "apiKey": "",
                "sttModel": "stt-model",
                "ttsModel": "tts-model",
                "voice": "speaker",
                "language": "zh",
                "autoSubmit": False,
            },
        }
    )
    raw = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))
    assert raw["voice"]["api_key"] == "preserved-secret"
    assert raw["voice"]["provider"] == "siliconflow"


def test_remote_save_migrates_profiles_and_preserves_each_secret(tmp_path: Path) -> None:
    config_dir = tmp_path / ".octocoder"
    config_dir.mkdir()
    _write_config(
        config_dir / "config.yaml",
        {
            "voice": {
                "provider": "aliyun",
                "enabled": True,
                "api_key": "legacy-aliyun-secret",
            }
        },
    )
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    server._write_config(
        {
            "name": "test",
            "protocol": "openai-compat",
            "baseUrl": "https://example.test/v1",
            "model": "test-model",
            "apiKey": "text-secret",
            "permissionMode": "default",
            "voice": {
                "enabled": True,
                "mode": "hold",
                "primaryAsrProfile": "default",
                "fallbackAsrProfiles": ["backup"],
                "ttsEnabled": False,
                "ttsProfile": "",
                "statusAnnouncements": False,
                "continuousSilenceMs": 900,
                "profiles": [
                    {
                        "id": "default",
                        "name": "Aliyun",
                        "provider": "aliyun",
                        "baseUrl": "https://dashscope.aliyuncs.com",
                        "streamingUrl": "wss://dashscope.aliyuncs.com/api-ws/v1/inference",
                        "apiKey": "",
                        "batchSttModel": "qwen3-asr-flash",
                        "streamingSttModel": "qwen-audio-3.0-asr-flash-streaming",
                        "ttsModel": "",
                        "voice": "",
                        "language": "zh",
                    },
                    {
                        "id": "backup",
                        "name": "Backup",
                        "provider": "openai-compatible",
                        "baseUrl": "https://voice.example/v1",
                        "streamingUrl": "",
                        "apiKey": "backup-secret",
                        "batchSttModel": "backup-asr",
                        "streamingSttModel": "",
                        "ttsModel": "",
                        "voice": "",
                        "language": "zh",
                    },
                ],
            },
        }
    )
    raw = yaml.safe_load((config_dir / "config.yaml").read_text(encoding="utf-8"))
    assert "provider" not in raw["voice"]
    assert raw["voice"]["profiles"][0]["api_key"] == "legacy-aliyun-secret"
    assert raw["voice"]["profiles"][1]["api_key"] == "backup-secret"
    loaded = load_config(config_dir / "config.yaml")
    assert loaded.voice.primary_asr_profile == "default"
    assert loaded.voice.fallback_asr_profiles == ["backup"]


def test_profile_status_redacts_all_secrets(tmp_path: Path) -> None:
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    server.voice_config = VoiceConfig(
        enabled=True,
        tts_enabled=True,
        tts_profile="backup",
        profiles=[
            VoiceProviderProfile(
                id="default",
                provider="aliyun",
                api_key="primary-secret",
                streaming_url="wss://dashscope.aliyuncs.com/api-ws/v1/inference",
                streaming_stt_model="qwen-audio-3.0-asr-flash-streaming",
            ),
            VoiceProviderProfile(
                id="backup",
                provider="volcengine",
                api_key="backup-secret",
                app_id="1234567890",
                secret_key="secondary-secret",
            ),
        ],
        declared=True,
    )
    status = server._voice_status()
    assert status["configured"] is True
    assert status["streamingConfigured"] is True
    assert status["ttsConfigured"] is True
    assert len(status["profiles"]) == 2
    rendered = repr(status)
    for secret in ("primary-secret", "backup-secret", "1234567890", "secondary-secret"):
        assert secret not in rendered


def test_remote_rejects_unknown_provider_without_overwriting_config(tmp_path: Path) -> None:
    config_dir = tmp_path / ".octocoder"
    config_dir.mkdir()
    config_path = _write_config(config_dir / "config.yaml")
    original = config_path.read_text(encoding="utf-8")
    server = RemoteServer(providers=[])
    server.config_dir = tmp_path
    with pytest.raises(ConfigError, match="Invalid voice provider"):
        server._write_config(
            {
                "name": "test",
                "protocol": "openai-compat",
                "baseUrl": "https://example.test/v1",
                "model": "test-model",
                "apiKey": "text-secret",
                "permissionMode": "default",
                "voice": {
                    "provider": "unknown",
                    "enabled": False,
                },
            }
        )
    assert config_path.read_text(encoding="utf-8") == original
