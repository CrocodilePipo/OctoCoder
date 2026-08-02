from __future__ import annotations

import struct

from octocoder.voice.models import (
    MAX_RECORDING_BYTES,
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    PCM_SAMPLE_WIDTH,
)


def validate_pcm16(pcm: bytes, *, max_bytes: int = MAX_RECORDING_BYTES) -> None:
    if not pcm:
        raise ValueError("PCM audio is empty")
    if len(pcm) % PCM_SAMPLE_WIDTH:
        raise ValueError("PCM16 audio must contain complete 16-bit samples")
    if len(pcm) > max_bytes:
        raise ValueError("PCM audio exceeds the recording size limit")


def encode_pcm16_wav(
    pcm: bytes,
    *,
    sample_rate: int = PCM_SAMPLE_RATE,
    channels: int = PCM_CHANNELS,
) -> bytes:
    validate_pcm16(pcm)
    if sample_rate <= 0:
        raise ValueError("Sample rate must be positive")
    if channels <= 0:
        raise ValueError("Channel count must be positive")
    block_align = channels * PCM_SAMPLE_WIDTH
    byte_rate = sample_rate * block_align
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        PCM_SAMPLE_WIDTH * 8,
        b"data",
        len(pcm),
    )
    return header + pcm
