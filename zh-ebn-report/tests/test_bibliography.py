"""BibTeX bibliography rendering tests."""

from __future__ import annotations

from zh_ebn_report.models import OxfordLevel, Paper, SourceDB, StudyDesign
from zh_ebn_report.renderers.bibliography import paper_to_entry, papers_to_bibtex


def _paper() -> Paper:
    return Paper(
        title="Music therapy reduces preoperative anxiety in adults",
        authors=["Smith J", "Doe A"],
        year=2023,
        journal="Journal of Advanced Nursing",
        doi="10.1111/jan.16000",
        study_design=StudyDesign.RCT,
        oxford_level=OxfordLevel.II,
        source_db=SourceDB.PUBMED,
        abstract="This is an abstract.",
    )


def test_paper_to_entry_contains_required_fields() -> None:
    entry = paper_to_entry(_paper())
    assert "@article{" in entry
    assert "title = {Music therapy" in entry
    assert "doi = {10.1111/jan.16000}" in entry
    assert "year = {2023}" in entry


def test_multiple_papers() -> None:
    p1 = _paper()
    p2 = _paper().model_copy(update={"doi": "10.1/xyz", "title": "Another paper"})
    bib = papers_to_bibtex([p1, p2])
    assert bib.count("@article{") == 2
