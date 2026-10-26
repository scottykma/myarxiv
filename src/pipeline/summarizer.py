import json
import logging
import time

from src.pipeline.fetcher import ArxivPaper
from src.llm import get_fast

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize this paper (2-3 sentences, plain language).

Title: {title}
Abstract: {abstract}

Return JSON: {{"summary": "...", "keywords": ["kw1", "kw2", "kw3"]}}"""


def summarize_papers(
    papers: list[tuple[ArxivPaper, int, str]],
) -> list[dict]:
    client = get_fast()
    results: list[dict] = []

    for paper, score, reason in papers:
        try:
            prompt = SUMMARY_PROMPT.format(
                title=paper.title,
                abstract=paper.abstract[:2000],
            )
            resp = client.call(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
                thinking=False,
            )
            data = client.parse_json(resp.choices[0].message.content)
            results.append({
                "paper": paper,
                "score": score,
                "reason": reason,
                "summary": data["summary"],
                "keywords": data["keywords"],
            })
        except (json.JSONDecodeError, KeyError, Exception) as e:
            logger.warning("Failed to summarize %s: %s", paper.arxiv_id, e)
            results.append({
                "paper": paper,
                "score": score,
                "reason": reason,
                "summary": paper.abstract[:200] + "...",
                "keywords": [],
            })
        time.sleep(0.2)

    logger.info("Summarized %d papers", len(results))
    return results
