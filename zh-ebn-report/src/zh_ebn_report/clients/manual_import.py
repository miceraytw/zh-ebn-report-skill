"""Manual import for databases without a usable search API.

Cochrane, CINAHL, 華藝 (Airiti), Taiwan Thesis System — all require the user to
search in their browser and export results as RIS or CSV. This module parses
those exports into :class:`Paper` objects so they flow through the same
deduplication / CASP pipeline as auto-fetched results.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bibtexparser
from bibtexparser.bparser import BibTexParser

from ..models import OxfordLevel, Paper, SourceDB, StudyDesign


@dataclass(frozen=True)
class ManualRecord:
    title: str
    authors: list[str]
    year: int
    journal: str
    doi: str | None
    abstract: str | None
    source_db: SourceDB


def _ris_to_records(text: str, default_source: SourceDB) -> list[ManualRecord]:
    """Minimal RIS parser. Accepts the fields we actually need."""

    records: list[ManualRecord] = []
    current: dict[str, Any] = {}
    authors: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if len(line) < 6 or line[2:6] != "  - ":
            # continuation of previous field
            if "_last_tag" in current:
                current[current["_last_tag"]] += " " + line.strip()
            continue
        tag = line[:2]
        value = line[6:].strip()
        if tag == "TY":
            current = {"_type": value}
            authors = []
        elif tag in {"AU", "A1", "A2"}:
            authors.append(value)
            current["_authors"] = authors
        elif tag == "TI" or tag == "T1":
            current["_title"] = value
            current["_last_tag"] = "_title"
        elif tag == "PY" or tag == "Y1":
            if value[:4].isdigit():
                current["_year"] = int(value[:4])
        elif tag == "JO" or tag == "T2" or tag == "JF":
            current["_journal"] = value
        elif tag == "DO":
            current["_doi"] = value
        elif tag == "AB" or tag == "N2":
            current["_abstract"] = value
            current["_last_tag"] = "_abstract"
        elif tag == "ER":
            records.append(
                ManualRecord(
                    title=current.get("_title", ""),
                    authors=current.get("_authors") or [],
                    year=int(current.get("_year", 0) or 0),
                    journal=current.get("_journal", ""),
                    doi=current.get("_doi"),
                    abstract=current.get("_abstract"),
                    source_db=default_source,
                )
            )
            current = {}
            authors = []
    return records


def _bibtex_to_records(text: str, default_source: SourceDB) -> list[ManualRecord]:
    parser = BibTexParser(common_strings=True)
    db = bibtexparser.loads(text, parser=parser)
    records: list[ManualRecord] = []
    for entry in db.entries:
        authors_raw = entry.get("author", "")
        authors = [a.strip() for a in authors_raw.split(" and ") if a.strip()]
        year_raw = entry.get("year", "0")
        try:
            year = int(year_raw[:4])
        except ValueError:
            year = 0
        records.append(
            ManualRecord(
                title=entry.get("title", "").strip("{}"),
                authors=authors,
                year=year,
                journal=entry.get("journal", ""),
                doi=entry.get("doi") or None,
                abstract=entry.get("abstract") or None,
                source_db=default_source,
            )
        )
    return records


def load_manual_import(path: Path, *, source_db: SourceDB) -> list[ManualRecord]:
    """Load an RIS or BibTeX file. Format detected by suffix."""

    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".ris", ".txt"}:
        return _ris_to_records(text, source_db)
    if suffix in {".bib", ".bibtex"}:
        return _bibtex_to_records(text, source_db)
    raise ValueError(f"Unsupported manual import format: {suffix}")


def record_to_paper(
    record: ManualRecord,
    *,
    study_design: StudyDesign = StudyDesign.OTHER,
    oxford_level: OxfordLevel = OxfordLevel.IV,
) -> Paper:
    """Convert a :class:`ManualRecord` into a :class:`Paper`.

    study_design / oxford_level default to conservative values; the CASP
    appraiser will refine these after reading the abstract.
    """

    return Paper(
        title=record.title,
        authors=record.authors,
        year=record.year,
        journal=record.journal,
        doi=record.doi or "",
        doi_validated=False,
        study_design=study_design,
        oxford_level=oxford_level,
        source_db=record.source_db,
        abstract=record.abstract,
    )
