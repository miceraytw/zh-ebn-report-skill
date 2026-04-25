"""Codex CLI LLM backend.

Shells out to ``codex exec`` and captures the final assistant message from a
temporary output file. This backend mirrors the existing Claude CLI backend:
one subprocess per LLM call, shared ``complete`` / ``complete_json`` surface,
and deterministic prompt assembly from cached system blocks.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Literal

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import LlmConfig
from .system import CachedSystemBlock

ModelTier = Literal["haiku", "sonnet", "opus"]

_DEFAULT_SUBPROCESS_TIMEOUT_S = 300


class CodexCliError(RuntimeError):
    """Raised when ``codex exec`` exits non-zero or yields no final message."""


class CodexCliClient:
    """Drop-in ``LLMClient`` backed by ``codex exec``."""

    def __init__(
        self,
        cfg: LlmConfig,
        *,
        codex_bin: str | None = None,
        timeout_s: int = _DEFAULT_SUBPROCESS_TIMEOUT_S,
    ):
        self._cfg = cfg
        self._codex_bin = codex_bin or os.getenv("CODEX_BIN") or "codex"
        self._timeout_s = timeout_s

    def model_for(self, tier: ModelTier) -> str:
        mapping = {
            "haiku": self._cfg.haiku_model,
            "sonnet": self._cfg.sonnet_model,
            "opus": self._cfg.opus_model,
        }
        return mapping[tier]

    async def complete(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,  # noqa: ARG002  codex CLI has no token flag here
        temperature: float = 0.2,  # noqa: ARG002  codex CLI has no temperature flag
        json_mode: bool = False,
    ) -> str:
        prompt = _build_exec_prompt(system_blocks, user_message, json_mode=json_mode)
        model = self.model_for(tier)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type((TimeoutError, CodexCliError)),
            reraise=True,
        ):
            with attempt:
                return await self._exec_once(model=model, prompt=prompt)
        raise CodexCliError("exhausted retries without a response")

    async def complete_json(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        raw = await self.complete(
            tier=tier,
            system_blocks=system_blocks,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
        return _parse_model_json(raw)

    async def _exec_once(self, *, model: str, prompt: str) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".txt",
            delete=False,
        ) as out_file:
            out_path = Path(out_file.name)

        try:
            proc = await asyncio.create_subprocess_exec(
                self._codex_bin,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--model",
                model,
                "--output-last-message",
                str(out_path),
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(input=prompt.encode("utf-8")),
                    timeout=self._timeout_s,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise
        finally:
            stderr = ""
            if "stderr_b" in locals():
                stderr = stderr_b.decode("utf-8", errors="replace")

        try:
            if proc.returncode != 0:
                raise CodexCliError(
                    f"codex exec exited {proc.returncode}: {stderr[:400]}"
                )
            if not out_path.exists():
                raise CodexCliError("codex exec produced no output-last-message file")
            result = out_path.read_text(encoding="utf-8").strip()
            if not result:
                raise CodexCliError("codex exec produced an empty final message")
            return result
        finally:
            out_path.unlink(missing_ok=True)


def _concatenate_system_blocks(blocks: list[CachedSystemBlock]) -> str:
    return "\n\n".join(block.text for block in blocks)


def _build_exec_prompt(
    system_blocks: list[CachedSystemBlock],
    user_message: str,
    *,
    json_mode: bool,
) -> str:
    prompt = (
        "You are the LLM backend for the zh-ebn-report pipeline.\n"
        "Follow the system instructions exactly.\n"
        "Do not run shell commands or inspect the workspace.\n"
        "Reply with the final answer only.\n\n"
        "<system>\n"
        f"{_concatenate_system_blocks(system_blocks)}\n"
        "</system>\n\n"
        "<user>\n"
        f"{user_message}\n"
        "</user>\n"
    )
    if json_mode:
        prompt += (
            "\nReturn valid JSON only. Do not include markdown fences or extra explanation.\n"
        )
    return prompt


def _parse_model_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
