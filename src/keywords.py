import re
from functools import lru_cache

STOPWORDS = frozenset(
    """
    a an the and or of for in on at to with via from by as is are was were be been being
    this that these those we our their its it using based toward towards into over under
    between through without within across per than then also such can may will not no do
    does did has have had but if when where which who how what why
    """.split()
)


def clean_keyword(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def content_tokens(keyword: str) -> list[str]:
    tokens = [token for token in clean_keyword(keyword).lower().split() if token not in STOPWORDS]
    return list(dict.fromkeys(tokens))


def _token_pattern(token: str) -> str:
    base = re.escape(token)
    if token in STOPWORDS or len(token) <= 2 or token.endswith(("s", "x", "z", "ch", "sh")):
        return base
    return rf"{base}(?:s|es)?"


@lru_cache(maxsize=4096)
def _token_regex(token: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){_token_pattern(token)}(?![A-Za-z0-9])")


@lru_cache(maxsize=4096)
def _phrase_regex(tokens: tuple[str, ...]) -> re.Pattern[str]:
    inner = r"\s+".join(_token_pattern(token) for token in tokens)
    return re.compile(rf"(?<![A-Za-z0-9]){inner}(?![A-Za-z0-9])")


def contains_phrase(text: str | None, keyword: str) -> bool:
    if not text:
        return False
    tokens = clean_keyword(keyword).lower().split()
    if not tokens:
        return False
    return bool(_phrase_regex(tuple(tokens)).search(text.lower()))


def contains_all_tokens(text: str | None, keyword: str) -> bool:
    if not text:
        return False
    tokens = content_tokens(keyword)
    if not tokens:
        return False
    lower = text.lower()
    return all(_token_regex(token).search(lower) for token in tokens)


def matched_content_tokens(text: str | None, keyword: str) -> list[str]:
    if not text:
        return []
    lower = text.lower()
    return [token for token in content_tokens(keyword) if _token_regex(token).search(lower)]


def token_coverage(text: str | None, keyword: str) -> float:
    tokens = content_tokens(keyword)
    if not tokens:
        return 0.0
    return len(matched_content_tokens(text, keyword)) / len(tokens)


def covers_keyword(text: str | None, keyword: str, threshold: float = 0.6) -> bool:
    return token_coverage(text, keyword) >= threshold


def keyword_matches_text(text: str | None, keyword: str) -> bool:
    if not content_tokens(keyword):
        return False
    return contains_phrase(text, keyword) or covers_keyword(text, keyword)
