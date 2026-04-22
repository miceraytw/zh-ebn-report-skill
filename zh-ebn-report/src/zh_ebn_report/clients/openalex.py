"""OpenAlex client for forward citation chasing.

Endpoint: ``https://api.openalex.org/works/doi:{DOI}``

Free, no auth required. The returned work includes ``cited_by_count`` and a
``cited_by_api_url`` that lists papers citing this one — used for forward
citation chasing (snowballing).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://api.openalex.org"


@dataclass(frozen=True)
class OpenAlexWork:
    openalex_id: str
    doi: str | None
    title: str
    year: int | None
    cited_by_count: int
    cited_by_api_url: str | None


@dataclass(frozen=True)
class CitingPaper:
    openalex_id: str
    doi: str | None
    title: str
    year: int | None
    authors: list[str]


class OpenAlexClient:
    def __init__(self, mailto: str | None = None, *, timeout: float = 15.0):
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

    async def __aenter__(self) -> OpenAlexClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def work_by_doi(self, doi: str) -> OpenAlexWork | None:
        url = f"{_BASE_URL}/works/doi:{doi}"
        params: dict[str, Any] = {}
        if self._mailto:
            params["mailto"] = self._mailto
        r = await self._client.get(url, params=params)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        d = r.json()
        title = d.get("title") or d.get("display_name") or ""
        return OpenAlexWork(
            openalex_id=d.get("id", ""),
            doi=(d.get("doi") or "").removeprefix("https://doi.org/") or None,
            title=title,
            year=d.get("publication_year"),
            cited_by_count=int(d.get("cited_by_count") or 0),
            cited_by_api_url=d.get("cited_by_api_url"),
        )

    async def forward_citations(
        self,
        doi: str,
        *,
        min_year: int | None = None,
        max_results: int = 25,
    ) -> list[CitingPaper]:
        """Return papers citing the given DOI (forward citation chase).

        Filters by year when ``min_year`` is given.
        """

        work = await self.work_by_doi(doi)
        if work is None or not work.cited_by_api_url:
            return []

        params: dict[str, Any] = {"per-page": min(max_results, 200)}
        if min_year is not None:
            params["filter"] = f"from_publication_date:{min_year}-01-01"
        if self._mailto:
            params["mailto"] = self._mailto

        r = await self._client.get(work.cited_by_api_url, params=params)
        r.raise_for_status()
        results = r.json().get("results") or []

        citing: list[CitingPaper] = []
        for w in results[:max_results]:
            authors = []
            for ag in (w.get("authorships") or [])[:5]:
                a = ag.get("author", {})
                name = a.get("display_name", "")
                if name:
                    authors.append(name)
            title = w.get("title") or w.get("display_name") or ""
            citing.append(
                CitingPaper(
                    openalex_id=w.get("id", ""),
                    doi=(w.get("doi") or "").removeprefix("https://doi.org/") or None,
                    title=title,
                    year=w.get("publication_year"),
                    authors=authors,
                )
            )
        return citing
