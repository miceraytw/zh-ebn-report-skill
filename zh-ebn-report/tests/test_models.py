"""Pydantic model validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zh_ebn_report.models import (
    PICO,
    CaspItem,
    Paper,
    QuestionType,
    SixPieceStrategy,
    SourceDB,
    OxfordLevel,
    StudyDesign,
)


class TestPICO:
    def test_comparison_无介入_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PICO(
                population_zh="ICU 成人",
                population_en="ICU adults",
                intervention_zh="音樂療法",
                intervention_en="music therapy",
                comparison_zh="無介入",
                comparison_en="no intervention",
                outcome_zh="焦慮量表",
                outcome_en="anxiety scale",
                question_type=QuestionType.THERAPY,
            )

    def test_comparison_routine_care_accepted(self) -> None:
        pico = PICO(
            population_zh="ICU 成人",
            population_en="ICU adults",
            intervention_zh="音樂療法",
            intervention_en="music therapy",
            comparison_zh="現行標準照護",
            comparison_en="routine care",
            outcome_zh="焦慮量表",
            outcome_en="anxiety scale",
            question_type=QuestionType.THERAPY,
        )
        assert pico.comparison_en == "routine care"


class TestSixPieceStrategy:
    def _base(self) -> dict:
        return dict(
            primary_terms=["a", "b", "c"],
            synonyms=["s1", "s2", "s3", "s4", "s5"],
            mesh_terms=["m1"],
            cinahl_headings=["c1"],
            boolean_query_pubmed="q",
            boolean_query_cochrane="q",
            boolean_query_cinahl="q",
            field_codes_used={"pubmed": "[tiab]"},
        )

    def test_primary_terms_below_3_rejected(self) -> None:
        args = self._base()
        args["primary_terms"] = ["a", "b"]
        with pytest.raises(ValidationError):
            SixPieceStrategy(**args)

    def test_primary_terms_above_5_rejected(self) -> None:
        args = self._base()
        args["primary_terms"] = ["a", "b", "c", "d", "e", "f"]
        with pytest.raises(ValidationError):
            SixPieceStrategy(**args)

    def test_synonyms_below_5_rejected(self) -> None:
        args = self._base()
        args["synonyms"] = ["s1"]
        with pytest.raises(ValidationError):
            SixPieceStrategy(**args)

    def test_empty_mesh_rejected(self) -> None:
        args = self._base()
        args["mesh_terms"] = []
        with pytest.raises(ValidationError):
            SixPieceStrategy(**args)


class TestCaspItem:
    def test_vague_language_rejected(self) -> None:
        with pytest.raises(ValidationError):
            CaspItem(q_no=1, question_zh="效度？", answer="Yes", rationale_zh="效度尚可")

    def test_specific_rationale_accepted(self) -> None:
        item = CaspItem(
            q_no=1,
            question_zh="效度？",
            answer="Yes",
            rationale_zh="作者採 ITT 分析，且 CONSORT flow diagram 完整呈現每組 N 數與退出原因。",
        )
        assert item.answer == "Yes"


class TestPaper:
    def test_citekey_generation(self) -> None:
        # PubMed-style "Surname Initials" must yield the surname (not the initial)
        p = Paper(
            title="Music therapy reduces postoperative anxiety",
            authors=["Smith J", "Doe A"],
            year=2023,
            journal="JAN",
            doi="10.1111/jan.16000",
            study_design=StudyDesign.RCT,
            oxford_level=OxfordLevel.II,
            source_db=SourceDB.PUBMED,
        )
        assert p.citekey().startswith("smith2023")

        # Also accept "Surname, Initials" comma form
        p2 = Paper(
            title="Another study",
            authors=["Smith, J", "Doe, A"],
            year=2024,
            journal="JAN",
            doi="10.1111/jan.16001",
            study_design=StudyDesign.RCT,
            oxford_level=OxfordLevel.II,
            source_db=SourceDB.PUBMED,
        )
        assert p2.citekey().startswith("smith2024")
