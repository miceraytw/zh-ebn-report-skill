"""End-to-end smoke test for evidence-level guardrail + compliance audit.

Simulates the pipeline path after CASP appraisal:
1. LLM returns mislabeled Oxford levels (MA-of-cohort as Level I).
2. Guardrail runs, corrects them, records downgrades.
3. Compliance audit then runs clean (no evidence_level_vs_design issues).
4. Manual tampering (setting level back to I) is caught by the compliance
   defense-in-depth check.
"""

from __future__ import annotations

from zh_ebn_report.models import (
    AdvancementLevel,
    CaspItem,
    CaspResult,
    CaspTool,
    OxfordLevel,
    Paper,
    PipelinePhase,
    ReportType,
    RunConfig,
    RunState,
    SourceDB,
    StudyDesign,
)
from zh_ebn_report.pipeline.compliance import _check_evidence_level_vs_design
from zh_ebn_report.pipeline.evidence_guard import enforce_evidence_levels


def _paper(
    title: str,
    design: StudyDesign,
    level: OxfordLevel,
    doi: str,
    abstract: str = "",
) -> Paper:
    return Paper(
        title=title,
        authors=["Author X"],
        year=2024,
        journal="Journal",
        doi=doi,
        study_design=design,
        oxford_level=level,
        source_db=SourceDB.PUBMED,
        abstract=abstract,
    )


def _casp(doi: str, level: OxfordLevel, tool: CaspTool) -> CaspResult:
    return CaspResult(
        paper_doi=doi,
        tool_used=tool,
        checklist_items=[
            CaspItem(
                q_no=1, question_zh="研究問題是否清楚？", answer="Yes", rationale_zh="明確"
            )
        ],
        validity_zh="合理",
        importance_zh="中等",
        applicability_zh="適用",
        oxford_level_2011=level,
    )


class TestEndToEndSmoke:
    def test_ma_of_cohort_gets_corrected_and_compliance_is_clean(self) -> None:
        # Simulate what an LLM might return: MA-of-cohort mislabeled Level I
        p_bad = _paper(
            title="Meta-analysis of cohort studies on VAP prevention",
            design=StudyDesign.MA,
            level=OxfordLevel.I,
            doi="10.x/bad",
            abstract="Pooled observational cohort data from 12 ICUs.",
        )
        p_good = _paper(
            title="Systematic review of randomized controlled trials",
            design=StudyDesign.SR,
            level=OxfordLevel.I,
            doi="10.x/good",
            abstract="We included 20 RCTs from Cochrane.",
        )
        casp_results = [
            _casp("10.x/bad", OxfordLevel.I, tool=CaspTool.SR),
            _casp("10.x/good", OxfordLevel.I, tool=CaspTool.SR),
        ]

        # 1. Guardrail normalizes
        downgrades = enforce_evidence_levels([p_bad, p_good], casp_results)
        assert len(downgrades) == 1
        assert downgrades[0].paper_doi == "10.x/bad"
        assert p_bad.oxford_level == OxfordLevel.III
        assert p_good.oxford_level == OxfordLevel.I  # SR-of-RCT untouched

        # 2. Compliance audit runs clean
        issues = _check_evidence_level_vs_design([p_bad, p_good])
        assert issues == [], f"unexpected issues: {[i.detail for i in issues]}"

    def test_compliance_catches_tampering_after_guardrail(self) -> None:
        """If someone edits state.json manually to push a cohort back to Level I,
        the compliance defense-in-depth check must fire."""

        p = _paper(
            title="Prospective cohort study",
            design=StudyDesign.COHORT,
            level=OxfordLevel.III,
            doi="10.x/c",
        )
        # Simulate tampering (or a future code path bypassing the guardrail)
        p.oxford_level = OxfordLevel.I

        issues = _check_evidence_level_vs_design([p])
        assert len(issues) == 1
        assert issues[0].rule == "evidence_level_vs_design"
        assert "Level I" in issues[0].detail
        assert "Level III" in issues[0].detail

    def test_run_state_records_downgrades_for_audit(self) -> None:
        """RunState.evidence_downgrades must be populated so audit tooling can
        see what the guardrail corrected."""

        cfg = RunConfig(
            run_id="smoke-001",
            report_type=ReportType.EBR_READING,
            advancement_level=AdvancementLevel.N3,
            user_topic_raw="smoke",
            ward_or_context="ICU",
            year_range_start=2021,
            year_range_end=2025,
        )
        state = RunState(config=cfg, current_phase=PipelinePhase.APPRAISE)

        p_bad = _paper(
            title="Meta-analysis of cohort studies",
            design=StudyDesign.MA,
            level=OxfordLevel.I,
            doi="10.x/bad",
            abstract="Observational cohort pool",
        )
        # Guardrail operates on papers+casp directly — no need to build a
        # full SearchResult for the smoke test.
        papers = [p_bad]
        state.casp_results = [_casp("10.x/bad", OxfordLevel.I, tool=CaspTool.SR)]

        downgrades = enforce_evidence_levels(papers, state.casp_results)
        state.evidence_downgrades = [
            {
                "paper_doi": d.paper_doi,
                "paper_title": d.paper_title,
                "study_design": d.study_design.value,
                "original_level": d.original_level.value,
                "corrected_level": d.corrected_level.value,
                "reason": d.reason,
            }
            for d in downgrades
        ]

        assert len(state.evidence_downgrades) == 1
        rec = state.evidence_downgrades[0]
        assert rec["paper_doi"] == "10.x/bad"
        assert rec["original_level"] == "I"
        assert rec["corrected_level"] == "III"
        assert "observational" in rec["reason"].lower() or "cohort" in rec["reason"].lower()

        # Round-trip through pydantic model dump works (state.json serialization)
        dumped = state.model_dump_json()
        assert "evidence_downgrades" in dumped
        assert "10.x/bad" in dumped
