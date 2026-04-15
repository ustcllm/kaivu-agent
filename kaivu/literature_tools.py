from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from .tools import Tool, ToolContext


def _fetch_text(url: str, *, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    cleaned = doi.strip().lower()
    cleaned = re.sub(r"^https?://(dx\.)?doi\.org/", "", cleaned)
    return cleaned or None


def _strip_jats(text: str | None) -> str | None:
    if not text:
        return None
    without_tags = re.sub(r"<[^>]+>", " ", text)
    return " ".join(without_tags.split()) or None


def _citation_key(item: dict[str, Any]) -> str:
    doi = _normalize_doi(item.get("doi"))
    if doi:
        return f"doi:{doi}"
    url = (item.get("url") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = " ".join((item.get("title") or "").lower().split())
    return f"title:{title}"


def _merge_into_library(context: ToolContext, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    library = context.state.scratchpad.setdefault("citation_library", {})
    for item in items:
        key = _citation_key(item)
        merged = dict(library.get(key, {}))
        for field, value in item.items():
            if value not in (None, "", [], {}):
                merged[field] = value
        library[key] = merged
    return list(library.values())


def _fetch_pubmed_abstracts(pmids: list[str]) -> dict[str, str]:
    if not pmids:
        return {}
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&retmode=xml&id={','.join(pmids)}"
    )
    xml_text = _fetch_text(url)
    root = ET.fromstring(xml_text)
    abstracts: dict[str, str] = {}
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        parts = []
        for abstract_text in article.findall(".//Abstract/AbstractText"):
            label = abstract_text.attrib.get("Label")
            piece = " ".join("".join(abstract_text.itertext()).split())
            if piece:
                parts.append(f"{label}: {piece}" if label else piece)
        if pmid and parts:
            abstracts[pmid] = " ".join(parts)
    return abstracts


def _pubmed_esearch(term: str, max_results: int = 5) -> list[str]:
    query = urllib.parse.quote(term)
    url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&retmode=json&retmax={max_results}&term={query}"
    )
    payload = json.loads(_fetch_text(url))
    return payload.get("esearchresult", {}).get("idlist", [])


def _fetch_pubmed_records(pmids: list[str]) -> list[dict[str, Any]]:
    if not pmids:
        return []
    summary_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=pubmed&retmode=json&id={','.join(pmids)}"
    )
    summary = json.loads(_fetch_text(summary_url))
    abstracts = _fetch_pubmed_abstracts(pmids)
    records: list[dict[str, Any]] = []
    for pmid in pmids:
        item = summary.get("result", {}).get(pmid, {})
        doi = None
        for article_id in item.get("articleids", []):
            if article_id.get("idtype") == "doi":
                doi = article_id.get("value")
                break
        records.append(
            {
                "source_type": "pubmed",
                "pmid": pmid,
                "title": item.get("title"),
                "authors": [a.get("name") for a in item.get("authors", [])],
                "published": item.get("pubdate"),
                "journal": item.get("source"),
                "doi": _normalize_doi(doi),
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "abstract": abstracts.get(pmid),
            }
        )
    return records


def _lookup_pubmed_by_doi(doi: str) -> dict[str, Any] | None:
    normalized = _normalize_doi(doi)
    if not normalized:
        return None
    pmids = _pubmed_esearch(f'"{normalized}"[AID]', max_results=1)
    records = _fetch_pubmed_records(pmids)
    return records[0] if records else None


def _lookup_pubmed_by_pmid(pmid: str) -> dict[str, Any] | None:
    records = _fetch_pubmed_records([pmid])
    return records[0] if records else None


class PubMedSearchTool(Tool):
    name = "pubmed_search"
    description = "Search PubMed literature, fetch abstracts, and return deduplicated papers."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "PubMed search query."},
            "max_results": {"type": "integer", "description": "Maximum number of papers to return."},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "query" not in arguments:
            raise ValueError("pubmed_search requires 'query'")
        arguments.setdefault("max_results", 5)
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        query = urllib.parse.quote(arguments["query"])
        max_results = int(arguments.get("max_results", 5))
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&retmode=json&sort=relevance&retmax={max_results}&term={query}"
        )
        search = json.loads(_fetch_text(search_url))
        ids = search.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return {"query": arguments["query"], "results": [], "citation_library_size": 0}

        results = _fetch_pubmed_records(ids)
        library = _merge_into_library(context, results)
        return {"query": arguments["query"], "results": results, "citation_library_size": len(library)}


