"""Deterministic APA-pass derivation.

``run_apa_formatter`` is an LLM that previously emitted its own ``apa_pass``
bool. CP8 (``pipeline/checkpoints.py:355``) uses that bool to set the default
``default_choice``, so an LLM claiming a false pass effectively auto-approves
a broken bibliography. Since the actual APA output is rendered by Quarto →
pandoc → ``apa-7th-edition.csl`` from ``references.bib``, the only things
that *can* go wrong are:

1. A ``Paper`` with missing APA-required fields (empty journal/title/authors,
   bad year). A1 ``Paper.apa_required_fields`` validator already prevents
   these from entering state at all, but if they did (e.g. via a hand-edited
   ``state.json``), we still want the bool to reflect reality.
2. An unvalidated DOI (``doi_validated=False``) — fabrication risk.
3. A citation key referenced in the draft that does not map to any Paper —
   pandoc would render ``[@key?]`` in the DOCX and reviewers often miss it.
   Compliance's A2 rules already emit errors for this; we just aggregate.
4. LLM-reported APA ``format_issues`` (kept as advisory signal).

This module gives the orchestrator a single call — ``compute_apa_pass`` —
that returns ``(bool, reasons)`` and is used to overwrite
``ApaCheckResult.apa_pass`` at phase_voice_apa time.
"""

from __future__ import annotations

from ..models import ApaCheckResult, Paper
from .compliance import (
    _check_citation_content_matches_placeholders,
    _check_citation_keys_exist,
)


def _doi_problems(papers: list[Paper]) -> list[str]:
    """Collect reason strings for any unvalidated or mismatched DOI."""

    reasons: list[str] = []
    for p in papers:
        if not p.doi_validated:
            reasons.append(
                f"[{p.citekey()}] DOI 未通過 CrossRef 驗證（doi={p.doi!r}）"
            )
            continue
        if p.doi_metadata_matches is False:
            reasons.append(
                f"[{p.citekey()}] CrossRef metadata 與 paper 不符"
            )
    return reasons


def _citation_problems(
    sections_by_name: dict,
    papers: list[Paper],
) -> list[str]:
    """Aggregate compliance A2 rules (orphan key / placeholder mismatch) into
    plain reason strings for the apa_pass verdict."""

    reasons: list[str] = []
    for issue in _check_citation_keys_exist(sections_by_name, papers):
        # Orphan citekey always an APA failure (captures fabricated cites)
        reasons.append(f"{issue.section} · {issue.rule}: {issue.detail}")
    for issue in _check_citation_content_matches_placeholders(sections_by_name):
        # Only hard-error (not warning) placeholder mismatches block the pass
        if issue.severity == "error":
            reasons.append(f"{issue.section} · {issue.rule}: {issue.detail}")
    return reasons


def compute_apa_pass(
    apa: ApaCheckResult,
    papers: list[Paper],
    sections_by_name: dict,
) -> tuple[bool, list[str]]:
    """Derive a Python-truth value for ``apa_pass``.

    Returns ``(apa_pass, reasons)``. ``reasons`` is empty when passing; each
    entry is a short sentence suitable for log output or CP8 body.
    """

    reasons: list[str] = []
    reasons.extend(_doi_problems(papers))
    reasons.extend(_citation_problems(sections_by_name, papers))

    # LLM-reported APA format issues remain advisory: if the LLM flagged
    # real format problems (e.g. missing page range) we treat that as a
    # failure. If the LLM said "fine" but we found real problems above,
    # we already override to False — it is a one-way ratchet.
    if apa.format_issues:
        reasons.append(
            f"LLM 回報 {len(apa.format_issues)} 項格式問題（advisory）"
        )

    return (len(reasons) == 0, reasons)


def normalize_apa_result(
    apa: ApaCheckResult,
    papers: list[Paper],
    sections_by_name: dict,
) -> tuple[ApaCheckResult, list[str]]:
    """Mutate ``apa.apa_pass`` to reflect the Python-derived verdict.

    Returns ``(mutated_apa, reasons)`` so the orchestrator can log why the
    verdict was what it was.
    """

    derived, reasons = compute_apa_pass(apa, papers, sections_by_name)
    apa.apa_pass = derived
    return apa, reasons
