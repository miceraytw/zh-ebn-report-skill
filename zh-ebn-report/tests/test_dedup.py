"""Dedup logic tests."""

from __future__ import annotations

from zh_ebn_report.models import OxfordLevel, Paper, SourceDB, StudyDesign
from zh_ebn_report.utils.dedup import dedup


def _paper(title: str, doi: str = "", year: int = 2023, authors: list[str] | None = None, source: SourceDB = SourceDB.PUBMED) -> Paper:
    return Paper(
        title=title,
        authors=authors or ["Smith J"],
        year=year,
        journal="J",
        doi=doi,
        study_design=StudyDesign.RCT,
        oxford_level=OxfordLevel.II,
        source_db=source,
    )


def test_doi_dedup_across_sources() -> None:
    p1 = _paper("Music therapy for anxiety", doi="10.1/abc", source=SourceDB.PUBMED)
    p2 = _paper("Music Therapy for Anxiety", doi="10.1/abc", source=SourceDB.SCOPUS)
    p3 = _paper("Music therapy for pain", doi="10.2/xyz", source=SourceDB.PUBMED)
    result = dedup([p1, p2, p3])
    assert len(result.unique) == 2
    assert result.duplicate_count == 1


def test_doi_normalization() -> None:
    p1 = _paper("A", doi="10.1/abc")
    p2 = _paper("A", doi="HTTPS://DOI.ORG/10.1/ABC")
    result = dedup([p1, p2])
    assert len(result.unique) == 1


def test_no_doi_fallback_by_title() -> None:
    p1 = _paper("Music therapy for anxiety", authors=["Smith J"])
    p2 = _paper("Music therapy for anxiety", authors=["Smith J"])  # same
    p3 = _paper("Totally different paper about beds", authors=["Doe A"])
    result = dedup([p1, p2, p3])
    assert len(result.unique) == 2


def test_preserves_first_occurrence() -> None:
    p1 = _paper("A", doi="10.1/abc", source=SourceDB.PUBMED)
    p2 = _paper("A", doi="10.1/abc", source=SourceDB.COCHRANE)
    result = dedup([p1, p2])
    assert result.unique[0].source_db == SourceDB.PUBMED
