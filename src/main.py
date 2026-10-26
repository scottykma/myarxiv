import json
import logging
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from src.config import get, reload
from src.pipeline.fetcher import ArxivPaper, canonical_id, fetch_daily_papers
from src.pipeline.filter import chat_final_score, keyword_hit_counts, keyword_prefilter
from src.pipeline.notifier import send_report
from src.report import _score_color, build_plain_text, build_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("main")

ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_SEEN_PATH = ROOT / "seen_papers.json"
SEEN_PATH = _DEFAULT_SEEN_PATH


def _seen_path() -> Path:
    if SEEN_PATH != _DEFAULT_SEEN_PATH:
        return SEEN_PATH
    configured = get("paths.seen_papers")
    if configured:
        return _resolve_path(configured)
    return SEEN_PATH


def load_seen_ids() -> set[str]:
    path = _seen_path()
    if not path.exists():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return set()
    if not isinstance(data, dict):
        return set()
    ids = data.get("ids") or []
    if not isinstance(ids, list):
        return set()
    return {canonical_id(str(arxiv_id)) for arxiv_id in ids}


def save_seen_ids(papers: list[ArxivPaper], seen_ids: set[str]) -> None:
    all_ids = {canonical_id(arxiv_id) for arxiv_id in seen_ids}
    all_ids.update(canonical_id(paper.arxiv_id) for paper in papers)
    path = _seen_path()
    payload = {"ids": sorted(all_ids), "updated": datetime.now().isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
    logger.info("Saved %d seen paper IDs", len(all_ids))


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _write_run_stats(stats: dict) -> None:
    configured = get("paths.last_run")
    if not configured:
        return
    stats["finished_at"] = datetime.now().isoformat()
    target = _resolve_path(configured)
    temp = target.with_name(target.name + ".tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        os.replace(temp, target)
    except OSError:
        logger.exception("Failed to write run stats to %s", target)
    finally:
        if temp.exists():
            temp.unlink()


def _finish(stats: dict) -> dict:
    _write_run_stats(stats)
    return stats


def run(
    *,
    dry_run: bool = False,
    lookback_days: int | None = None,
    categories: list[str] | None = None,
) -> dict:
    reload()
    stats: dict = {
        "started_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "fetched": 0,
        "unseen": 0,
        "prefiltered": 0,
        "selected": 0,
        "email_sent": False,
    }
    logger.info("=== MyArxiv run started%s ===", " (dry run)" if dry_run else "")

    papers = fetch_daily_papers(categories=categories, lookback_days=lookback_days)
    stats["fetched"] = len(papers)
    if not papers:
        logger.info("No new papers found today")
        return _finish(stats)

    seen_ids = load_seen_ids()
    unseen = [paper for paper in papers if canonical_id(paper.arxiv_id) not in seen_ids]
    stats["unseen"] = len(unseen)
    if not unseen:
        logger.info("All papers already seen, nothing new")
        return _finish(stats)
    logger.info("New unseen papers: %d", len(unseen))

    include_keywords = get("interests.keywords_include", [])
    stats["keyword_hits"] = keyword_hit_counts(unseen, include_keywords)

    candidates = keyword_prefilter(unseen)
    stats["prefiltered"] = len(candidates)
    if not candidates:
        logger.info("No papers passed keyword filter")
        return _finish(stats)
    logger.info("After keyword filter: %d papers", len(candidates))

    scored_input = [(paper, 0, "") for paper in candidates]
    filtered = chat_final_score(scored_input)
    stats["selected"] = len(filtered)
    if not filtered:
        logger.info("No papers passed final scoring (all below threshold)")
        return _finish(stats)

    report = build_report(filtered, fetched=len(papers), prefiltered=len(candidates), theme="light")
    plain_text = build_plain_text(filtered, fetched=len(papers), prefiltered=len(candidates))

    if dry_run:
        report_path = get("paths.report")
        if report_path:
            target = _resolve_path(report_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(report)
            text_target = target.with_suffix(".txt")
            with open(text_target, "w", encoding="utf-8") as f:
                f.write(plain_text)
            stats["report_path"] = str(target)
            stats["text_report_path"] = str(text_target)
        logger.info("Dry run: %d papers selected; email not sent, seen cache unchanged", len(filtered))
        return _finish(stats)

    title = f"MyArxiv - {datetime.now().strftime('%Y-%m-%d')} - {len(filtered)} papers"
    results = send_report(title, report, plain_text)
    delivered = bool(results.get("email", False))
    stats["email_sent"] = delivered

    if not delivered:
        logger.error("Email not delivered; papers will be retried on the next run")
        return _finish(stats)

    save_seen_ids([paper for paper, _score, _reason in filtered], seen_ids)
    logger.info("=== MyArxiv run completed ===")
    return _finish(stats)


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the daily arXiv digest")
    parser.add_argument("--dry-run", action="store_true", help="build the report without sending or marking papers seen")
    parser.add_argument("--lookback-days", type=int, default=None, help="override daily.lookback_days")
    args = parser.parse_args()
    stats = run(dry_run=args.dry_run, lookback_days=args.lookback_days)
    if (
        not args.dry_run
        and stats.get("selected", 0) > 0
        and not stats.get("email_sent", False)
        and get("notification.email.enabled", True)
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    _main()
