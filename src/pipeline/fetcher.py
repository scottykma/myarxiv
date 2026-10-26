import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import arxiv

from src.config import get

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / get("paths.cache_dir", ".cache")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

ARXIV_CATEGORIES = {
    "cs.AI": "Artificial Intelligence",
    "cs.CL": "Computation and Language",
    "cs.CV": "Computer Vision and Pattern Recognition",
    "cs.LG": "Machine Learning",
    "cs.RO": "Robotics",
    "cs.NE": "Neural and Evolutionary Computing",
    "cs.IR": "Information Retrieval",
    "stat.ML": "Machine Learning (Statistics)",
}


def canonical_id(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", str(arxiv_id).strip())


class ArxivPaper:
    def __init__(self, result: arxiv.Result):
        self.arxiv_id: str = canonical_id(result.get_short_id())
        self.title: str = result.title
        self.authors: list[str] = [a.name for a in result.authors]
        self.abstract: str = result.summary.replace("\n", " ")
        self.published: datetime = result.published
        self.url: str = result.entry_id
        self.pdf_url: str = result.pdf_url
        self.categories: list[str] = result.categories
        self.comment: str = result.comment or ""

    def to_dict(self) -> dict:
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "published": self.published.isoformat(),
            "url": self.url,
            "pdf_url": self.pdf_url,
            "categories": self.categories,
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ArxivPaper":
        p = cls.__new__(cls)
        p.arxiv_id = canonical_id(d["arxiv_id"])
        p.title = d["title"]
        p.authors = d["authors"]
        p.abstract = d["abstract"]
        p.published = datetime.fromisoformat(d["published"])
        p.url = d["url"]
        p.pdf_url = d["pdf_url"]
        p.categories = d["categories"]
        p.comment = d.get("comment", "")
        return p

    def __repr__(self) -> str:
        return f"ArxivPaper({self.arxiv_id}: {self.title[:60]}...)"


def _make_client() -> arxiv.Client:
    client = arxiv.Client(
        page_size=get("arxiv.page_size", 100),
        delay_seconds=get("arxiv.delay_seconds", 10.0),
        num_retries=get("arxiv.num_retries", 2),
    )
    client._session.trust_env = get("arxiv.trust_env", False)
    return client


def _date_range_query(categories: list[str], lookback_days: int) -> str:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=lookback_days)
    since_str = since.strftime("%Y%m%d000000")
    until_str = now.strftime("%Y%m%d235959")

    cat_queries = " OR ".join(f"cat:{c}" for c in categories)
    return f"({cat_queries}) AND submittedDate:[{since_str} TO {until_str}]"


def _cache_path(categories: list[str], lookback_days: int) -> Path:
    key = "+".join(sorted(categories)) + f"_d{lookback_days}"
    return _CACHE_DIR / f"arxiv_{key}.json"


def _load_cache(categories: list[str], lookback_days: int) -> list[ArxivPaper] | None:
    path = _cache_path(categories, lookback_days)
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, KeyError):
        return None
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    if data.get("fetch_date") != today:
        return None
    papers = [ArxivPaper.from_dict(d) for d in data["papers"]]
    logger.info("Loaded %d papers from cache (%s)", len(papers), path.name)
    return papers


def _save_cache(papers: list[ArxivPaper], categories: list[str], lookback_days: int) -> None:
    path = _cache_path(categories, lookback_days)
    data = {
        "fetch_date": datetime.now(timezone.utc).strftime("%Y%m%d"),
        "categories": categories,
        "lookback_days": lookback_days,
        "papers": [p.to_dict() for p in papers],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Cached %d papers to %s", len(papers), path.name)

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for f in _CACHE_DIR.glob("arxiv_*.json"):
        try:
            stale = json.loads(f.read_text()).get("fetch_date", "")
            if stale and stale != today:
                f.unlink()
                logger.info("Removed stale cache: %s", f.name)
        except (json.JSONDecodeError, KeyError, OSError):
            pass


def fetch_daily_papers(
    categories: list[str] | None = None,
    lookback_days: int | None = None,
    use_cache: bool = True,
) -> list[ArxivPaper]:
    if categories is None:
        categories = get("interests.categories", ["cs.AI", "cs.CL", "cs.LG"])
    if lookback_days is None:
        lookback_days = get("daily.lookback_days", 1)
    lookback_days = max(1, int(lookback_days))

    if lookback_days == 1 and datetime.now(timezone.utc).weekday() == 0:
        lookback_days = 3

    if use_cache:
        cached = _load_cache(categories, lookback_days)
        if cached is not None:
            return cached

    valid_cats = [c for c in categories if c in ARXIV_CATEGORIES]
    if not valid_cats:
        logger.warning("No valid categories to fetch")
        return []

    query = _date_range_query(valid_cats, lookback_days)
    logger.info("Fetching arXiv papers: %s", query)

    client = _make_client()
    search = arxiv.Search(
        query=query,
        max_results=None,
        sort_by=arxiv.SortCriterion.SubmittedDate,
    )

    all_papers: list[ArxivPaper] = []
    fetch_failed = False
    try:
        for result in client.results(search):
            all_papers.append(ArxivPaper(result))
    except Exception:
        fetch_failed = True
        logger.exception("arXiv fetch error")

    seen_ids = set()
    unique_papers: list[ArxivPaper] = []
    for p in all_papers:
        if p.arxiv_id not in seen_ids:
            seen_ids.add(p.arxiv_id)
            unique_papers.append(p)

    if fetch_failed and not unique_papers:
        raise RuntimeError("arXiv fetch failed before any papers were returned")

    if fetch_failed:
        logger.warning("Not caching partial arXiv results after fetch error")
    elif not unique_papers:
        logger.warning("arXiv returned 0 papers; not caching an empty result")
    else:
        _save_cache(unique_papers, categories, lookback_days)

    logger.info("Fetched %d unique papers", len(unique_papers))
    return unique_papers
