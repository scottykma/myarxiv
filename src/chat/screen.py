import logging

from src.config import get

logger = logging.getLogger(__name__)

_ACTION_ICONS = {
    "add_keywords": "\u2705",
    "remove_keywords": "\U0001f5d1\ufe0f",
    "add_exclude": "\U0001f6ab",
    "remove_exclude": "\u267b\ufe0f",
    "set_categories": "\U0001f4c2",
    "set_max_papers": "\U0001f4ca",
    "set_min_score": "\U0001f3af",
    "suggest": "\U0001f4a1",
    "none": "\u2139\ufe0f",
}


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m"


def _dim(s: str) -> str:
    return f"\033[2m{s}\033[0m"


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m"


def _cyan(s: str) -> str:
    return f"\033[36m{s}\033[0m"


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m"


def _action_icon(action: str) -> str:
    return _ACTION_ICONS.get(action, "\u2022")


class Screen:
    def __init__(self):
        self._header_printed = False
        self._thinking = False

    def render_header(self) -> None:
        if self._header_printed:
            return

        include = get("interests.keywords_include", [])
        exclude = get("interests.keywords_exclude", [])
        categories = get("interests.categories", [])
        weights = dict(get("interests.keyword_weights", {}) or {})

        print(_bold("  MyArxiv - Interest Manager"))
        print(f"  {_cyan('Keywords')} ({len(include)}): {', '.join(include) if include else '(none)'}")
        print(f"  {_cyan('Weights')}: {', '.join(f'{k}×{v}' for k, v in weights.items()) if weights else '(default 1)'}")
        print(f"  {_cyan('Exclude')}  ({len(exclude)}): {', '.join(exclude) if exclude else '(none)'}")
        print(f"  {_cyan('Categories')}: {', '.join(categories) if categories else '(none)'}")
        print(f"  {_cyan('Max/Day')}: {get('daily.max_papers', 20)}  |  {_cyan('Min Score')}: {get('daily.min_relevance_score', 7)}")
        print()

        self._header_printed = True

    def render_message_history(self, messages: list[dict]) -> None:
        for msg in messages:
            if msg.get("role") == "system":
                continue
            if msg.get("role") == "user":
                print(f"{_green('>')} {msg['content']}")
            elif msg.get("role") == "assistant":
                print(f"{_cyan('\u25cf')} {msg['content']}")

    def show_thinking(self) -> None:
        print(_dim("\u25cf Thinking..."), end="", flush=True)
        self._thinking = True

    def hide_thinking(self) -> None:
        if not self._thinking:
            return
        print("\r\033[K", end="", flush=True)
        self._thinking = False

    def write(self, text: str) -> None:
        if self._thinking:
            self.hide_thinking()
        print(text, end="", flush=True)

    def writeln(self, text: str = "") -> None:
        if self._thinking:
            self.hide_thinking()
        print(text, flush=True)

    def show_actions(self, action: dict, results: list[tuple[str, str]]) -> None:
        icon = _action_icon(action.get("action", ""))
        for _color, msg in results:
            print(f"    {icon} {msg}")

    def show_config_status(self) -> None:
        include = get("interests.keywords_include", [])
        exclude = get("interests.keywords_exclude", [])
        categories = get("interests.categories", [])
        max_papers = get("daily.max_papers", 20)
        min_score = get("daily.min_relevance_score", 7)
        weights = dict(get("interests.keyword_weights", {}) or {})
        parts = [
            f"{_cyan('Keywords')}: {len(include)}",
            f"{_cyan('Exclude')}: {len(exclude)}",
            f"{_cyan('Weights')}: {len(weights)}",
            f"{_cyan('Cats')}: {', '.join(categories) if categories else 'none'}",
            f"{_cyan('Max')}: {max_papers}",
            f"{_cyan('Min')}: {min_score}",
        ]
        print(_dim("\u2500" * 40))
        print(f"  {' | '.join(parts)}")
        print()

    def show_continue_prompt(self) -> None:
        print(f"\n{_dim('Press Enter to continue...')}")
