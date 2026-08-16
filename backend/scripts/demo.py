"""End-to-end demo: submit the bundled sample, stream progress, print the summary.

Runs fully offline against the deterministic mock provider by default:

    uv run python scripts/demo.py

Pass --live to use Gemini + DeepSeek (requires GEMINI_API_KEY and
DEEPSEEK_API_KEY in the repo-root .env), and --language id for Bahasa
Indonesia output.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE = REPO_ROOT / "samples" / "demo" / "standup.wav"


def _print_summary(detail: dict[str, object]) -> None:
    summary = detail["summary"]
    assert isinstance(summary, dict)
    print(f"\n=== {summary['title']} ===")
    print(f"\nTL;DR: {summary['tldr']}")
    for heading, key in (
        ("Key points", "key_points"),
        ("Decisions", "decisions"),
        ("Open questions", "open_questions"),
    ):
        items = summary[key]
        assert isinstance(items, list)
        print(f"\n{heading}:")
        for item in items or ["(none)"]:
            print(f"  - {item}")
    actions = summary["action_items"]
    assert isinstance(actions, list)
    print("\nAction items:")
    for action in actions or [{"task": "(none)", "owner": None, "due": None}]:
        assert isinstance(action, dict)
        owner = action["owner"] or "—"
        due = action["due"] or "—"
        print(f"  - {action['task']}  (owner: {owner}, due: {due})")

    stages = detail["stages"]
    assert isinstance(stages, list)
    print(f"\n{'stage':<12}{'seconds':>9}{'in tok':>9}{'out tok':>9}{'model':>20}{'cost':>11}")
    total_cost = 0.0
    for stage in stages:
        assert isinstance(stage, dict)
        cost = stage["cost_usd"]
        cost_text = f"${cost:.6f}" if isinstance(cost, int | float) else "n/a"
        if isinstance(cost, int | float):
            total_cost += cost
        print(
            f"{stage['stage']:<12}{stage['seconds']:>9.2f}{stage['input_tokens']:>9}"
            f"{stage['output_tokens']:>9}{stage['model']:>20}{cost_text:>11}"
        )
    print(f"{'total':<12}{'':>9}{'':>9}{'':>9}{'':>20}{f'${total_cost:.6f}':>11}")


async def run(language: str) -> int:
    from notula.infrastructure.settings import Settings
    from notula.main import build_app

    settings = Settings()
    app = build_app(settings)
    print(f"provider: {settings.provider}")
    if not SAMPLE.is_file():
        print(f"sample missing: {SAMPLE} (run scripts/make_demo_audio.py)", file=sys.stderr)
        return 1

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://demo", timeout=600
        ) as client:
            started = time.perf_counter()
            response = await client.post(
                "/api/meetings",
                files={"file": (SAMPLE.name, SAMPLE.read_bytes(), "audio/wav")},
                data={"roster": "Rina, Dimas", "language": language},
            )
            response.raise_for_status()
            meeting_id = response.json()["id"]
            print(f"meeting {meeting_id} submitted; streaming events:")

            failed = False
            async with client.stream("GET", f"/api/meetings/{meeting_id}/events") as stream:
                kind = ""
                async for line in stream.aiter_lines():
                    if line.startswith("event: "):
                        kind = line.removeprefix("event: ")
                    elif line.startswith("data: "):
                        data = json.loads(line.removeprefix("data: "))
                        elapsed = time.perf_counter() - started
                        print(f"  [{elapsed:6.2f}s] {kind}: {data}")
                        failed = failed or kind == "error"

            detail = (await client.get(f"/api/meetings/{meeting_id}")).json()
            if failed or detail["summary"] is None:
                print(f"pipeline failed: {detail['meeting']['error']}", file=sys.stderr)
                return 1
            _print_summary(detail)
            return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="use Gemini + DeepSeek")
    parser.add_argument("--language", choices=("en", "id"), default="en")
    args = parser.parse_args()
    os.environ["NOTULA_PROVIDER"] = "live" if args.live else "mock"
    return asyncio.run(run(args.language))


if __name__ == "__main__":
    raise SystemExit(main())
