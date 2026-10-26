import logging
import time

from src.config import get
from src.keywords import (
    contains_all_tokens,
    contains_phrase,
    content_tokens,
    covers_keyword,
    keyword_matches_text,
)
from src.llm import get_fast, get_pro
from src.pipeline.fetcher import ArxivPaper

logger = logging.getLogger(__name__)

BATCH_TITLE_PROMPT = """Rate these papers based on TITLES only. Use the following scale STRICTLY:

Score rubric:
- 0-2: Title shows completely unrelated field (e.g. user does CV, paper is about NLP/question answering)
- 3-4: Same broad discipline (CS/AI) but different sub-area (e.g. user does image generation, paper is about image classification)
- 5-6: Related sub-area, could be tangentially relevant (e.g. user does diffusion models, paper is about general generative models)
- 7-8: Directly matches user's research area (e.g. user does video generation, paper explicitly about video generation)
- 9-10: Perfect match, core interest topic (e.g. user's exact keywords appear prominently in title)

User research keywords: {keywords}
These topics should be EXCLUDED (score ≤3 if title is about these): {exclude_keywords}

Papers:
{papers_text}

Return JSON array: [{{"index": 0, "score": int, "reason": "one English sentence"}}, ...]
Return ONLY the JSON array."""

BATCH_FINAL_PROMPT = """You are a research paper evaluator. Rate each paper's TRUE relevance by carefully reading the FULL abstract. Keep thinking enabled to fully analyze technical content.

User's research keywords: {keywords}
User's EXCLUDED topics (papers primarily about these score ≤3): {exclude_keywords}

---
SCORING CALIBRATION (use as strict anchors)
---
Score 9-10 — CORE MATCH: The paper's primary contribution is directly about the user's keywords. The title AND abstract center on the user's exact research topics. The methods, datasets, and problems are what the user works on daily. Keywords appear in the title itself.

Score 7-8 — STRONG MATCH: The paper addresses a problem or uses methods within the user's research area. The connection is technically clear, but the paper's contribution may extend beyond the user's immediate keywords, or the keywords appear prominently in the abstract but not title.

Score 5-6 — TANGENTIAL: The paper touches on adjacent topics or uses related techniques. There is meaningful methodological overlap, but the paper's core focus is clearly in a neighboring sub-area. Keywords may appear in background/related work sections.

Score 3-4 — WEAK MATCH: The paper is in the same broad discipline (computer vision, AI) but focuses on a different sub-area. Only superficial terminology overlap exists; the actual problem being solved differs substantially from the user's interests.

Score 0-2 — IRRELEVANT: Paper's main topic is clearly outside the user's research. Examples: user does video generation but paper is about NLP text classification, reinforcement learning for games, or robotics manipulation. Dominated by exclude keywords.

---
RULES
---
1. Judge the ACTUAL technical contribution, not surface keywords. A paper mentioning "video" in passing ≠ a video generation paper.
2. For each paper, cite SPECIFIC evidence from the abstract to justify the score.
3. Be consistent: papers with similar technical depth and relevance should get similar scores.
4. Do NOT inflate scores just because a paper is well-written or from a top venue.

Papers:
{papers_text}

Return JSON array: [{{"index": 0, "score": int, "reason": "one brief sentence with specific evidence"}}, ...]
Return ONLY the JSON array."""


def _score_weights() -> tuple[int, int, int]:
    return (
        int(get("keyword_prefilter.title_exact_weight", 3)),
        int(get("keyword_prefilter.title_partial_weight", 2)),
        int(get("keyword_prefilter.abstract_weight", 1)),
    )


def _keyword_weight_map(weights: dict[str, int] | None = None) -> dict[str, int]:
    raw = weights
    if raw is None:
        raw = get("interests.keyword_weights", {}) or {}
    result: dict[str, int] = {}
    for keyword, weight in raw.items():
        try:
            value = int(weight)
        except (TypeError, ValueError):
            continue
        if 1 <= value <= 5:
            result[str(keyword).lower()] = value
    return result


