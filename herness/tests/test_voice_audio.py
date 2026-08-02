from __future__ import annotations

import struct

import pytest

from octocoder.voice.audio import encode_pcm16_wav, validate_pcm16


def test_encode_pcm16_wav_preserves_samples() -> None:
    pcm = struct.pack("<hhhh", -32768, -1, 0, 32767)
    wav = encode_pcm16_wav(pcm)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt "
    assert struct.unpack_from("<H", wav, 20)[0] == 1
    assert struct.unpack_from("<H", wav, 22)[0] == 1
    assert struct.unpack_from("<I", wav, 24)[0] == 16000
    assert struct.unpack_from("<H", wav, 34)[0] == 16
    assert wav[36:40] == b"data"
    assert struct.unpack_from("<I", wav, 40)[0] == len(pcm)
    assert wav[44:] == pcm


@pytest.mark.parametrize("pcm, message", [(b"", "empty"), (b"x", "complete")])
def test_validate_pcm16_rejects_invalid_input(pcm: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        validate_pcm16(pcm)


def test_validate_pcm16_enforces_size_limit() -> None:
    with pytest.raises(ValueError, match="size limit"):
        validate_pcm16(b"\x00\x00" * 3, max_bytes=4)


def test_encode_pcm16_wav_rejects_invalid_audio_parameters() -> None:
    with pytest.raises(ValueError, match="Sample rate"):
        encode_pcm16_wav(b"\x00\x00", sample_rate=0)
    with pytest.raises(ValueError, match="Channel"):
        encode_pcm16_wav(b"\x00\x00", channels=0)
