from src.keywords import clean_keyword
from src.pipeline.fetcher import ARXIV_CATEGORIES

VALID_CATEGORIES = tuple(ARXIV_CATEGORIES)
_CATEGORY_LOOKUP = {category.lower(): category for category in VALID_CATEGORIES}


def unique_keywords(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        keyword = clean_keyword(value)
        if not keyword:
            continue
        key = keyword.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(keyword)
    return result


def add_keywords(current: list[str], new: list[str]) -> tuple[list[str], list[str], list[str]]:
    updated = unique_keywords(current)
    existing = {keyword.lower(): keyword for keyword in updated}
    added: list[str] = []
    duplicates: list[str] = []

    for value in new:
        keyword = clean_keyword(value)
        if not keyword:
            continue
        key = keyword.lower()
        if key in existing:
            duplicates.append(existing[key])
            continue
        updated.append(keyword)
        added.append(keyword)
        existing[key] = keyword

    return updated, added, duplicates


def remove_keywords(
    current: list[str],
    remove: list[str],
) -> tuple[list[str], list[str], list[str]]:
    current_keywords = unique_keywords(current)
    targets = {clean_keyword(value).lower() for value in remove if clean_keyword(value)}
    updated: list[str] = []
    removed: list[str] = []

    for keyword in current_keywords:
        if keyword.lower() in targets:
            removed.append(keyword)
        else:
            updated.append(keyword)

    missing: list[str] = []
    current_keys = {keyword.lower() for keyword in current_keywords}
    for value in remove:
        keyword = clean_keyword(value)
        if keyword and keyword.lower() not in current_keys and keyword not in missing:
            missing.append(keyword)

    return updated, removed, missing


def parse_categories(values: list[str]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for value in values:
        for raw in str(value).split(","):
            category = raw.strip()
            if not category:
                continue
            canonical = _CATEGORY_LOOKUP.get(category.lower())
            if canonical is None:
                if category not in invalid:
                    invalid.append(category)
            elif canonical not in valid:
                valid.append(canonical)
    return valid, invalid


def validate_score(value: object) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid score: {value!r}. Must be an integer 1-10") from exc
    if not 1 <= score <= 10:
        raise ValueError(f"Invalid score: {score}. Must be an integer 1-10")
    return score


def validate_max_papers(value: object) -> int:
    try:
        max_papers = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid max papers: {value!r}. Must be an integer 1-50") from exc
    if not 1 <= max_papers <= 50:
        raise ValueError(f"Invalid max papers: {max_papers}. Must be an integer 1-50")
    return max_papers


def validate_weight(value: object) -> int:
    try:
        weight = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid weight: {value!r}. Must be an integer 1-5") from exc
    if not 1 <= weight <= 5:
        raise ValueError(f"Invalid weight: {weight}. Must be an integer 1-5")
    return weight


def canonical_keyword(keywords: list[str], term: str) -> str | None:
    key = clean_keyword(term).lower()
    if not key:
        return None
    for keyword in keywords:
        if clean_keyword(keyword).lower() == key:
            return clean_keyword(keyword)
    return None


def drop_weights(weights: dict[str, int], removed: list[str]) -> dict[str, int]:
    keys = {clean_keyword(keyword).lower() for keyword in removed if clean_keyword(keyword)}
    return {
        keyword: weight
        for keyword, weight in weights.items()
        if str(keyword).lower() not in keys
    }


def category_help() -> str:
    return ", ".join(VALID_CATEGORIES)
