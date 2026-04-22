"""Elsevier Scopus Search API client.

Docs: https://dev.elsevier.com/documentation/ScopusSearchAPI.wadl

Requires ``SCOPUS_API_KEY``; institutional token optional.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://api.elsevier.com/content/search/scopus"


@dataclass(frozen=True)
class ScopusHit:
    scopus_id: str
    title: str
    authors: list[str]
    year: int | None
    journal: str
    doi: str | None
    abstract: str | None


class ScopusClient:
    def __init__(
        self,
        api_key: str,
        *,
        inst_token: str | None = None,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("Scopus API key is required")
        headers = {
            "X-ELS-APIKey": api_key,
            "Accept": "application/json",
        }
        if inst_token:
            headers["X-ELS-Insttoken"] = inst_token
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ScopusClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def count(self, query: str) -> int:
        params: dict[str, Any] = {"query": query, "count": 0}
        r = await self._client.get(_BASE_URL, params=params)
        r.raise_for_status()
        return int(r.json().get("search-results", {}).get("opensearch:totalResults", 0))

    async def search(self, query: str, *, max_results: int = 50) -> list[ScopusHit]:
        hits: list[ScopusHit] = []
        start = 0
        page_size = min(25, max_results)
        while len(hits) < max_results:
            params: dict[str, Any] = {
                "query": query,
                "count": page_size,
                "start": start,
                "view": "STANDARD",
            }
            r = await self._client.get(_BASE_URL, params=params)
            r.raise_for_status()
            entries = r.json().get("search-results", {}).get("entry", []) or []
            if not entries:
                break
            for e in entries:
                hits.append(_parse_scopus_entry(e))
                if len(hits) >= max_results:
                    break
            start += page_size
        return hits


def _parse_scopus_entry(e: dict[str, Any]) -> ScopusHit:
    authors: list[str] = []
    for a in e.get("author", []) or []:
        name = a.get("authname") or ""
        if name:
            authors.append(name)
    year = None
    cover_date = e.get("prism:coverDate") or ""
    if cover_date[:4].isdigit():
        year = int(cover_date[:4])
    return ScopusHit(
        scopus_id=e.get("dc:identifier", "").removeprefix("SCOPUS_ID:"),
        title=e.get("dc:title", ""),
        authors=authors,
        year=year,
        journal=e.get("prism:publicationName", ""),
        doi=e.get("prism:doi"),
        abstract=e.get("dc:description"),
    )
