from __future__ import annotations

import httpx

from octocoder.config import VoiceConfig, VoiceProviderProfile
from octocoder.voice.aliyun import AliyunVoiceProvider
from octocoder.voice.aliyun_streaming import AliyunStreamingASRProvider
from octocoder.voice.openai_compatible import OpenAICompatibleVoiceProvider
from octocoder.voice.provider import (
    BatchASRProvider,
    StreamingASRProvider,
    TTSProvider,
    VoiceErrorKind,
    VoiceProvider,
    VoiceProviderError,
)


def _profile_config(profile: VoiceProviderProfile) -> VoiceConfig:
    return VoiceConfig(
        provider=profile.provider,
        enabled=True,
        base_url=profile.base_url,
        api_key=profile.api_key,
        app_id=profile.app_id,
        secret_key=profile.secret_key,
        stt_model=profile.batch_stt_model,
        tts_model=profile.tts_model,
        voice=profile.voice,
        language=profile.language,
        primary_asr_profile=profile.id,
        tts_enabled=True,
        tts_profile=profile.id,
        profiles=[profile],
        declared=True,
    )


def _create_provider(
    profile: VoiceProviderProfile,
    *,
    client: httpx.AsyncClient | None = None,
) -> VoiceProvider:
    config = _profile_config(profile)
    if profile.provider == "aliyun":
        return AliyunVoiceProvider(config, client=client)
    if profile.provider == "siliconflow":
        return SiliconFlowVoiceProvider(config, client=client)
    if profile.provider == "volcengine":
        return VolcengineVoiceProvider(config, client=client)
    return OpenAICompatibleVoiceProvider(config, client=client)
from octocoder.voice.siliconflow import SiliconFlowVoiceProvider
from octocoder.voice.volcengine import VolcengineVoiceProvider


def create_voice_provider(
    config: VoiceConfig,
    *,
    client: httpx.AsyncClient | None = None,
) -> VoiceProvider:
    return _create_provider(config.primary_profile, client=client)


def create_batch_asr_provider(
    profile: VoiceProviderProfile,
    *,
    client: httpx.AsyncClient | None = None,
) -> BatchASRProvider:
    return _create_provider(profile, client=client)


def create_tts_provider(
    profile: VoiceProviderProfile,
    *,
    client: httpx.AsyncClient | None = None,
) -> TTSProvider:
    return _create_provider(profile, client=client)


def create_streaming_asr_provider(
    profile: VoiceProviderProfile,
    *,
    connector=None,
) -> StreamingASRProvider:
    if profile.provider != "aliyun" or not profile.streaming_url or not profile.streaming_stt_model:
        raise VoiceProviderError(
            f"Voice profile '{profile.id}' does not support streaming ASR",
            kind=VoiceErrorKind.INVALID_REQUEST,
            provider=profile.provider,
        )
    return AliyunStreamingASRProvider(profile, connector=connector)