def keyword_score(
    paper: ArxivPaper,
    include_keywords: list[str],
    weights: tuple[int, int, int] | None = None,
    keyword_weights: dict[str, int] | None = None,
) -> tuple[int, list[str]]:
    title_exact_weight, title_partial_weight, abstract_weight = weights or _score_weights()
    keyword_weights = _keyword_weight_map(keyword_weights)
    score = 0
    matched: list[str] = []

    for keyword in include_keywords:
        if not content_tokens(keyword):
            continue
        if contains_phrase(paper.title, keyword):
            title_points = title_exact_weight
        elif covers_keyword(paper.title, keyword):
            title_points = title_partial_weight
        else:
            title_points = 0

        abstract_points = abstract_weight if covers_keyword(paper.abstract, keyword) else 0
        points = title_points + abstract_points
        if points:
            weight = keyword_weights.get(keyword.lower(), 1)
            score += points * weight
            matched.append(keyword)

    return score, matched


def excluded_by_keyword(paper: ArxivPaper, exclude_keywords: list[str]) -> str | None:
    for keyword in exclude_keywords:
        if not content_tokens(keyword):
            continue
        if contains_phrase(paper.title, keyword) or contains_all_tokens(paper.title, keyword):
            return keyword
    return None


def keyword_hit_counts(papers: list[ArxivPaper], keywords: list[str]) -> dict[str, int]:
    counts = {keyword: 0 for keyword in keywords}
    searchable = [keyword for keyword in keywords if content_tokens(keyword)]
    for paper in papers:
        for keyword in searchable:
            if keyword_matches_text(paper.title, keyword) or keyword_matches_text(paper.abstract, keyword):
                counts[keyword] += 1
    return counts


