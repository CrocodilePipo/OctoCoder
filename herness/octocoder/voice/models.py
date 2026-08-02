from __future__ import annotations

from dataclasses import dataclass, field


MAX_RECORDING_SECONDS = 120
MAX_RECORDING_BYTES = 16 * 1024 * 1024
PCM_SAMPLE_RATE = 16_000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH = 2
MAX_PCM_FRAME_BYTES = 64 * 1024
MAX_PCM_QUEUE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class VoiceAudio:
    data: bytes
    content_type: str


@dataclass
class VoiceUpload:
    request_id: str
    mime_type: str
    started_at: float
    payload: bytearray = field(default_factory=bytearray)


@dataclass(frozen=True)
class TranscriptionEvent:
    type: str
    text: str = ""
    sentence_id: int = 0
    revision: int = 0
