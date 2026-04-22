"""Elsevier Embase Search API client.

Docs: https://dev.elsevier.com/documentation/EmbaseAPI.wadl

Requires ``EMBASE_API_KEY`` and typically an ``EMBASE_AUTH_TOKEN`` (session token)
with institutional subscription. Many institutions do not provision Embase access
even when Scopus works — when unauthorized, callers should treat this client as
``manual_import``-only and fall back to RIS upload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_BASE_URL = "https://api.elsevier.com/content/embase/article"


@dataclass(frozen=True)
class EmbaseHit:
    embase_id: str
    title: str
    authors: list[str]
    year: int | None
    journal: str
    doi: str | None


class EmbaseClient:
    def __init__(
        self,
        api_key: str,
        *,
        inst_token: str | None = None,
        auth_token: str | None = None,
        timeout: float = 30.0,
    ):
        if not api_key:
            raise ValueError("Embase API key is required")
        headers = {
            "X-ELS-APIKey": api_key,
            "Accept": "application/json",
        }
        if inst_token:
            headers["X-ELS-Insttoken"] = inst_token
        if auth_token:
            headers["X-ELS-Authtoken"] = auth_token
        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> EmbaseClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def search(
        self, query: str, *, max_results: int = 25
    ) -> tuple[list[EmbaseHit], str | None]:
        """Run a search. Returns (hits, error_reason).

        If the API returns 401/403, ``error_reason`` is non-None and ``hits`` is
        empty — the caller should fall back to manual RIS import.
        """

        params: dict[str, Any] = {
            "query": query,
            "count": min(max_results, 25),
        }
        try:
            r = await self._client.get(_BASE_URL, params=params)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in {401, 403}:
                return (
                    [],
                    f"Embase 未授權（HTTP {e.response.status_code}）；請改用手動 RIS 匯入",
                )
            raise

        data = r.json()
        entries = data.get("embase-article-search-results", {}).get("results", []) or []
        hits: list[EmbaseHit] = []
        for e in entries[:max_results]:
            hits.append(_parse_embase_entry(e))
        return hits, None


def _parse_embase_entry(e: dict[str, Any]) -> EmbaseHit:
    title = (e.get("title") or {}).get("value", "") if isinstance(e.get("title"), dict) else e.get("title", "")
    authors: list[str] = []
    for a in e.get("authors") or []:
        name = a.get("lastName", "")
        if a.get("firstName"):
            name = f"{name} {a['firstName']}"
        if name:
            authors.append(name.strip())
    year = None
    issue = e.get("issue") or {}
    if isinstance(issue, dict):
        y = issue.get("volumeIssueNumber", {}).get("publicationDate", "")
        if isinstance(y, str) and y[:4].isdigit():
            year = int(y[:4])

    return EmbaseHit(
        embase_id=str(e.get("embaseId", "")),
        title=title if isinstance(title, str) else str(title),
        authors=authors,
        year=year,
        journal=(e.get("source") or {}).get("title", "") if isinstance(e.get("source"), dict) else "",
        doi=e.get("doi"),
    )
