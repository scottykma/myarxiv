import logging
import re
from typing import Any

import requests

from src.config import get

logger = logging.getLogger(__name__)

GS_URL_PATTERN = re.compile(
    r"scholar\.google\.com/citations\?.*user=([A-Za-z0-9_-]+)"
)

SS_API = "https://api.semanticscholar.org/graph/v1"


class ScholarProfile:
    def __init__(self):
        self.name: str = ""
        self.affiliation: str = ""
        self.interests: list[str] = []
        self.publications: list[dict[str, str]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "affiliation": self.affiliation,
            "interests": self.interests,
            "publications": self.publications,
            "total_papers": len(self.publications),
        }


def extract_user_id(url: str) -> str | None:
    match = GS_URL_PATTERN.search(url)
    if match:
        return match.group(1)
    return None


def _fetch_from_semantic_scholar(gs_url: str) -> ScholarProfile | None:
    try:
        resp = requests.get(
            f"{SS_API}/author/search",
            params={"query": get("profile.name", "")},
            headers={"User-Agent": get("external.user_agent", "MyArxiv/1.0")},
            timeout=get("external.semantic_scholar_timeout", 15),
        )
        resp.raise_for_status()
        data = resp.json()
        authors = data.get("data", [])
        if not authors:
            return None

        author_id = authors[0].get("authorId")
        if not author_id:
            return None

        resp = requests.get(
            f"{SS_API}/author/{author_id}",
            params={"fields": "name,affiliations,homepage,paperCount,papers.title,papers.year,papers.abstract,papers.citationCount"},
            headers={"User-Agent": get("external.user_agent", "MyArxiv/1.0")},
            timeout=get("external.semantic_scholar_timeout", 15),
        )
        resp.raise_for_status()
        data = resp.json()

        profile = ScholarProfile()
        profile.name = data.get("name", "")
        affils = data.get("affiliations", [])
        profile.affiliation = affils[0] if affils else ""

        papers = data.get("papers", [])
        for paper in papers[:30]:
            profile.publications.append({
                "title": paper.get("title", "") or "",
                "year": str(paper.get("year", "") or ""),
                "abstract": paper.get("abstract", "") or "",
                "citation_count": paper.get("citationCount", 0) or 0,
            })

        logger.info(
            "Semantic Scholar: %s, %d papers",
            profile.name,
            len(profile.publications),
        )
        return profile
    except Exception as e:
        logger.warning("Semantic Scholar fetch failed: %s", e)
        return None


def _fetch_from_google_scholar(gs_url: str) -> ScholarProfile | None:
    try:
        from scholarly import scholarly
    except ImportError:
        logger.warning("scholarly not installed")
        return None

    user_id = extract_user_id(gs_url)
    profile = ScholarProfile()

    logger.info("Fetching Google Scholar profile...")

    try:
        if user_id:
            author = scholarly.search_author_id(user_id)
        else:
            search_query = scholarly.search_author(gs_url)
            author = next(search_query)
    except StopIteration:
        raise ValueError(f"Could not find scholar profile from: {gs_url}")

    profile.name = author.get("name", "")
    profile.affiliation = author.get("affiliation", "")
    profile.interests = author.get("interests", [])

    try:
        author = scholarly.fill(author, sections=["basics"])
    except Exception:
        pass

    publications = author.get("publications", [])
    max_pubs = min(len(publications), 30)
    for i in range(max_pubs):
        pub = publications[i]
        try:
            pub = scholarly.fill(pub)
        except Exception:
            pass
        profile.publications.append({
            "title": pub.get("bib", {}).get("title", ""),
            "year": str(pub.get("bib", {}).get("pub_year", "")),
            "abstract": pub.get("bib", {}).get("abstract", ""),
            "citation_count": pub.get("num_citations", 0),
        })

    logger.info(
        "Google Scholar: %s, %d papers",
        profile.name,
        len(profile.publications),
    )
    return profile


def fetch_profile(gs_url: str) -> ScholarProfile:
    profile = _fetch_from_semantic_scholar(gs_url)
    if profile and profile.publications:
        return profile

    logger.info("Semantic Scholar returned no results, trying Google Scholar...")
    profile = _fetch_from_google_scholar(gs_url)
    if profile:
        return profile

    raise ValueError(
        "Could not fetch profile from any source. "
        "Please enter the TUI and describe your interests directly."
    )
