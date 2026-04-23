"""Guardrail tests for the deterministic Oxford-level normalizer.

These tests encode the OCEBM 2011 ceiling rules:
- RCT → max Level II
- SR/MA of RCTs → may reach Level I
- SR/MA of cohort/observational → max Level III (SR does not upgrade design)
- Single cohort → max Level III
- Case-control / Qualitative / Other → max Level IV

Matches ``zh_ebn_report/references/appraisal-tools.md``.
"""

from __future__ import annotations

from zh_ebn_report.models import (
    CaspItem,
    CaspResult,
    CaspTool,
    OxfordLevel,
    Paper,
    SourceDB,
    StudyDesign,
)
from zh_ebn_report.pipeline.evidence_guard import enforce_evidence_levels


def _paper(
    *,
    title: str,
    design: StudyDesign,
    level: OxfordLevel,
    doi: str = "10.x/1",
    abstract: str | None = None,
) -> Paper:
    return Paper(
        title=title,
        authors=["Author A"],
        year=2024,
        journal="J",
        doi=doi,
        study_design=design,
        oxford_level=level,
        source_db=SourceDB.PUBMED,
        abstract=abstract,
    )


def _casp(doi: str, level: OxfordLevel, tool: CaspTool = CaspTool.SR) -> CaspResult:
    return CaspResult(
        paper_doi=doi,
        tool_used=tool,
        checklist_items=[
            CaspItem(
                q_no=1,
                question_zh="研究問題是否清楚？",
                answer="Yes",
                rationale_zh="明確界定",
            )
        ],
        validity_zh="合理",
        importance_zh="中等",
        applicability_zh="適用",
        oxford_level_2011=level,
    )


class TestDowngradeMAofCohort:
    def test_ma_of_cohort_labeled_level_i_is_downgraded_to_iii(self) -> None:
        p = _paper(
            title="Meta-analysis of cohort studies on postoperative pain",
            design=StudyDesign.MA,
            level=OxfordLevel.I,
            abstract="We pooled 12 observational cohort studies.",
        )
        c = _casp(p.doi, OxfordLevel.I, tool=CaspTool.SR)

        downgrades = enforce_evidence_levels([p], [c])

        assert len(downgrades) == 1
        assert downgrades[0].original_level == OxfordLevel.I
        assert downgrades[0].corrected_level == OxfordLevel.III
        assert p.oxford_level == OxfordLevel.III
        assert c.oxford_level_2011 == OxfordLevel.III

    def test_sr_of_cohort_labeled_level_ii_is_downgraded_to_iii(self) -> None:
        p = _paper(
            title="Systematic review of cohort studies on fall prevention",
            design=StudyDesign.SR,
            level=OxfordLevel.II,
            abstract="Cohort studies in elderly inpatients.",
        )
        c = _casp(p.doi, OxfordLevel.II, tool=CaspTool.SR)

        downgrades = enforce_evidence_levels([p], [c])

        assert len(downgrades) == 1
        assert p.oxford_level == OxfordLevel.III


class TestKeepSRofRCT:
    def test_sr_of_rct_keeps_level_i(self) -> None:
        p = _paper(
            title="Meta-analysis of randomized controlled trials of EMLA",
            design=StudyDesign.MA,
            level=OxfordLevel.I,
            abstract="We searched Cochrane and included 15 RCTs.",
        )
        c = _casp(p.doi, OxfordLevel.I, tool=CaspTool.SR)

        downgrades = enforce_evidence_levels([p], [c])

        assert downgrades == []
        assert p.oxford_level == OxfordLevel.I
        assert c.oxford_level_2011 == OxfordLevel.I


class TestSingleRCT:
    def test_single_rct_at_level_ii_is_kept(self) -> None:
        p = _paper(
            title="A randomized trial of music therapy",
            design=StudyDesign.RCT,
            level=OxfordLevel.II,
        )
        c = _casp(p.doi, OxfordLevel.II, tool=CaspTool.RCT)

        downgrades = enforce_evidence_levels([p], [c])

        assert downgrades == []
        assert p.oxford_level == OxfordLevel.II

    def test_single_rct_mis_labeled_level_i_is_downgraded_to_ii(self) -> None:
        p = _paper(
            title="A randomized trial of music therapy",
            design=StudyDesign.RCT,
            level=OxfordLevel.I,
        )
        c = _casp(p.doi, OxfordLevel.I, tool=CaspTool.RCT)

        downgrades = enforce_evidence_levels([p], [c])

        assert len(downgrades) == 1
        assert downgrades[0].corrected_level == OxfordLevel.II
        assert p.oxford_level == OxfordLevel.II


class TestSingleCohort:
    def test_cohort_at_level_iii_is_kept(self) -> None:
        p = _paper(
            title="Prospective cohort of elderly patients",
            design=StudyDesign.COHORT,
            level=OxfordLevel.III,
        )
        c = _casp(p.doi, OxfordLevel.III, tool=CaspTool.COHORT)

        downgrades = enforce_evidence_levels([p], [c])

        assert downgrades == []

    def test_cohort_mis_labeled_level_i_is_downgraded(self) -> None:
        p = _paper(
            title="Observational study of pressure ulcers",
            design=StudyDesign.COHORT,
            level=OxfordLevel.I,
        )
        c = _casp(p.doi, OxfordLevel.I, tool=CaspTool.COHORT)

        downgrades = enforce_evidence_levels([p], [c])

        assert len(downgrades) == 1
        assert p.oxford_level == OxfordLevel.III


class TestMixedBatch:
    def test_multiple_papers_only_offenders_downgraded(self) -> None:
        p1 = _paper(
            title="Randomized controlled trial of A",
            design=StudyDesign.RCT,
            level=OxfordLevel.II,
            doi="10.x/rct",
        )
        p2 = _paper(
            title="Meta-analysis of cohort studies",
            design=StudyDesign.MA,
            level=OxfordLevel.I,
            abstract="Pooled 10 cohort studies.",
            doi="10.x/ma-cohort",
        )
        p3 = _paper(
            title="Cochrane review of RCTs",
            design=StudyDesign.SR,
            level=OxfordLevel.I,
            abstract="We included 20 randomized trials.",
            doi="10.x/sr-rct",
        )
        casp_results = [
            _casp("10.x/rct", OxfordLevel.II, tool=CaspTool.RCT),
            _casp("10.x/ma-cohort", OxfordLevel.I, tool=CaspTool.SR),
            _casp("10.x/sr-rct", OxfordLevel.I, tool=CaspTool.SR),
        ]

        downgrades = enforce_evidence_levels([p1, p2, p3], casp_results)

        # Only the MA-of-cohort should be touched
        assert len(downgrades) == 1
        assert downgrades[0].paper_doi == "10.x/ma-cohort"
        assert p1.oxford_level == OxfordLevel.II  # RCT kept
        assert p2.oxford_level == OxfordLevel.III  # MA of cohort downgraded
        assert p3.oxford_level == OxfordLevel.I  # SR of RCTs kept
