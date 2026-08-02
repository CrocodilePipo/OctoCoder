from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from octocoder.config import VoiceConfig, VoiceProviderProfile
from octocoder.voice.audio import encode_pcm16_wav
from octocoder.voice.factory import create_batch_asr_provider
from octocoder.voice.provider import BatchASRProvider, VoiceErrorKind, VoiceProviderError


@dataclass(frozen=True)
class FallbackResult:
    text: str
    profile_id: str
    provider: str


BatchFactory = Callable[[VoiceProviderProfile], BatchASRProvider]


def fallback_profiles(config: VoiceConfig) -> list[VoiceProviderProfile]:
    ordered = [config.primary_profile]
    ordered.extend(
        profile
        for profile_id in config.fallback_asr_profiles
        if (profile := config.get_profile(profile_id)) is not None
    )
    result: list[VoiceProviderProfile] = []
    seen: set[tuple[str, str, str]] = set()
    for profile in ordered:
        identity = (profile.provider, profile.base_url, profile.batch_stt_model)
        if identity in seen or not profile.batch_asr_configured:
            continue
        seen.add(identity)
        result.append(profile)
    return result


async def transcribe_with_fallback(
    config: VoiceConfig,
    pcm: bytes,
    streaming_error: VoiceProviderError,
    *,
    provider_factory: BatchFactory = create_batch_asr_provider,
) -> FallbackResult:
    if not streaming_error.retryable:
        raise streaming_error
    profiles = fallback_profiles(config)
    if not profiles:
        raise streaming_error
    wav = encode_pcm16_wav(pcm)
    failures: list[str] = []
    for profile in profiles:
        provider = provider_factory(profile)
        try:
            text = await provider.transcribe(
                wav,
                filename="recording.wav",
                content_type="audio/wav",
                language=profile.language,
            )
        except VoiceProviderError as exc:
            failures.append(f"{profile.name}: {str(exc)[:180]}")
            if not exc.retryable:
                raise exc
            continue
        if text.strip():
            return FallbackResult(
                text=text.strip(),
                profile_id=profile.id,
                provider=profile.provider,
            )
    detail = "; ".join(failures)[:500] or str(streaming_error)[:500]
    raise VoiceProviderError(
        f"Voice recognition fallback failed: {detail}",
        kind=VoiceErrorKind.SERVER,
        provider="fallback",
    )