class ArxivSearchTool(Tool):
    name = "arxiv_search"
    description = "Search arXiv and return preprints with abstract-style summaries."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "arXiv search query."},
            "max_results": {"type": "integer", "description": "Maximum number of papers to return."},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "query" not in arguments:
            raise ValueError("arxiv_search requires 'query'")
        arguments.setdefault("max_results", 5)
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        query = urllib.parse.quote(arguments["query"])
        max_results = int(arguments.get("max_results", 5))
        url = (
            "http://export.arxiv.org/api/query"
            f"?search_query=all:{query}&start=0&max_results={max_results}"
        )
        xml_text = _fetch_text(url)
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        results = []
        for entry in root.findall("atom:entry", ns):
            arxiv_id = entry.findtext("atom:id", default="", namespaces=ns)
            summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns)).split())
            results.append(
                {
                    "source_type": "arxiv",
                    "id": arxiv_id,
                    "title": " ".join((entry.findtext("atom:title", default="", namespaces=ns)).split()),
                    "abstract": summary,
                    "published": entry.findtext("atom:published", default="", namespaces=ns),
                    "authors": [author.findtext("atom:name", default="", namespaces=ns) for author in entry.findall("atom:author", ns)],
                    "doi": None,
                    "url": arxiv_id,
                }
            )
        library = _merge_into_library(context, results)
        return {"query": arguments["query"], "results": results, "citation_library_size": len(library)}


class CrossrefSearchTool(Tool):
    name = "crossref_search"
    description = "Search Crossref metadata, normalize DOIs, and deduplicate scholarly works."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Crossref search query."},
            "max_results": {"type": "integer", "description": "Maximum number of works to return."},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if "query" not in arguments:
            raise ValueError("crossref_search requires 'query'")
        arguments.setdefault("max_results", 5)
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        query = urllib.parse.quote(arguments["query"])
        rows = int(arguments.get("max_results", 5))
        url = f"https://api.crossref.org/works?query={query}&rows={rows}"
        payload = json.loads(_fetch_text(url, headers={"User-Agent": "kaivu/0.1"}))
        items = payload.get("message", {}).get("items", [])
        results = []
        for item in items:
            doi = _normalize_doi(item.get("DOI"))
            pubmed_match = _lookup_pubmed_by_doi(doi) if doi else None
            results.append(
                {
                    "source_type": "crossref",
                    "title": (item.get("title") or [""])[0],
                    "doi": doi,
                    "type": item.get("type"),
                    "published": item.get("created", {}).get("date-time"),
                    "journal": (item.get("container-title") or [""])[0],
                    "authors": [
                        " ".join(filter(None, [author.get("given"), author.get("family")]))
                        for author in item.get("author", [])
                    ],
                    "url": item.get("URL"),
                    "abstract": _strip_jats(item.get("abstract")) or (pubmed_match or {}).get("abstract"),
                    "pmid": (pubmed_match or {}).get("pmid"),
                }
            )
        library = _merge_into_library(context, results)
        return {"query": arguments["query"], "results": results, "citation_library_size": len(library)}


class ResolveCitationTool(Tool):
    name = "resolve_citation"
    description = "Resolve a DOI or PMID into normalized metadata, identifier mappings, and abstract."
    concurrency_safe = True
    read_only = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI to resolve."},
            "pmid": {"type": "string", "description": "PMID to resolve."},
        },
        "additionalProperties": False,
    }

    def validate(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not arguments.get("doi") and not arguments.get("pmid"):
            raise ValueError("resolve_citation requires 'doi' or 'pmid'")
        return arguments

    async def call(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        record = None
        if arguments.get("pmid"):
            record = _lookup_pubmed_by_pmid(str(arguments["pmid"]))
        elif arguments.get("doi"):
            record = _lookup_pubmed_by_doi(str(arguments["doi"]))

        if record is None and arguments.get("doi"):
            doi = _normalize_doi(arguments["doi"])
            url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
            payload = json.loads(_fetch_text(url, headers={"User-Agent": "kaivu/0.1"}))
            item = payload.get("message", {})
            record = {
                "source_type": "crossref",
                "title": (item.get("title") or [""])[0],
                "doi": doi,
                "type": item.get("type"),
                "published": item.get("created", {}).get("date-time"),
                "journal": (item.get("container-title") or [""])[0],
                "authors": [
                    " ".join(filter(None, [author.get("given"), author.get("family")]))
                    for author in item.get("author", [])
                ],
                "url": item.get("URL"),
                "abstract": _strip_jats(item.get("abstract")),
                "pmid": None,
            }

        if record is None:
            return {"resolved": False}

        library = _merge_into_library(context, [record])
        return {
            "resolved": True,
            "record": record,
            "citation_library_size": len(library),
        }



