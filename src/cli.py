import argparse
import difflib
import json
import sys

from src import config
from src.config import get, set as config_set, save
from src.interests import (
    add_keywords,
    canonical_keyword,
    category_help,
    drop_weights,
    parse_categories,
    remove_keywords,
    validate_max_papers,
    validate_score,
    validate_weight,
)
from src.pipeline.preview import format_preview, preview_papers, preview_to_json


def _split_items(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        result.extend(part.strip() for part in item.split(",") if part.strip())
    return result


def _keyword_key(exclude: bool) -> str:
    return "interests.keywords_exclude" if exclude else "interests.keywords_include"


def _cmd_list(args: argparse.Namespace) -> int:
    include = list(get("interests.keywords_include", []))
    exclude = list(get("interests.keywords_exclude", []))
    categories = list(get("interests.categories", []))
    max_papers = get("daily.max_papers", 20)
    min_score = get("daily.min_relevance_score", 5)
    weights = dict(get("interests.keyword_weights", {}) or {})

    if args.json:
        print(json.dumps({
            "include": include,
            "exclude": exclude,
            "categories": categories,
            "keyword_weights": weights,
            "max_papers": max_papers,
            "min_relevance_score": min_score,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"Include ({len(include)}):")
    for index, keyword in enumerate(include, 1):
        weight = weights.get(keyword, 1)
        suffix = f"  (weight {weight})" if weight != 1 else ""
        print(f"  {index:>2}. {keyword}{suffix}")
    print(f"Exclude ({len(exclude)}):")
    for index, keyword in enumerate(exclude, 1):
        print(f"  {index:>2}. {keyword}")
    print(f"Categories: {', '.join(categories) if categories else '(none)'}")
    print(f"Daily: max={max_papers}, min_score={min_score}")
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    key = _keyword_key(args.exclude)
    current = list(get(key, []))
    updated, added, duplicates = add_keywords(current, _split_items(args.items))

    if added:
        config_set(key, updated)
        save()
        print(f"Added: {', '.join(added)}")
    if duplicates:
        print(f"Already present: {', '.join(duplicates)}")
    if not added and not duplicates:
        print("No keywords provided.")
        return 1
    return 0


def _cmd_rm(args: argparse.Namespace) -> int:
    key = _keyword_key(args.exclude)
    current = list(get(key, []))
    targets: list[str] = []
    had_error = False

    for token in _split_items(args.items):
        if token.isdigit():
            index = int(token)
            if 1 <= index <= len(current):
                targets.append(current[index - 1])
            else:
                print(f"Index {index} out of range (1-{len(current)})", file=sys.stderr)
                had_error = True
                continue
        else:
            targets.append(token)

    updated, removed, missing = remove_keywords(current, targets)
    if removed:
        config_set(key, updated)
        if not args.exclude:
            weights = dict(get("interests.keyword_weights", {}) or {})
            config_set("interests.keyword_weights", drop_weights(weights, removed))
        save()
        print(f"Removed: {', '.join(removed)}")
    if missing:
        print(f"Not found: {', '.join(missing)}")
    if not removed and not missing:
        print("No matching keywords.")
        return 1
    return 1 if had_error else 0


def _cmd_set(args: argparse.Namespace) -> int:
    raw_value = " ".join(args.value).strip()
    try:
        if args.key == "score":
            value = validate_score(raw_value)
            config_set("daily.min_relevance_score", value)
            print(f"Min score set to {value}")
        elif args.key == "max":
            value = validate_max_papers(raw_value)
            config_set("daily.max_papers", value)
            print(f"Max papers set to {value}")
        elif args.key == "weight":
            if len(args.value) < 2:
                raise ValueError("Usage: set weight <keyword> <1-5>")
            term = " ".join(args.value[:-1]).strip()
            keyword = canonical_keyword(list(get("interests.keywords_include", [])), term)
            if keyword is None:
                raise ValueError(f"Keyword not in include list: {term}")
            weight = validate_weight(args.value[-1])
            weights = dict(get("interests.keyword_weights", {}) or {})
            weights[keyword] = weight
            config_set("interests.keyword_weights", weights)
            print(f"Weight for {keyword} set to {weight}")
        else:
            valid, invalid = parse_categories(args.value)
            if invalid:
                raise ValueError(f"Unknown categories: {', '.join(invalid)}. Valid: {category_help()}")
            if not valid:
                raise ValueError(f"No categories provided. Valid: {category_help()}")
            config_set("interests.categories", valid)
            print(f"Categories set to: {', '.join(valid)}")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    save()
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    result = preview_papers(
        days=args.days,
        top_n=args.top,
        use_cache=not args.no_cache,
        use_llm=args.llm,
    )
    if args.json:
        print(json.dumps(preview_to_json(result), ensure_ascii=False, indent=2))
    else:
        print(format_preview(result, show_excluded=args.show_excluded, show_stats=args.stats))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    result = preview_papers(days=args.days, use_cache=not args.no_cache)
    stats = result["stats"]
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    print(f"Fetched {result['fetched']} papers")
    if not stats:
        print("  (no keywords configured)")
        return 0
    for keyword, count in sorted(stats.items(), key=lambda item: (-item[1], item[0])):
        print(f"  {count:>3}  {keyword}")
    return 0


def _cmd_diff(args: argparse.Namespace) -> int:
    current = config.config_path()
    backup = config.backup_path()
    if not backup.exists():
        print("No previous config version available.")
        return 0
    diff = difflib.unified_diff(
        backup.read_text(encoding="utf-8").splitlines(),
        current.read_text(encoding="utf-8").splitlines(),
        fromfile=backup.name,
        tofile=current.name,
        lineterm="",
    )
    output = "\n".join(diff)
    print(output if output else "No changes.")
    return 0


def _cmd_undo(args: argparse.Namespace) -> int:
    if config.undo():
        print("Restored previous config.")
        return 0
    print("No previous config version to restore.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="update.py",
        description="Manage MyArxiv interests, or run the interactive TUI with no arguments.",
    )
    sub = parser.add_subparsers(dest="command")

    list_parser = sub.add_parser("list", help="show current interests")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(handler=_cmd_list)

    add_parser = sub.add_parser("add", help="add include/exclude keywords")
    add_parser.add_argument("items", nargs="+", help="keywords, comma-separated or space-separated")
    add_parser.add_argument("--exclude", action="store_true", help="add to the exclude list")
    add_parser.set_defaults(handler=_cmd_add)

    rm_parser = sub.add_parser("rm", help="remove keywords by 1-based index or text")
    rm_parser.add_argument("items", nargs="+", help="indices (e.g. 3,5) or keywords")
    rm_parser.add_argument("--exclude", action="store_true", help="remove from the exclude list")
    rm_parser.set_defaults(handler=_cmd_rm)

    set_parser = sub.add_parser("set", help="set score, max papers, categories, or keyword weight")
    set_parser.add_argument("key", choices=["score", "max", "cats", "weight"])
    set_parser.add_argument("value", nargs="+")
    set_parser.set_defaults(handler=_cmd_set)

    preview_parser = sub.add_parser("preview", help="preview keyword filtering on fetched papers")
    preview_parser.add_argument("--days", type=int, default=None)
    preview_parser.add_argument("--top", type=int, default=None)
    preview_parser.add_argument("--json", action="store_true")
    preview_parser.add_argument("--no-cache", action="store_true")
    preview_parser.add_argument("--show-excluded", action="store_true")
    preview_parser.add_argument("--stats", action="store_true")
    preview_parser.add_argument("--llm", action="store_true", help="run full LLM scoring (costs API calls)")
    preview_parser.set_defaults(handler=_cmd_preview)

    stats_parser = sub.add_parser("stats", help="show per-keyword hit counts")
    stats_parser.add_argument("--days", type=int, default=None)
    stats_parser.add_argument("--json", action="store_true")
    stats_parser.add_argument("--no-cache", action="store_true")
    stats_parser.set_defaults(handler=_cmd_stats)

    diff_parser = sub.add_parser("diff", help="diff the previous saved config against the current one")
    diff_parser.set_defaults(handler=_cmd_diff)

    undo_parser = sub.add_parser("undo", help="restore the previous saved config")
    undo_parser.set_defaults(handler=_cmd_undo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        from src.chat.terminal import run_tui

        run_tui()
        return 0

    try:
        return args.handler(args)
    except (ValueError, FileNotFoundError, OSError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
