"""NCBI E-utilities client for PubMed search and metadata fetching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


@dataclass(frozen=True)
class PubMedHit:
    pmid: str
    title: str
    authors: list[str]
    year: int
    journal: str
    doi: str | None
    abstract: str | None


class PubMedClient:
    def __init__(self, api_key: str | None, *, timeout: float = 30.0):
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> PubMedClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def count(self, query: str) -> int:
        """Run an esearch with retmax=0 to get just the total count."""

        params: dict[str, Any] = {
            "db": "pubmed",
            "retmode": "json",
            "retmax": 0,
            "term": query,
        }
        if self._api_key:
            params["api_key"] = self._api_key
        r = await self._client.get(_ESEARCH, params=params)
        r.raise_for_status()
        data = r.json()
        return int(data["esearchresult"]["count"])

    async def search_pmids(self, query: str, *, retmax: int = 100) -> list[str]:
        params: dict[str, Any] = {
            "db": "pubmed",
            "retmode": "json",
            "retmax": retmax,
            "term": query,
        }
        if self._api_key:
            params["api_key"] = self._api_key
        r = await self._client.get(_ESEARCH, params=params)
        r.raise_for_status()
        data = r.json()
        return list(data["esearchresult"].get("idlist", []))

    async def fetch_metadata(self, pmids: list[str]) -> list[PubMedHit]:
        """Fetch title/authors/year/journal/DOI/abstract for a list of PMIDs."""

        if not pmids:
            return []
        params: dict[str, Any] = {
            "db": "pubmed",
            "rettype": "abstract",
            "retmode": "xml",
            "id": ",".join(pmids),
        }
        if self._api_key:
            params["api_key"] = self._api_key
        r = await self._client.get(_EFETCH, params=params)
        r.raise_for_status()
        return _parse_pubmed_xml(r.text)


def _parse_pubmed_xml(xml: str) -> list[PubMedHit]:
    """Minimal XML parser: pulls PubmedArticle records into :class:`PubMedHit`."""

    from xml.etree import ElementTree as ET

    root = ET.fromstring(xml)
    hits: list[PubMedHit] = []
    for article in root.findall(".//PubmedArticle"):
        pmid_node = article.find(".//PMID")
        pmid = pmid_node.text or "" if pmid_node is not None else ""

        title_node = article.find(".//ArticleTitle")
        title = "".join(title_node.itertext()).strip() if title_node is not None else ""

        authors: list[str] = []
        for a in article.findall(".//Author"):
            last = a.findtext("LastName") or ""
            initials = a.findtext("Initials") or ""
            full = f"{last} {initials}".strip()
            if full:
                authors.append(full)

        year_node = article.find(".//PubDate/Year")
        medline_date = article.find(".//PubDate/MedlineDate")
        year = 0
        if year_node is not None and year_node.text:
            try:
                year = int(year_node.text[:4])
            except ValueError:
                year = 0
        elif medline_date is not None and medline_date.text:
            try:
                year = int(medline_date.text[:4])
            except ValueError:
                year = 0

        journal = article.findtext(".//Journal/Title") or ""

        doi = None
        for id_el in article.findall(".//ArticleId"):
            if id_el.attrib.get("IdType") == "doi" and id_el.text:
                doi = id_el.text.strip()
                break

        abstract_parts: list[str] = []
        for ab in article.findall(".//Abstract/AbstractText"):
            label = ab.attrib.get("Label")
            text = "".join(ab.itertext()).strip()
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = "\n".join(abstract_parts) if abstract_parts else None

        hits.append(
            PubMedHit(
                pmid=pmid,
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                doi=doi,
                abstract=abstract,
            )
        )
    return hits
