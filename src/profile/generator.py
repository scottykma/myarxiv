import json
import logging

from src.config import get
from src.llm import get_fast
from src.profile.fetcher import ScholarProfile

logger = logging.getLogger(__name__)

INTEREST_PROMPT = """Analyze this researcher's profile and generate targeted arXiv filtering keywords.

Profile:
Name: {name}
Affiliation: {affiliation}
Stated Interests: {interests}
Recent Publications:
{publications}

Generate a JSON object:
- "keywords_include": 10-15 specific, distinct English keyphrases directly derived from the researcher's publications and stated interests. Each keyword must represent a unique research direction. Avoid near-synonyms (e.g. do not include both "attention mechanism" and "self-attention"; pick the most specific one). Avoid overly broad terms like "machine learning" or "deep learning" unless the researcher specifically works on foundations of that broad area. Prefer specific technical terms used in their paper titles. Format: "large language model", "diffusion transformer".
- "keywords_exclude": 3-5 clearly unrelated topics. Only exclude fields the researcher demonstrably does NOT work on.
- "categories": 2-4 arXiv categories from: cs.AI, cs.CL, cs.CV, cs.LG, cs.RO, cs.NE, cs.IR, stat.ML.

Return ONLY the JSON object."""


def generate_interests(profile: ScholarProfile) -> dict:
    client = get_fast()

    pub_texts = []
    for pub in profile.publications[:25]:
        pub_texts.append(f"- [{pub.get('year', '?')}] {pub.get('title', '')}")
    publications_str = "\n".join(pub_texts) if pub_texts else "No publications found"

    prompt = INTEREST_PROMPT.format(
        name=profile.name,
        affiliation=profile.affiliation,
        interests=", ".join(profile.interests) if profile.interests else "None stated",
        publications=publications_str,
    )

    logger.info("Generating research interests via LLM...")
    resp = client.call(
        [{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1200,
        thinking=False,
    )

    content = resp.choices[0].message.content

    try:
        interests = client.parse_json(content)
    except json.JSONDecodeError:
        logger.error("Failed to parse interests JSON: %s", content[:200])
        raise ValueError("LLM returned invalid JSON for interests")

    logger.info(
        "Generated %d include, %d exclude, %d categories",
        len(interests.get("keywords_include", [])),
        len(interests.get("keywords_exclude", [])),
        len(interests.get("categories", [])),
    )
    return interests
