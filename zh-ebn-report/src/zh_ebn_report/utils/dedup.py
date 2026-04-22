"""Cross-database deduplication.

Two-stage comparison:
1. DOI primary key: papers with identical normalized DOI are the same.
2. Title prefix + first-author-surname + year: papers without DOI fall back here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models import Paper


def _normalize_doi(doi: str) -> str:
    d = doi.strip().lower()
    d = d.removeprefix("https://doi.org/")
    d = d.removeprefix("http://doi.org/")
    d = d.removeprefix("doi:")
    return d.strip()


def _normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^a-z0-9一-鿿\s]", "", t)
    t = re.sub(r"\s+", " ", t)
    return t[:50]


def _first_author_surname(paper: Paper) -> str:
    if not paper.authors:
        return ""
    name = paper.authors[0]
    # Handle "Surname, Given" vs "Given Surname" vs Chinese names.
    if "," in name:
        return name.split(",", 1)[0].strip().lower()
    parts = name.strip().split()
    if not parts:
        return ""
    if "一" <= parts[0][0] <= "鿿":
        return parts[0]  # Chinese: first char block
    return parts[-1].lower()


@dataclass
class DedupGroup:
    canonical: Paper
    duplicates: list[Paper] = field(default_factory=list)


@dataclass
class DedupResult:
    unique: list[Paper]
    groups: list[DedupGroup]

    @property
    def duplicate_count(self) -> int:
        return sum(len(g.duplicates) for g in self.groups)


def dedup(papers: list[Paper]) -> DedupResult:
    """Deduplicate a list of papers. Preserves order by first occurrence."""

    groups: dict[str, DedupGroup] = {}
    title_year_key: dict[tuple[str, str, int], str] = {}
    unique: list[Paper] = []

    for p in papers:
        doi_norm = _normalize_doi(p.doi) if p.doi else ""
        key: str | None = None

        if doi_norm:
            key = f"doi:{doi_norm}"
        else:
            ta_key = (_normalize_title(p.title), _first_author_surname(p), p.year)
            if ta_key in title_year_key:
                key = title_year_key[ta_key]
            else:
                key = f"ta:{len(title_year_key)}"
                title_year_key[ta_key] = key

        if key in groups:
            groups[key].duplicates.append(p)
        else:
            groups[key] = DedupGroup(canonical=p)
            unique.append(p)

    return DedupResult(unique=unique, groups=list(groups.values()))
