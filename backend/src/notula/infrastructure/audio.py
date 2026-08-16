"""Audio adapters: ffmpeg when available, a stdlib WAV passthrough otherwise.

The passthrough keeps `git clone && make demo` honest on machines without
ffmpeg: it handles RIFF WAV via the stdlib `wave` module and refuses anything
else with a message that names the fix.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import wave
from pathlib import Path

from notula.application.ports import AudioInfo, AudioProcessor

_SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")


# Sync helpers: these are small local files; blocking the loop for them is fine
# and keeps the adapters free of an async-filesystem dependency (ASYNC240).
def _size(path: Path) -> int:
    return path.stat().st_size


def _copy_bytes(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(src.read_bytes())


async def _run(*argv: str) -> tuple[bytes, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = stderr.decode(errors="replace")[-500:]
        raise RuntimeError(f"{argv[0]} failed ({proc.returncode}): {tail}")
    return stdout, stderr


class FfmpegAudioProcessor:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe

    async def probe(self, path: Path) -> AudioInfo:
        stdout, _ = await _run(
            self._ffprobe, "-v", "error", "-print_format", "json", "-show_format", str(path)
        )
        info = json.loads(stdout)
        duration = float(info.get("format", {}).get("duration", 0.0))
        return AudioInfo(duration_seconds=duration, size_bytes=_size(path))

    async def normalize(self, src: Path, dst: Path) -> AudioInfo:
        """Pipeline-standard format: 16 kHz mono s16 (container from dst suffix)."""
        await _run(
            self._ffmpeg,
            "-y",
            "-i",
            str(src),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-sample_fmt",
            "s16",
            str(dst),
        )
        return await self.probe(dst)

    async def detect_silences(self, path: Path) -> tuple[float, ...]:
        _, stderr = await _run(
            self._ffmpeg,
            "-i",
            str(path),
            "-af",
            "silencedetect=noise=-30dB:d=0.5",
            "-f",
            "null",
            "-",
        )
        text = stderr.decode(errors="replace")
        starts = [float(m) for m in _SILENCE_START.findall(text)]
        ends = [float(m) for m in _SILENCE_END.findall(text)]
        return tuple((start + end) / 2 for start, end in zip(starts, ends, strict=False))

    async def slice(self, src: Path, dst: Path, start_seconds: float, end_seconds: float) -> None:
        # -ss before -i seeks the input; -t is the segment length (re-encode, no -c copy,
        # so cuts land exactly on the requested times rather than on packet boundaries).
        await _run(
            self._ffmpeg,
            "-y",
            "-ss",
            str(start_seconds),
            "-t",
            str(end_seconds - start_seconds),
            "-i",
            str(src),
            str(dst),
        )


class PassthroughAudioProcessor:
    """WAV-only fallback used when ffmpeg is absent (and by the offline demo)."""

    def _params(self, path: Path) -> wave._wave_params:
        try:
            with wave.open(str(path), "rb") as reader:
                return reader.getparams()
        except (wave.Error, EOFError) as exc:
            raise NotImplementedError(
                f"{path.name} is not a RIFF WAV; install ffmpeg to process other formats"
            ) from exc

    async def probe(self, path: Path) -> AudioInfo:
        params = self._params(path)
        return AudioInfo(
            duration_seconds=params.nframes / params.framerate,
            size_bytes=_size(path),
        )

    async def normalize(self, src: Path, dst: Path) -> AudioInfo:
        # No resampling without ffmpeg: the source WAV is copied unchanged.
        self._params(src)  # reject non-WAV input early
        _copy_bytes(src, dst)
        info = await self.probe(src)
        return AudioInfo(duration_seconds=info.duration_seconds, size_bytes=_size(dst))

    async def detect_silences(self, path: Path) -> tuple[float, ...]:
        return ()

    async def slice(self, src: Path, dst: Path, start_seconds: float, end_seconds: float) -> None:
        # Writes WAV bytes even if dst carries a .flac suffix; downstream mock
        # providers hash bytes and never parse the container.
        with wave.open(str(src), "rb") as reader:
            params = reader.getparams()
            reader.setpos(int(start_seconds * params.framerate))
            frames = reader.readframes(int((end_seconds - start_seconds) * params.framerate))
        dst.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(dst), "wb") as writer:
            writer.setnchannels(params.nchannels)
            writer.setsampwidth(params.sampwidth)
            writer.setframerate(params.framerate)
            writer.writeframes(frames)


def pick_audio_processor() -> AudioProcessor:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return FfmpegAudioProcessor()
    return PassthroughAudioProcessor()