def keyword_prefilter(
    papers: list[ArxivPaper],
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    top_n: int | None = None,
) -> list[ArxivPaper]:
    if include_keywords is None:
        include_keywords = get("interests.keywords_include", [])
    if exclude_keywords is None:
        exclude_keywords = get("interests.keywords_exclude", [])
    if top_n is None:
        top_n = get("daily.keyword_prefilter_top", 60)
    top_n = max(0, int(top_n))

    weights = _score_weights()
    keyword_weights = _keyword_weight_map()
    scored: list[tuple[ArxivPaper, int]] = []
    discarded = 0
    zero_score = 0

    for paper in papers:
        if excluded_by_keyword(paper, exclude_keywords):
            discarded += 1
            continue
        score, _ = keyword_score(paper, include_keywords, weights, keyword_weights)
        if score == 0:
            zero_score += 1
        scored.append((paper, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    result = [paper for paper, _ in scored[:top_n]]

    logger.info(
        "Keyword prefilter: %d→%d (discarded=%d zero_score=%d)",
        len(papers),
        len(result),
        discarded,
        zero_score,
    )
    return result


def flash_title_score(
    papers: list[ArxivPaper],
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    top_n: int | None = None,
    batch_size: int | None = None,
) -> list[tuple[ArxivPaper, int, str]]:
    if include_keywords is None:
        include_keywords = get("interests.keywords_include", [])
    if exclude_keywords is None:
        exclude_keywords = get("interests.keywords_exclude", [])
    if top_n is None:
        top_n = get("daily.title_score_top", 25)
    if batch_size is None:
        batch_size = get("llm.flash_batch_size", 20)

    if not papers:
        return []

    client = get_fast()
    scored: list[tuple[ArxivPaper, int, str]] = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        papers_text = "\n".join(
            f"[{j}] {p.title} | cats: {', '.join(p.categories)}"
            for j, p in enumerate(batch)
        )
        prompt = BATCH_TITLE_PROMPT.format(
            keywords=", ".join(include_keywords),
            exclude_keywords=", ".join(exclude_keywords),
            papers_text=papers_text,
        )
        _call_flash_batch(client, prompt, batch, scored)
        time.sleep(get("llm.flash_batch_delay", 0.3))

    scored.sort(key=lambda x: x[1], reverse=True)
    result = scored[:top_n]
    logger.info("Title scoring: %d→%d papers", len(papers), len(result))
    return result


def chat_final_score(
    papers: list[tuple[ArxivPaper, int, str]],
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    min_score: int | None = None,
    max_papers: int | None = None,
    batch_size: int | None = None,
) -> list[tuple[ArxivPaper, int, str]]:
    if include_keywords is None:
        include_keywords = get("interests.keywords_include", [])
    if exclude_keywords is None:
        exclude_keywords = get("interests.keywords_exclude", [])
    if min_score is None:
        min_score = get("daily.min_relevance_score", 7)
    if max_papers is None:
        max_papers = get("daily.max_papers", 20)
    if batch_size is None:
        batch_size = get("llm.pro_batch_size", 8)

    if not papers:
        return []

    client = get_pro()
    scored: list[tuple[ArxivPaper, int, str]] = []

    for i in range(0, len(papers), batch_size):
        batch = papers[i : i + batch_size]
        papers_text = "\n\n".join(
            f"[{j}] Title: {p.title}\n    Abstract: {p.abstract}\n    Categories: {', '.join(p.categories)}"
            for j, (p, _, _) in enumerate(batch)
        )
        prompt = BATCH_FINAL_PROMPT.format(
            keywords=", ".join(include_keywords),
            exclude_keywords=", ".join(exclude_keywords),
            papers_text=papers_text,
        )
        _call_pro_batch(client, prompt, [p for p, _, _ in batch], scored)
        time.sleep(get("llm.pro_batch_delay", 0.5))

    scored.sort(key=lambda x: x[1], reverse=True)
    filtered = [(p, s, r) for p, s, r in scored if s >= min_score]
    if len(filtered) > max_papers:
        filtered = filtered[:max_papers]

    logger.info("Final scoring: %d→%d papers (score≥%d, top %d)", len(papers), len(filtered), min_score, max_papers)
    return filtered


def _call_flash_batch(client, prompt, batch, existing):
    try:
        resp = client.call(
            [{"role": "user", "content": prompt}],
            temperature=get("llm.flash_temperature", 0.1),
            max_tokens=len(batch) * 50 + 50,
            thinking=False,
        )
        parsed = _parse_batch_response(resp.choices[0].message.content, batch, existing)
    except Exception as e:
        logger.warning("Flash batch failed: %s", e)
        return _fallback_single(client, batch, existing)

    missing = [paper for index, paper in enumerate(batch) if index not in parsed]
    if missing:
        logger.warning("Flash batch missed %d papers, scoring individually", len(missing))
        _fallback_single(client, missing, existing)
    return existing


def _call_pro_batch(client, prompt, batch, existing):
    try:
        resp = client.call(
            [{"role": "user", "content": prompt}],
            temperature=get("llm.pro_temperature", 0.0),
            max_tokens=max(4096, len(batch) * 80),
            thinking=True,
        )
        parsed = _parse_batch_response(resp.choices[0].message.content, batch, existing)
    except Exception as e:
        logger.warning("Pro batch failed: %s, retrying with flash", e)
        return _call_flash_batch(get_fast(), prompt, batch, existing)

    missing = [paper for index, paper in enumerate(batch) if index not in parsed]
    if missing:
        logger.warning("Pro batch missed %d papers, scoring individually", len(missing))
        _fallback_single(client, missing, existing)
    return existing


def _parse_batch_response(content, batch, existing) -> set[int]:
    results = get_fast().parse_json(content)
    if isinstance(results, dict):
        results = [results]
    if not isinstance(results, list):
        raise ValueError("LLM response is not a JSON array")

    parsed: list[tuple[ArxivPaper, int, str]] = []
    indices: set[int] = set()

    for item in results:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        if isinstance(index, bool) or not isinstance(index, int):
            continue
        if not 0 <= index < len(batch) or index in indices:
            continue
        score_value = item.get("score")
        if isinstance(score_value, bool):
            continue
        try:
            score = int(score_value)
        except (TypeError, ValueError):
            continue
        if not 0 <= score <= 10:
            continue
        reason = str(item.get("reason") or "")
        parsed.append((batch[index], score, reason))
        indices.add(index)

    if not parsed:
        raise ValueError("No valid scored papers in LLM response")

    existing.extend(parsed)
    return indices


def _fallback_single(client, batch, existing):
    for paper in batch:
        try:
            resp = client.call(
                [{"role": "user", "content": f"Rate 0-10.\nTitle: {paper.title}\nAbstract: {paper.abstract}\nReturn JSON: {{\"score\": int, \"reason\": \"...\"}}"}],
                temperature=get("llm.flash_temperature", 0.1),
                max_tokens=100,
                thinking=False,
            )
            result = client.parse_json(resp.choices[0].message.content)
            score = int(result["score"])
            if not 0 <= score <= 10:
                raise ValueError(f"score out of range: {score}")
            existing.append((paper, score, str(result.get("reason") or "")))
        except Exception as e:
            logger.warning("Single-paper scoring failed for %s: %s", paper.arxiv_id, e)
            continue
        time.sleep(get("llm.fallback_single_delay", 0.2))
    return existing
