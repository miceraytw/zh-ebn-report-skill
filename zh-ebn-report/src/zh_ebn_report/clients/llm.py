"""Backend-agnostic LLM client protocol + factory."""

from __future__ import annotations

import shutil
from typing import Any, Literal, Protocol

from ..config import LlmConfig
from .system import CachedSystemBlock

ModelTier = Literal["haiku", "sonnet", "opus"]


class LLMClient(Protocol):
    """Minimum surface the pipeline expects from an LLM backend."""

    def model_for(self, tier: ModelTier) -> str: ...

    async def complete(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[Any],
        user_message: str,
        max_tokens: int = ...,
        temperature: float = ...,
        json_mode: bool = ...,
    ) -> str: ...

    async def complete_json(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[Any],
        user_message: str,
        max_tokens: int = ...,
        temperature: float = ...,
    ) -> dict[str, Any]: ...


def _auto_detect_backend() -> str:
    """Prefer local CLIs over direct API usage when available."""

    if shutil.which("codex") is not None:
        return "codex"
    if shutil.which("claude") is not None:
        return "claude_code"
    return "anthropic"


def make_llm_client(cfg: LlmConfig) -> LLMClient:
    """Construct the LLM client matching ``cfg.backend``.

    Lazy imports avoid loading the Anthropic SDK when the user runs through
    Claude Code CLI only (and vice versa).
    """

    backend = cfg.backend
    if backend == "auto":
        backend = _auto_detect_backend()

    if backend == "codex":
        from .codex_cli import CodexCliClient  # noqa: PLC0415

        return CodexCliClient(cfg)

    if backend == "claude_code":
        # Lazy import so users without the Anthropic SDK can still run through
        # the CLI backend. PLC0415 is intentional here.
        from .claude_code_cli import ClaudeCodeCliClient  # noqa: PLC0415

        return ClaudeCodeCliClient(cfg)

    if backend == "anthropic":
        from .anthropic import AnthropicClient  # noqa: PLC0415

        return AnthropicClient(cfg)

    raise ValueError(
        "Unknown LLM_BACKEND="
        f"{backend!r}; expected 'codex' | 'claude_code' | 'anthropic' | 'auto'"
    )
