"""Tests for A1/A2/A3: APA safety guardrails.

A1 — Paper model_validator requires authors/title/journal/year.
A2a — compliance flags citation_placeholders field vs content_zh drift.
A2b — compliance flags citation keys that have no matching Paper.
A3 — apa_guard.compute_apa_pass overrides the LLM's self-reported apa_pass.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from zh_ebn_report.models import (
    ApaCheckResult,
    ApaIssue,
    OxfordLevel,
    Paper,
    Section,
    SectionSelfCheck,
    SourceDB,
    StudyDesign,
)
from zh_ebn_report.pipeline.apa_guard import compute_apa_pass, normalize_apa_result
from zh_ebn_report.pipeline.compliance import (
    _check_citation_content_matches_placeholders,
    _check_citation_keys_exist,
)


def _section(name: str, content: str, placeholders: list[str]) -> Section:
    return Section(
        section_name=name,  # type: ignore[arg-type]
        content_zh=content,
        word_count_estimate=len(content),
        citation_placeholders=placeholders,
        self_check=SectionSelfCheck(
            uses_bi_jia_not_wo=True,
            uses_ge_an_not_bing_ren=True,
            formal_register_only=True,
            cites_phrasing_bank=False,
        ),
    )


def _paper(**overrides) -> Paper:
    base = dict(
        title="A sample study of intervention",
        authors=["Smith J", "Doe A"],
        year=2024,
        journal="Journal of Nursing",
        doi="10.1111/jan.9999",
        doi_validated=True,
        doi_metadata_matches=True,
        study_design=StudyDesign.RCT,
        oxford_level=OxfordLevel.II,
        source_db=SourceDB.PUBMED,
    )
    base.update(overrides)
    return Paper(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# A1: Paper field completeness
# ---------------------------------------------------------------------------
class TestPaperApaFields:
    def test_normal_paper_accepted(self) -> None:
        _paper()  # no raise

    def test_empty_title_rejected(self) -> None:
        with pytest.raises(ValidationError, match="title"):
            _paper(title="   ")

    def test_empty_journal_rejected(self) -> None:
        with pytest.raises(ValidationError, match="journal"):
            _paper(journal="")

    def test_empty_authors_rejected(self) -> None:
        with pytest.raises(ValidationError, match="authors"):
            _paper(authors=[])

    def test_blank_author_string_rejected(self) -> None:
        with pytest.raises(ValidationError, match="authors"):
            _paper(authors=["   ", ""])

    def test_year_too_old_rejected(self) -> None:
        with pytest.raises(ValidationError, match="1900"):
            _paper(year=1800)

    def test_year_too_far_future_rejected(self) -> None:
        # Testing against current year; year = 3000 is always invalid
        with pytest.raises(ValidationError, match="1900"):
            _paper(year=3000)


# ---------------------------------------------------------------------------
# A2a: citation_placeholders field must match content_zh
# ---------------------------------------------------------------------------
class TestCitationPlaceholderMatch:
    def test_matched_passes(self) -> None:
        sections = {
            "前言": _section(
                "前言",
                "如文獻 [@smith2024sample] 所示……",
                ["@smith2024sample"],
            )
        }
        assert _check_citation_content_matches_placeholders(sections) == []

    def test_field_missing_keys_from_content_flagged(self) -> None:
        # content has smith + doe; placeholders only lists smith
        sections = {
            "前言": _section(
                "前言",
                "[@smith2024sample] 與 [@doe2023other] 均顯示……",
                ["@smith2024sample"],
            )
        }
        issues = _check_citation_content_matches_placeholders(sections)
        assert any(
            i.rule == "citation_placeholder_missing_from_field" for i in issues
        )

    def test_field_phantom_keys_flagged_as_warning(self) -> None:
        sections = {
            "前言": _section(
                "前言",
                "[@smith2024sample] 顯示……",
                ["@smith2024sample", "@ghost2020"],
            )
        }
        issues = _check_citation_content_matches_placeholders(sections)
        phantoms = [
            i for i in issues if i.rule == "citation_placeholder_field_phantom"
        ]
        assert len(phantoms) == 1
        assert phantoms[0].severity == "warning"

    def test_no_at_prefix_normalization(self) -> None:
        """placeholders may be 'key' or '@key' — both should normalize."""
        sections = {
            "前言": _section(
                "前言", "[@smith2024sample] 顯示……", ["smith2024sample"]
            )
        }
        assert _check_citation_content_matches_placeholders(sections) == []


# ---------------------------------------------------------------------------
# A2b: citation keys must map to real Papers
# ---------------------------------------------------------------------------
class TestCitationKeyExists:
    def test_all_valid_keys_pass(self) -> None:
        p = _paper(doi="10.x/1")
        valid_key = p.citekey()
        sections = {"前言": _section("前言", f"[@{valid_key}] 顯示……", [f"@{valid_key}"])}
        assert _check_citation_keys_exist(sections, [p]) == []

    def test_orphan_key_flagged(self) -> None:
        p = _paper()
        sections = {
            "前言": _section(
                "前言", "[@ghost2099madeup] 顯示……", ["@ghost2099madeup"]
            )
        }
        issues = _check_citation_keys_exist(sections, [p])
        assert any(i.rule == "citation_key_orphan" for i in issues)
        assert "ghost2099madeup" in issues[0].detail


# ---------------------------------------------------------------------------
# A3: compute_apa_pass and normalize_apa_result
# ---------------------------------------------------------------------------
class TestComputeApaPass:
    def _apa(
        self, apa_pass: bool = True, format_issues: list | None = None
    ) -> ApaCheckResult:
        return ApaCheckResult(
            format_issues=format_issues or [],
            doi_validation_results=[],
            apa_pass=apa_pass,
        )

    def test_all_clean_passes(self) -> None:
        p = _paper(doi="10.x/1")
        key = p.citekey()
        sections = {"前言": _section("前言", f"[@{key}] ref", [f"@{key}"])}
        derived, reasons = compute_apa_pass(self._apa(True), [p], sections)
        assert derived is True
        assert reasons == []

    def test_orphan_citation_fails(self) -> None:
        p = _paper()
        sections = {
            "前言": _section("前言", "[@ghost] 說", ["@ghost"])
        }
        derived, reasons = compute_apa_pass(self._apa(True), [p], sections)
        assert derived is False
        assert any("orphan" in r.lower() or "ghost" in r for r in reasons)

    def test_unvalidated_doi_fails(self) -> None:
        p = _paper(doi_validated=False)
        key = p.citekey()
        sections = {"前言": _section("前言", f"[@{key}]", [f"@{key}"])}
        derived, reasons = compute_apa_pass(self._apa(True), [p], sections)
        assert derived is False
        assert any("doi" in r.lower() or "crossref" in r.lower() for r in reasons)

    def test_metadata_mismatch_fails(self) -> None:
        p = _paper(doi_metadata_matches=False)
        key = p.citekey()
        sections = {"前言": _section("前言", f"[@{key}]", [f"@{key}"])}
        derived, reasons = compute_apa_pass(self._apa(True), [p], sections)
        assert derived is False

    def test_llm_format_issues_fail(self) -> None:
        p = _paper()
        key = p.citekey()
        sections = {"前言": _section("前言", f"[@{key}]", [f"@{key}"])}
        apa = self._apa(
            apa_pass=True,
            format_issues=[
                ApaIssue(citekey=key, issue="缺少 pages", suggested_fix="補入 1-10")
            ],
        )
        derived, reasons = compute_apa_pass(apa, [p], sections)
        assert derived is False
        assert any("advisory" in r.lower() or "格式" in r for r in reasons)

    def test_llm_lied_pass_true_overwritten_to_false(self) -> None:
        """The headline scenario: LLM says apa_pass=True but reality has an
        orphan cite. normalize_apa_result must flip the bool."""
        p = _paper()
        sections = {
            "前言": _section("前言", "[@fabricated] ref", ["@fabricated"])
        }
        apa = self._apa(apa_pass=True)  # LLM's lie
        mutated, reasons = normalize_apa_result(apa, [p], sections)
        assert mutated.apa_pass is False
        assert reasons  # non-empty
