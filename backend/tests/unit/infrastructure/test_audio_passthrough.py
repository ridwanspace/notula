import struct
import wave
from pathlib import Path

import pytest

from notula.infrastructure.audio import PassthroughAudioProcessor


def _write_wav(path: Path, seconds: float, framerate: int = 16000) -> None:
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(framerate)
        writer.writeframes(struct.pack("<h", 1000) * int(seconds * framerate))


async def test_probe(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    _write_wav(src, 2.0)
    info = await PassthroughAudioProcessor().probe(src)
    assert info.duration_seconds == 2.0
    assert info.size_bytes == src.stat().st_size


async def test_normalize_copies_bytes(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    dst = tmp_path / "a.norm.flac"
    _write_wav(src, 1.0)
    info = await PassthroughAudioProcessor().normalize(src, dst)
    assert dst.read_bytes() == src.read_bytes()
    assert info.duration_seconds == 1.0
    assert info.size_bytes == dst.stat().st_size


async def test_slice(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    dst = tmp_path / "a.part.wav"
    _write_wav(src, 3.0)
    processor = PassthroughAudioProcessor()
    await processor.slice(src, dst, 0.5, 1.5)
    info = await processor.probe(dst)
    assert info.duration_seconds == pytest.approx(1.0)


async def test_detect_silences_is_empty(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    _write_wav(src, 1.0)
    assert await PassthroughAudioProcessor().detect_silences(src) == ()


async def test_non_wav_rejected_with_ffmpeg_hint(tmp_path: Path) -> None:
    src = tmp_path / "a.mp3"
    src.write_bytes(b"not audio at all")
    with pytest.raises(NotImplementedError, match="ffmpeg"):
        await PassthroughAudioProcessor().probe(src)
