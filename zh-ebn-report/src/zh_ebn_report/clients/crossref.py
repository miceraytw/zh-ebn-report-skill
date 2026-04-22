"""CrossRef client for DOI validation and metadata cross-check.

Endpoint: ``https://api.crossref.org/works/{DOI}``

The polite pool (mailto parameter or User-Agent header) gets better SLA and
higher rate limits. Not strictly required but courteous.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass

import httpx

_BASE_URL = "https://api.crossref.org/works/"


@dataclass(frozen=True)
class CrossrefMetadata:
    doi: str
    title: str
    authors: list[str]  # "Surname, Given"
    year: int | None
    journal: str


@dataclass(frozen=True)
class DoiCheck:
    doi: str
    resolvable: bool
    metadata: CrossrefMetadata | None
    matches_paper: bool | None
    mismatch_details: str | None
    http_status: int | None


class CrossrefClient:
    def __init__(self, mailto: str | None, *, timeout: float = 15.0):
        self._mailto = mailto
        headers = {
            "Accept": "application/json",
            "User-Agent": (
                f"zh-ebn-report (mailto:{mailto})" if mailto else "zh-ebn-report"
            ),
        }
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> CrossrefClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def fetch(self, doi: str) -> CrossrefMetadata | None:
        url = _BASE_URL + httpx.URL(doi).path.lstrip("/") if doi.startswith("http") else _BASE_URL + doi
        r = await self._client.get(url)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        data = r.json().get("message", {})

        title_list = data.get("title") or []
        title = title_list[0] if title_list else ""

        authors: list[str] = []
        for a in data.get("author", []) or []:
            family = a.get("family", "")
            given = a.get("given", "")
            if family or given:
                authors.append(f"{family}, {given}".strip(", "))

        year = None
        issued = data.get("issued", {}).get("date-parts") or []
        if issued and issued[0]:
            year = int(issued[0][0])

        journal_list = data.get("container-title") or []
        journal = journal_list[0] if journal_list else ""

        return CrossrefMetadata(
            doi=doi,
            title=title,
            authors=authors,
            year=year,
            journal=journal,
        )

    async def validate(
        self,
        doi: str,
        *,
        expected_title: str | None = None,
        expected_year: int | None = None,
        expected_first_author_surname: str | None = None,
        title_similarity_threshold: float = 0.75,
    ) -> DoiCheck:
        """Fetch metadata and compare with Paper-level expectations.

        Returns a :class:`DoiCheck` with ``matches_paper`` True iff title similarity
        ≥ threshold, year matches, and first author surname present.
        """

        try:
            md = await self.fetch(doi)
        except httpx.HTTPStatusError as e:
            return DoiCheck(
                doi=doi,
                resolvable=False,
                metadata=None,
                matches_paper=None,
                mismatch_details=f"HTTP {e.response.status_code}",
                http_status=e.response.status_code,
            )
        except httpx.RequestError as e:
            return DoiCheck(
                doi=doi,
                resolvable=False,
                metadata=None,
                matches_paper=None,
                mismatch_details=f"Network error: {e}",
                http_status=None,
            )

        if md is None:
            return DoiCheck(
                doi=doi,
                resolvable=False,
                metadata=None,
                matches_paper=None,
                mismatch_details="CrossRef 404 — DOI does not resolve",
                http_status=404,
            )

        mismatches: list[str] = []
        if expected_title is not None:
            ratio = difflib.SequenceMatcher(
                None, expected_title.lower(), md.title.lower()
            ).ratio()
            if ratio < title_similarity_threshold:
                mismatches.append(
                    f"title similarity {ratio:.2f} < {title_similarity_threshold}"
                )
        if expected_year is not None and md.year is not None and expected_year != md.year:
            mismatches.append(f"year {expected_year} ≠ CrossRef {md.year}")
        if expected_first_author_surname and md.authors:
            first = md.authors[0].split(",")[0].strip().lower()
            if expected_first_author_surname.lower() not in first:
                mismatches.append(
                    f"first author surname '{expected_first_author_surname}' not in '{first}'"
                )

        return DoiCheck(
            doi=doi,
            resolvable=True,
            metadata=md,
            matches_paper=(not mismatches),
            mismatch_details="; ".join(mismatches) if mismatches else None,
            http_status=200,
        )
