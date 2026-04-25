#!/usr/bin/env python3
"""Minimal smoke test for the Codex CLI backend.

Purpose:
1. Verify the local ``codex`` CLI is callable from Python.
2. Verify ``CodexCliClient.complete()`` returns plain text.
3. Verify ``CodexCliClient.complete_json()`` returns parsed JSON.

Usage:
    python scripts/smoke_test_codex_backend.py
    python scripts/smoke_test_codex_backend.py --model gpt-5.4
    python scripts/smoke_test_codex_backend.py --timeout 180
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

# Allow running without editable install by adding src/ to sys.path.
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent / "src"))

from zh_ebn_report.clients.codex_cli import CodexCliClient  # noqa: E402
from zh_ebn_report.clients.system import CachedSystemBlock  # noqa: E402
from zh_ebn_report.config import LlmConfig  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke test the Codex CLI backend.")
    p.add_argument(
        "--model",
        default="gpt-5.4",
        help="Model id for sonnet/opus-tier requests; default: gpt-5.4",
    )
    p.add_argument(
        "--mini-model",
        default="gpt-5.4-mini",
        help="Model id for haiku-tier requests; default: gpt-5.4-mini",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="Per-subprocess timeout seconds; default: 180",
    )
    return p.parse_args()


async def _run(args: argparse.Namespace) -> int:
    if shutil.which("codex") is None:
        print("FAIL: `codex` not found on PATH", file=sys.stderr)
        return 2

    cfg = LlmConfig(
        backend="codex",
        api_key="",
        base_url=None,
        default_model=args.model,
        haiku_model=args.mini_model,
        sonnet_model=args.model,
        opus_model=args.model,
    )
    client = CodexCliClient(cfg, timeout_s=args.timeout)

    system = [
        CachedSystemBlock(
            text=(
                "You are a backend smoke test. "
                "Do not use tools. Follow the output instructions exactly."
            )
        )
    ]

    print("== complete() ==")
    text = await client.complete(
        tier="haiku",
        system_blocks=system,
        user_message="Reply with exactly: CODEx-SMOKE-OK",
    )
    print(text)

    print("\n== complete_json() ==")
    data = await client.complete_json(
        tier="sonnet",
        system_blocks=system,
        user_message=(
            'Return a JSON object with exactly two keys: '
            '"ok" set to true and "backend" set to "codex".'
        ),
    )
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if text.strip() != "CODEx-SMOKE-OK":
        print(
            "FAIL: complete() returned unexpected text",
            file=sys.stderr,
        )
        return 1

    if data != {"ok": True, "backend": "codex"}:
        print(
            "FAIL: complete_json() returned unexpected payload",
            file=sys.stderr,
        )
        return 1

    print("\nPASS: Codex CLI backend basic text + JSON round trips succeeded.")
    return 0


def main() -> int:
    args = _parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
