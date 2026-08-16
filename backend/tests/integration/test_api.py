"""Full-stack offline tests: real HTTP surface, real SQLite, mock providers."""

from __future__ import annotations

import asyncio
import io
import struct
import wave
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from notula.infrastructure.settings import Settings
from notula.main import build_app


def make_wav(seconds: float = 1.0, *, seed: int = 7) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        n = int(16000 * seconds)
        out.writeframes(
            b"".join(struct.pack("<h", (i * seed * 37) % 8000 - 4000) for i in range(n))
        )
    return buffer.getvalue()


async def make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str
) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("NOTULA_PROVIDER", "mock")
    monkeypatch.setenv("NOTULA_DATA_DIR", str(tmp_path / "data"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    app = build_app(Settings())
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[httpx.AsyncClient]:
    async for c in make_client(tmp_path, monkeypatch):
        yield c


async def submit(client: httpx.AsyncClient, *, language: str = "en", roster: str = "") -> str:
    response = await client.post(
        "/api/meetings",
        files={"file": ("standup.wav", make_wav(), "audio/wav")},
        data={"roster": roster, "language": language},
    )
    assert response.status_code == 202, response.text
    meeting_id = response.json()["id"]
    assert isinstance(meeting_id, str)
    return meeting_id


async def wait_terminal(client: httpx.AsyncClient, meeting_id: str) -> dict[str, object]:
    deadline = asyncio.get_running_loop().time() + 10
    while asyncio.get_running_loop().time() < deadline:
        detail = (await client.get(f"/api/meetings/{meeting_id}")).json()
        if detail["meeting"]["state"] in ("completed", "failed"):
            return detail  # type: ignore[no-any-return]
        await asyncio.sleep(0.05)
    raise AssertionError("meeting did not reach a terminal state in time")


async def test_full_pipeline_offline(client: httpx.AsyncClient) -> None:
    meeting_id = await submit(client, roster="Rina, Dimas")
    detail = await wait_terminal(client, meeting_id)

    meeting = detail["meeting"]
    assert meeting["state"] == "completed", meeting["error"]
    assert meeting["duration_seconds"] == pytest.approx(1.0, abs=0.05)

    transcript = detail["transcript"]
    assert transcript is not None and transcript["utterances"]

    summary = detail["summary"]
    assert summary is not None
    assert summary["model"] == "mock"
    assert summary["version"] == 1
    assert summary["title"]

    stages = {s["stage"]: s for s in detail["stages"]}
    assert set(stages) == {"normalize", "transcribe", "summarize"}
    assert stages["transcribe"]["input_tokens"] > 0
    assert stages["transcribe"]["cost_usd"] == 0.0  # mock is priced at zero, not unknown
    assert all(s["seconds"] >= 0 for s in stages.values())

    listing = (await client.get("/api/meetings")).json()["meetings"]
    assert any(m["id"] == meeting_id for m in listing)

    audio = await client.get(f"/api/meetings/{meeting_id}/audio")
    assert audio.status_code == 200
    assert audio.content == make_wav()


async def test_sse_stream_reaches_completed(client: httpx.AsyncClient) -> None:
    meeting_id = await submit(client)
    kinds: list[str] = []
    async with client.stream("GET", f"/api/meetings/{meeting_id}/events") as stream:
        async for line in stream.aiter_lines():
            if line.startswith("event: "):
                kinds.append(line.removeprefix("event: "))
    assert kinds[0] == "state"
    assert kinds[-1] == "completed"
    assert "error" not in kinds


async def test_resummarize_creates_new_version(client: httpx.AsyncClient) -> None:
    meeting_id = await submit(client)
    await wait_terminal(client, meeting_id)

    response = await client.post(f"/api/meetings/{meeting_id}/summaries", json={"language": "id"})
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert response.json()["language"] == "id"

    detail = (await client.get(f"/api/meetings/{meeting_id}")).json()
    assert detail["summary"]["version"] == 2
    assert detail["meeting"]["state"] == "completed"


async def test_deterministic_mock_same_audio_same_summary(client: httpx.AsyncClient) -> None:
    first = await wait_terminal(client, await submit(client))
    second = await wait_terminal(client, await submit(client))
    assert first["transcript"] == second["transcript"]
    assert first["summary"]["tldr"] == second["summary"]["tldr"]


async def test_validation_errors(client: httpx.AsyncClient) -> None:
    bad_type = await client.post(
        "/api/meetings", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert bad_type.status_code == 415

    empty = await client.post("/api/meetings", files={"file": ("empty.wav", b"", "audio/wav")})
    assert empty.status_code == 400

    bad_language = await client.post(
        "/api/meetings",
        files={"file": ("a.wav", make_wav(0.2), "audio/wav")},
        data={"language": "fr"},
    )
    assert bad_language.status_code == 422

    assert (await client.get("/api/meetings/nope")).status_code == 404
    assert (await client.get("/api/meetings/nope/events")).status_code == 404
    assert (await client.get("/api/meetings/nope/audio")).status_code == 404
    missing = await client.post("/api/meetings/nope/summaries", json={"language": "en"})
    assert missing.status_code == 404


async def test_upload_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async for client in make_client(tmp_path, monkeypatch, NOTULA_MAX_UPLOAD_BYTES="1000"):
        response = await client.post(
            "/api/meetings", files={"file": ("big.wav", make_wav(1.0), "audio/wav")}
        )
        assert response.status_code == 413


async def test_healthz_reports_provider(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.json() == {"status": "ok", "provider": "mock"}


async def test_index_serves_ui(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "Notula" in response.text
