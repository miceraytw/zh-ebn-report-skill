"""Prompt assembly utilities.

Every subagent needs a system prompt composed of:
1. A shared base (`_base.md`) — role, language, voice rules
2. One or more knowledge-base references (from ``zh-ebn-report/references/``)
3. A role-specific prompt (from ``src/zh_ebn_report/prompts/*.md``)

Each chunk is wrapped as a :class:`CachedSystemBlock` so Anthropic prompt caching
is used across the pipeline's many calls.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..clients.anthropic import CachedSystemBlock
from ..config import PipelineConfig

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


@lru_cache(maxsize=32)
def _read_cached(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def skill_reference(pipeline_cfg: PipelineConfig, filename: str) -> str:
    """Load a reference file from the skill knowledge base (read-only, cached)."""

    path = pipeline_cfg.skill_root / "references" / filename
    return _read_cached(path)


def role_prompt(filename: str) -> str:
    """Load a role-specific prompt template shipped with the pipeline."""

    path = _PROMPTS_DIR / filename
    return _read_cached(path)


def build_system(
    pipeline_cfg: PipelineConfig,
    *,
    skill_refs: list[str],
    role_prompt_file: str,
) -> list[CachedSystemBlock]:
    """Assemble the full system prompt.

    The returned list is ordered so prompt caching is maximized: stable content
    (base + skill refs) first, role prompt last.
    """

    blocks: list[CachedSystemBlock] = []
    base = _PROMPTS_DIR / "_base.md"
    if base.exists():
        blocks.append(CachedSystemBlock(text=_read_cached(base), cache=True))
    for ref in skill_refs:
        blocks.append(
            CachedSystemBlock(text=skill_reference(pipeline_cfg, ref), cache=True)
        )
    blocks.append(CachedSystemBlock(text=role_prompt(role_prompt_file), cache=True))
    return blocks
