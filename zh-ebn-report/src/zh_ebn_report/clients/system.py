"""Backend-agnostic system prompt blocks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CachedSystemBlock:
    """A system prompt block that may be cacheable for some backends."""

    text: str
    cache: bool = True
