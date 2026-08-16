"""Generate the deterministic demo recording (samples/demo/standup.wav).

Stdlib only, byte-identical across runs (fixed seed, fixed parameters).
The mock transcriber recognizes this exact file by content hash and returns
the bundled fixture transcript, so the offline demo produces a realistic
meeting summary without any API key.
"""

from __future__ import annotations

import hashlib
import math
import random
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 16000
DURATION_SECONDS = 60.0
_SEED = 20260816


def main(out_path: Path | None = None) -> Path:
    out = out_path or Path(__file__).resolve().parents[2] / "samples" / "demo" / "standup.wav"
    out.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(_SEED)  # noqa: S311 - deterministic audio, not crypto
    total_frames = int(SAMPLE_RATE * DURATION_SECONDS)
    frames = bytearray()
    cursor = 0
    while cursor < total_frames:
        # A "speech turn": a short vibrato tone burst, then a pause.
        burst = int(rng.uniform(2.0, 5.0) * SAMPLE_RATE)
        gap = int(rng.uniform(0.4, 1.2) * SAMPLE_RATE)
        freq = rng.uniform(150.0, 300.0)
        for i in range(min(burst, total_frames - cursor)):
            wobble = 1.0 + 0.08 * math.sin(2 * math.pi * 4.0 * i / SAMPLE_RATE)
            sample = int(0.3 * 32767 * math.sin(2 * math.pi * freq * wobble * i / SAMPLE_RATE))
            frames += struct.pack("<h", sample)
        cursor += burst
        for _ in range(min(gap, max(0, total_frames - cursor))):
            frames += struct.pack("<h", 0)
        cursor += gap

    frames = frames[: total_frames * 2]
    if len(frames) < total_frames * 2:
        frames += b"\x00" * (total_frames * 2 - len(frames))

    with wave.open(str(out), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(bytes(frames))

    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"{out} sha256={digest}")
    return out


if __name__ == "__main__":
    main()
