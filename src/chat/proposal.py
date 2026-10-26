import copy

from src.config import get, load_config, replace
from src.chat.engine import execute_action
from src.interests import (
    add_keywords,
    canonical_keyword,
    drop_weights,
    parse_categories,
    remove_keywords,
    validate_max_papers,
    validate_score,
    validate_weight,
)


def _as_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        return list(value)
    return [str(value)]


def build_proposal(actions: list[dict]) -> dict:
    include = list(get("interests.keywords_include", []))
    exclude = list(get("interests.keywords_exclude", []))
    weights = dict(get("interests.keyword_weights", {}) or {})
    changes: list[dict] = []
    errors: list[str] = []
    notes: list[str] = []

    for action in actions:
        act = action.get("action", "none")

        if act in ("add_keywords", "add_exclude"):
            current = include if act == "add_keywords" else exclude
            updated, added, duplicates = add_keywords(current, _as_list(action.get("keywords")))
            if act == "add_keywords":
                include = updated
            else:
                exclude = updated
            for keyword in added:
                changes.append({
                    "op": "+",
                    "field": "include" if act == "add_keywords" else "exclude",
                    "value": keyword,
                    "weight": weights.get(keyword, 1),
                })
            if duplicates:
                notes.append(f"Already present: {', '.join(duplicates)}")

        elif act in ("remove_keywords", "remove_exclude"):
            current = include if act == "remove_keywords" else exclude
            updated, removed, missing = remove_keywords(current, _as_list(action.get("keywords")))
            if act == "remove_keywords":
                include = updated
                weights = drop_weights(weights, removed)
            else:
                exclude = updated
            for keyword in removed:
                changes.append({
                    "op": "-",
                    "field": "include" if act == "remove_keywords" else "exclude",
                    "value": keyword,
                })
            if missing:
                notes.append(f"Not found: {', '.join(missing)}")

        elif act == "set_categories":
            valid, invalid = parse_categories(_as_list(action.get("categories")))
            if invalid:
                errors.append(f"Unknown categories: {', '.join(invalid)}")
            elif not valid:
                errors.append("No categories provided")
            elif valid != get("interests.categories", []):
                changes.append({
                    "op": "~",
                    "field": "categories",
                    "before": ", ".join(get("interests.categories", [])),
                    "after": ", ".join(valid),
                })

        elif act == "set_max_papers":
            try:
                value = validate_max_papers(action.get("value"))
            except ValueError as exc:
                errors.append(str(exc))
            else:
                before = get("daily.max_papers", 20)
                if value != before:
                    changes.append({"op": "~", "field": "max_papers", "before": before, "after": value})

        elif act == "set_min_score":
            try:
                value = validate_score(action.get("value"))
            except ValueError as exc:
                errors.append(str(exc))
            else:
                before = get("daily.min_relevance_score", 5)
                if value != before:
                    changes.append({"op": "~", "field": "min_score", "before": before, "after": value})

        elif act == "set_keyword_weight":
            keyword = canonical_keyword(include, str(action.get("keyword", "")))
            if keyword is None:
                errors.append(f"Keyword not in include list: {action.get('keyword', '')}")
            else:
                try:
                    value = validate_weight(action.get("weight"))
                except ValueError as exc:
                    errors.append(str(exc))
                else:
                    before = weights.get(keyword, 1)
                    if value != before:
                        changes.append({
                            "op": "~",
                            "field": f"weight:{keyword}",
                            "before": before,
                            "after": value,
                        })
                        weights[keyword] = value

    return {
        "changes": changes,
        "errors": errors,
        "notes": notes,
        "actions": actions,
        "has_changes": bool(changes),
    }


def format_proposal(proposal: dict) -> str:
    lines = ["Proposed changes:"]
    for change in proposal["changes"]:
        op = change["op"]
        field = change["field"]
        if op in ("+", "-"):
            suffix = ""
            if op == "+" and change.get("weight", 1) != 1:
                suffix = f" (weight {change['weight']})"
            lines.append(f"  {op} {field}: {change['value']}{suffix}")
        else:
            lines.append(f"  ~ {field}: {change['before']} -> {change['after']}")
    if not proposal["changes"]:
        lines.append("  (none)")
    for note in proposal.get("notes", []):
        lines.append(f"  i {note}")
    if proposal["errors"]:
        lines.append("Cannot apply:")
        for error in proposal["errors"]:
            lines.append(f"  ! {error}")
    return "\n".join(lines)


def build_proposed_config(actions: list[dict]) -> dict | None:
    original = copy.deepcopy(load_config())
    try:
        for action in actions:
            execute_action(action, persist=False)
        return copy.deepcopy(load_config())
    finally:
        replace(original)


def apply_actions(actions: list[dict]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for action in actions:
        results.extend(execute_action(action))
    return results
