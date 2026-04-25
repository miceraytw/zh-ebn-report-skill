"""Anthropic API wrapper with prompt caching and retries.

All LLM calls go through :func:`complete`. System prompts that include knowledge
base content from ``zh-ebn-report/references/*.md`` are cached on the first call;
subsequent calls within the same 5-minute TTL window pay no re-read cost.

The wrapper supports both direct Anthropic API and an Anthropic-schema-compatible
proxy (configured via ``LLM_API_BASE`` / ``LLM_API_KEY``).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from anthropic import AsyncAnthropic
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import LlmConfig
from .system import CachedSystemBlock

ModelTier = Literal["haiku", "sonnet", "opus"]


class AnthropicClient:
    def __init__(self, cfg: LlmConfig):
        self._cfg = cfg
        kwargs: dict[str, Any] = {"api_key": cfg.api_key}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        self._client = AsyncAnthropic(**kwargs)

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
        max_tokens: int = 4096,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        """Send a completion request and return the text of the first content block."""

        system_payload: list[dict[str, Any]] = []
        for block in system_blocks:
            entry: dict[str, Any] = {"type": "text", "text": block.text}
            if block.cache:
                entry["cache_control"] = {"type": "ephemeral"}
            system_payload.append(entry)

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]
        if json_mode:
            messages[0]["content"] = (
                user_message
                + "\n\n請以合法 JSON 回應，不要加任何說明文字或 markdown code fence。"
            )

        model = self.model_for(tier)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(4),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type((asyncio.TimeoutError, Exception)),
            reraise=True,
        ):
            with attempt:
                response = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system_payload,
                    messages=messages,
                )
                break

        content = response.content[0]
        if hasattr(content, "text"):
            return content.text  # type: ignore[no-any-return]
        raise RuntimeError(f"Unexpected content block: {content!r}")

    async def complete_json(
        self,
        *,
        tier: ModelTier,
        system_blocks: list[CachedSystemBlock],
        user_message: str,
        max_tokens: int = 4096,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        """Like :meth:`complete` but parses the response as JSON."""

        raw = await self.complete(
            tier=tier,
            system_blocks=system_blocks,
            user_message=user_message,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=True,
        )
        raw = raw.strip()
        # Strip markdown fences if model included them despite instructions.
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        return json.loads(raw)
