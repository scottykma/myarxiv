from src.config import get
from src.pipeline.fetcher import ArxivPaper, fetch_daily_papers
from src.pipeline.filter import (
    chat_final_score,
    excluded_by_keyword,
    keyword_hit_counts,
    keyword_score,
)


def build_preview(
    papers: list[ArxivPaper],
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    top_n: int | None = None,
) -> dict:
    if include_keywords is None:
        include_keywords = get("interests.keywords_include", [])
    if exclude_keywords is None:
        exclude_keywords = get("interests.keywords_exclude", [])
    if top_n is None:
        top_n = get("daily.keyword_prefilter_top", 60)
    top_n = max(0, int(top_n))
    keyword_weights = dict(get("interests.keyword_weights", {}) or {})

    candidates: list[dict] = []
    excluded: list[dict] = []

    for paper in papers:
        excluded_keyword = excluded_by_keyword(paper, exclude_keywords)
        if excluded_keyword is not None:
            excluded.append({"paper": paper, "keyword": excluded_keyword})
            continue
        score, matched_keywords = keyword_score(
            paper,
            include_keywords,
            keyword_weights=keyword_weights,
        )
        candidates.append({"paper": paper, "score": score, "keywords": matched_keywords})

    candidates.sort(key=lambda row: row["score"], reverse=True)
    return {
        "fetched": len(papers),
        "candidates": candidates[:top_n],
        "excluded": excluded,
        "stats": keyword_hit_counts(papers, include_keywords),
        "include_keywords": include_keywords,
        "exclude_keywords": exclude_keywords,
        "keyword_weights": keyword_weights,
    }


def preview_papers(
    days: int | None = None,
    top_n: int | None = None,
    use_cache: bool = True,
    use_llm: bool = False,
) -> dict:
    papers = fetch_daily_papers(lookback_days=days, use_cache=use_cache)
    result = build_preview(papers, top_n=top_n)
    if use_llm:
        scored = [(row["paper"], row["score"], "") for row in result["candidates"]]
        result["llm_results"] = chat_final_score(scored)
    return result


def format_preview(result: dict, *, show_excluded: bool = False, show_stats: bool = False) -> str:
    lines = [f"Fetched {result['fetched']} papers · candidates {len(result['candidates'])}"]
    if not result["candidates"]:
        lines.append("  (no candidates)")
    for index, row in enumerate(result["candidates"], 1):
        title = row["paper"].title
        if len(title) > 96:
            title = title[:95] + "…"
        weights = result.get("keyword_weights", {})
        matched = ", ".join(
            f"{keyword}×{weights[keyword]}" if weights.get(keyword, 1) != 1 else keyword
            for keyword in row["keywords"]
        ) or "-"
        lines.append(f"{index:>2}. score {row['score']:>2}  {title}")
        lines.append(f"      [{matched}]")

    if show_excluded:
        lines.extend(["", f"Excluded by keyword ({len(result['excluded'])}):"])
        if not result["excluded"]:
            lines.append("  (none)")
        for item in result["excluded"]:
            lines.append(f"  - {item['paper'].title}  ← {item['keyword']}")

    if show_stats:
        lines.extend(["", "Keyword hits:"])
        if not result["stats"]:
            lines.append("  (no keywords configured)")
        weights = result.get("keyword_weights", {})
        for keyword, count in sorted(result["stats"].items(), key=lambda item: (-item[1], item[0])):
            weight = weights.get(keyword, 1)
            suffix = f"  (weight {weight})" if weight != 1 else ""
            lines.append(f"  {count:>3}  {keyword}{suffix}")

    if result.get("llm_results") is not None:
        min_score = get("daily.min_relevance_score", 5)
        lines.extend(["", f"LLM selection (score ≥ {min_score}): {len(result['llm_results'])}"])
        for paper, score, reason in result["llm_results"]:
            lines.append(f"  {score:>2}  {paper.title}")
            if reason:
                lines.append(f"      {reason}")

    return "\n".join(lines)


def preview_to_json(result: dict) -> dict:
    return {
        "fetched": result["fetched"],
        "candidates": [
            {
                "paper": row["paper"].to_dict(),
                "score": row["score"],
                "keywords": row["keywords"],
            }
            for row in result["candidates"]
        ],
        "excluded": [
            {"paper": item["paper"].to_dict(), "keyword": item["keyword"]}
            for item in result["excluded"]
        ],
        "stats": result["stats"],
        "keyword_weights": result.get("keyword_weights", {}),
        "llm_results": [
            {"paper": paper.to_dict(), "score": score, "reason": reason}
            for paper, score, reason in result.get("llm_results", [])
        ],
    }
