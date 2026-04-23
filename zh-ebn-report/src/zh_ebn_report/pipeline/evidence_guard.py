"""Deterministic evidence-level guardrail.

Runs after CASP appraisal to catch the common LLM failure of assigning Oxford
Level 1 or 2 to SR/MA of cohort, single cohort, case-control, etc. Not a
stylistic preference — OCEBM 2011 / JBI / GRADE all agree that observational
evidence cannot be upgraded to Level 1 by meta-analysis alone.

The guardrail is pure Python; it does not call the LLM. It mutates the
incoming ``Paper`` and ``CaspResult`` records in place and returns a list of
``EvidenceDowngrade`` records describing what changed and why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models import CaspResult, OxfordLevel, Paper, StudyDesign

_LEVEL_ORDER: tuple[OxfordLevel, ...] = (
    OxfordLevel.I,
    OxfordLevel.II,
    OxfordLevel.III,
    OxfordLevel.IV,
    OxfordLevel.V,
)
_LEVEL_RANK: dict[OxfordLevel, int] = {lvl: idx for idx, lvl in enumerate(_LEVEL_ORDER)}

_RCT_SIGNAL_RE = re.compile(
    r"\b(randomi[sz]ed|randomi[sz]ed\s+controlled|rct)\b",
    re.IGNORECASE,
)
_OBSERVATIONAL_SIGNAL_RE = re.compile(
    r"\b(cohort|observational|case[-\s]?control|retrospective)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EvidenceDowngrade:
    """One deterministic correction to an LLM-assigned Oxford level."""

    paper_doi: str
    paper_title: str
    study_design: StudyDesign
    original_level: OxfordLevel
    corrected_level: OxfordLevel
    reason: str

    def format(self) -> str:
        return (
            f"⚠ [{self.paper_doi}] {self.study_design.value} "
            f"自 Level {self.original_level.value} 降級至 "
            f"Level {self.corrected_level.value}：{self.reason}"
        )


def _cap_at(level: OxfordLevel, ceiling: OxfordLevel) -> OxfordLevel:
    """Return ``level`` if at or below ceiling, else ``ceiling``.

    Ordering is by rank in ``_LEVEL_ORDER`` (Level I strongest → Level V weakest).
    """

    return level if _LEVEL_RANK[level] >= _LEVEL_RANK[ceiling] else ceiling


def _detect_sr_underlying_design(paper: Paper) -> str:
    """Classify the underlying design of a SR/MA by inspecting title + abstract.

    Returns one of ``"rct"``, ``"observational"``, or ``"unknown"``. Only used
    when StudyDesign is SR or MA — for those we must know what's *inside* the
    review to decide whether Level 1 is legitimate.
    """

    haystack = f"{paper.title} {paper.abstract or ''}"
    has_rct = bool(_RCT_SIGNAL_RE.search(haystack))
    has_obs = bool(_OBSERVATIONAL_SIGNAL_RE.search(haystack))
    # Explicit "RCT" signal wins: many SR-of-RCTs also mention cohort in the
    # discussion, and OCEBM Level 1 applies when RCTs are the primary input.
    if has_rct and not has_obs:
        return "rct"
    if has_rct and has_obs:
        # Mixed review: conservative path treats it as observational unless the
        # title unambiguously commits to RCTs.
        title_only = paper.title.lower()
        if "randomi" in title_only or "rct" in title_only:
            return "rct"
        return "observational"
    if has_obs:
        return "observational"
    return "unknown"


def _ceiling_for(paper: Paper) -> tuple[OxfordLevel, str]:  # noqa: PLR0911
    """Return the maximum allowable Oxford Level for a given paper.

    Second tuple element is a human-readable reason used in downgrade records
    and warnings. Follows OCEBM 2011 Treatment Benefits column; see
    ``references/appraisal-tools.md`` for citations.
    """

    design = paper.study_design

    if design == StudyDesign.RCT:
        return OxfordLevel.II, "單一 RCT 最高 Level II（OCEBM 2011）"

    if design in (StudyDesign.SR, StudyDesign.MA):
        underlying = _detect_sr_underlying_design(paper)
        if underlying == "rct":
            return OxfordLevel.I, "SR/MA of RCTs 可達 Level I"
        if underlying == "observational":
            return (
                OxfordLevel.III,
                "SR/MA of cohort/observational 最高 Level III"
                "（OCEBM 2011；SR 不升級 observational 設計）",
            )
        return (
            OxfordLevel.III,
            "SR/MA 未偵測到 RCT 訊號，保守採最高 Level III",
        )

    if design == StudyDesign.COHORT:
        return (
            OxfordLevel.III,
            "Cohort 屬 observational，預設最高 Level III（除非 dramatic effect）",
        )

    if design == StudyDesign.CASE_CONTROL:
        return OxfordLevel.IV, "Case-control 最高 Level IV（OCEBM 2011）"

    if design == StudyDesign.QUALITATIVE:
        return (
            OxfordLevel.IV,
            "質性研究不在 OCEBM treatment hierarchy 內，保守採 Level IV",
        )

    # StudyDesign.OTHER
    return OxfordLevel.IV, "未分類設計，保守採最高 Level IV"


def enforce_evidence_levels(
    papers: list[Paper],
    casp_results: list[CaspResult],
) -> list[EvidenceDowngrade]:
    """Normalize evidence levels across papers + CASP results.

    Mutates ``paper.oxford_level`` and ``casp_result.oxford_level_2011`` in
    place. Returns a list of downgrades actually applied (empty list when
    every assignment was already compatible with the study design).

    The two sources of truth (Paper.oxford_level from search time, and
    CaspResult.oxford_level_2011 from appraisal time) are both capped
    against the same ceiling, so they cannot drift apart.
    """

    downgrades: list[EvidenceDowngrade] = []
    casp_by_doi: dict[str, CaspResult] = {c.paper_doi: c for c in casp_results}

    for paper in papers:
        ceiling, reason = _ceiling_for(paper)
        casp = casp_by_doi.get(paper.doi)

        # Post-CASP level (the one that matters for synthesis) takes precedence
        # if present; otherwise fall back to the search-time level on the paper.
        observed = casp.oxford_level_2011 if casp is not None else paper.oxford_level
        corrected = _cap_at(observed, ceiling)

        if corrected != observed:
            downgrades.append(
                EvidenceDowngrade(
                    paper_doi=paper.doi,
                    paper_title=paper.title,
                    study_design=paper.study_design,
                    original_level=observed,
                    corrected_level=corrected,
                    reason=reason,
                )
            )

        # Always write back the capped value so Paper and CaspResult agree,
        # even when the observed value was already fine (keeps downstream
        # assumptions simple).
        paper.oxford_level = corrected
        if casp is not None:
            casp.oxford_level_2011 = corrected

    return downgrades
