import difflib
import logging
import os
import shlex
import subprocess
import sys
import tempfile

import yaml

from src.config import backup_path, config_path, get, replace, save, undo
from src.chat.engine import build_system_prompt, execute_action, parse_response_stream
from src.chat.proposal import (
    apply_actions,
    build_proposal,
    build_proposed_config,
    format_proposal,
)
from src.chat.screen import Screen, _action_icon, _bold, _cyan, _dim, _green, _yellow
from src.pipeline.preview import format_preview, preview_papers

try:
    from rich.console import Console

    from src.chat import ui

    _RICH_AVAILABLE = True
except ImportError:
    Console = None
    ui = None
    _RICH_AVAILABLE = False

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory, InMemoryHistory

    _PROMPT_AVAILABLE = True
except ImportError:
    PromptSession = None
    AutoSuggestFromHistory = None
    Completer = None
    Completion = None
    FileHistory = None
    InMemoryHistory = None
    _PROMPT_AVAILABLE = False

logger = logging.getLogger(__name__)

SLASH_COMMANDS = {
    "/add": "add_keywords",
    "/rm": "remove_keywords",
    "/exclude": "add_exclude",
    "/unexclude": "remove_exclude",
    "/cats": "set_categories",
    "/score": "set_min_score",
    "/max": "set_max_papers",
    "/weight": "set_keyword_weight",
}


def _clear_screen() -> None:
    print("\033[H\033[J", end="")


def _stdio_is_tty() -> bool:
    stdin_tty = getattr(sys.stdin, "isatty", lambda: False)()
    stdout_tty = getattr(sys.stdout, "isatty", lambda: False)()
    return bool(stdin_tty and stdout_tty)


def _use_rich() -> bool:
    return _RICH_AVAILABLE and _stdio_is_tty()


def _init_readline() -> None:
    try:
        import readline
        hist_file = os.path.expanduser(get("paths.readline_history", "~/.daily_papers_history"))
        try:
            readline.read_history_file(hist_file)
        except (FileNotFoundError, OSError):
            pass
    except ImportError:
        pass


def _save_readline() -> None:
    try:
        import readline
        hist_file = os.path.expanduser(get("paths.readline_history", "~/.daily_papers_history"))
        readline.write_history_file(hist_file)
    except (ImportError, OSError):
        pass


def _parse_slash_command(user_input: str) -> dict | None:
    if not user_input.startswith("/"):
        return None
    cmd = user_input.split()[0].lower()
    if cmd == "/help":
        return {"action": "show_help"}
    if cmd == "/show":
        return {"action": "show_config"}
    if cmd == "/list":
        return {"action": "show_list"}
    if cmd == "/diff":
        return {"action": "show_diff"}
    if cmd == "/undo":
        return {"action": "undo"}
    if cmd == "/preview":
        days = None
        use_llm = False
        for token in user_input[len(cmd):].strip().split():
            if token.lower() == "llm":
                use_llm = True
                continue
            try:
                days = int(token)
            except ValueError:
                pass
        return {"action": "show_preview", "days": days, "use_llm": use_llm}
    if cmd == "/stats":
        days = None
        for token in user_input[len(cmd):].strip().split():
            try:
                days = int(token)
            except ValueError:
                pass
        return {"action": "show_stats", "days": days}
    if cmd not in SLASH_COMMANDS:
        return None
    action_name = SLASH_COMMANDS[cmd]
    raw_args = user_input[len(cmd):].strip()
    if action_name in ("add_keywords", "remove_keywords", "add_exclude", "remove_exclude"):
        keywords = [k.strip() for k in raw_args.split(",") if k.strip()]
        return {"action": action_name, "keywords": keywords}
    if action_name == "set_categories":
        cats = [c.strip() for c in raw_args.split(",") if c.strip()]
        return {"action": action_name, "categories": cats}
    if action_name in ("set_max_papers", "set_min_score"):
        try:
            val = int(raw_args.strip().split()[0])
        except (ValueError, IndexError):
            val = None
        return {"action": action_name, "value": val}
    if action_name == "set_keyword_weight":
        parts = raw_args.rsplit(None, 1)
        if len(parts) == 2:
            try:
                weight = int(parts[1])
            except ValueError:
                weight = None
            return {"action": action_name, "keyword": parts[0], "weight": weight}
        return {"action": action_name, "keyword": raw_args, "weight": None}


def _print_header() -> None:
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


def _print_help() -> None:
    print(_bold("\nSlash Commands:"))
    for cmd, desc in [
        ("/add k1, k2", "Add keywords to include list"),
        ("/rm k1, k2", "Remove keywords from include list"),
        ("/exclude k1, k2", "Add keywords to exclude list"),
        ("/unexclude k1, k2", "Remove from exclude list"),
        ("/cats c1, c2", "Set arXiv categories"),
        ("/score N", "Set min relevance score (1-10)"),
        ("/max N", "Set max papers/day (1-50)"),
        ("/weight term N", "Set keyword weight (1-5)"),
        ("/list", "Show keyword table"),
        ("/preview [days] [llm]", "Preview candidates; add llm for full scoring"),
        ("/stats [days]", "Show per-keyword hit counts"),
        ("/diff", "Diff the previous saved config"),
        ("/undo", "Restore the previous saved config"),
        ("/show", "Display current config"),
        ("/help", "Show this help"),
        ("/quit, exit, q", "Exit"),
    ]:
        print(f"  {_cyan(cmd):30s} {desc}")
    print()


def _build_completer():
    if not _PROMPT_AVAILABLE:
        return None

    class SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            if not text.startswith("/"):
                return
            if " " not in text:
                for command in sorted({*SLASH_COMMANDS, "/help", "/show", "/list", "/preview", "/stats", "/diff", "/undo"}):
                    if command.startswith(text):
                        yield Completion(command, start_position=-len(text))
                return
            command, rest = text.split(" ", 1)
            prefix = rest.strip()
            if command in ("/rm", "/unexclude"):
                candidates = get("interests.keywords_include", [])
                if command == "/unexclude":
                    candidates = get("interests.keywords_exclude", [])
            elif command == "/exclude":
                candidates = get("interests.keywords_exclude", [])
            elif command == "/weight":
                candidates = get("interests.keywords_include", [])
            else:
                candidates = []
            for keyword in candidates:
                if keyword.lower().startswith(prefix.lower()):
                    yield Completion(keyword, start_position=-len(prefix))

    return SlashCompleter()


def _make_session(input=None, output=None):
    if not (_PROMPT_AVAILABLE and _use_rich()):
        return None
    history_path = os.path.expanduser(get("paths.readline_history", "~/.daily_papers_history"))
    history_dir = os.path.dirname(history_path) or "."
    try:
        if not os.access(history_dir, os.W_OK):
            raise OSError("history directory is not writable")
        history = FileHistory(history_path)
    except OSError:
        history = InMemoryHistory()
    return PromptSession(
        history=history,
        auto_suggest=AutoSuggestFromHistory(),
        completer=_build_completer(),
        complete_while_typing=False,
        enable_history_search=True,
        input=input,
        output=output,
    )


def _read_line(session, prompt: str = "> ") -> str:
    if session is not None:
        return session.prompt(prompt, bottom_toolbar=ui.status_text if ui else None)
    return input("\033[32m> \033[0m" if _stdio_is_tty() else prompt)


def _render_message(screen, console, text: str) -> None:
    if console is not None:
        ui.print_markdown(console, text)
    elif screen is not None:
        screen.writeln(text)
    elif text:
        print(text)


def _render_results(console, screen, action: dict, results: list[tuple[str, str]]) -> None:
    if console is not None:
        styles = {"green": "green", "yellow": "yellow", "red": "red"}
        for color, message in results:
            console.print(f"  {_action_icon(action.get('action', ''))} {message}", style=styles.get(color, "default"))
        return
    for _color, message in results:
        print(f"  {_action_icon(action.get('action', ''))} {message}")


def _render_status(console, screen) -> None:
    if console is not None:
        console.print(ui.status_text(), style="dim")
    elif screen is not None:
        screen.show_config_status()


def _render_error(console, screen, exc: Exception) -> None:
    if console is not None:
        console.print(ui.error_panel(str(exc)))
    elif screen is not None:
        screen.writeln(f"Error: {exc}")
    else:
        print(f"\n  {_yellow('Error:')} {exc}\n")


def _handle_preview(console, screen, action: dict) -> None:
    if console is not None:
        with console.status("Fetching papers...", spinner="dots"):
            result = preview_papers(
                days=action.get("days"),
                use_cache=True,
                use_llm=bool(action.get("use_llm")),
            )
    else:
        result = preview_papers(
            days=action.get("days"),
            use_cache=True,
            use_llm=bool(action.get("use_llm")),
        )
    if console is not None:
        console.print(ui.preview_table(result))
        console.print(ui.stats_table(result["stats"], result.get("keyword_weights", {})))
        if result.get("llm_results") is not None:
            console.print(ui.llm_table(result))
    else:
        print(format_preview(result, show_stats=True))


def _handle_stats(console, screen, action: dict) -> None:
    if console is not None:
        with console.status("Fetching papers...", spinner="dots"):
            result = preview_papers(days=action.get("days"), use_cache=True)
    else:
        result = preview_papers(days=action.get("days"), use_cache=True)
    if console is not None:
        console.print(ui.stats_table(result["stats"], result.get("keyword_weights", {})))
    else:
        print(f"Fetched {result['fetched']} papers")
        weights = result.get("keyword_weights", {})
        for keyword, count in sorted(result["stats"].items(), key=lambda item: (-item[1], item[0])):
            suffix = f" (weight {weights.get(keyword, 1)})" if weights.get(keyword, 1) != 1 else ""
            print(f"  {count:>3}  {keyword}{suffix}")


def _show_diff(console) -> None:
    backup = backup_path()
    current = config_path()
    if not backup.exists():
        text = "No previous config version available."
    else:
        diff = difflib.unified_diff(
            backup.read_text(encoding="utf-8").splitlines(),
            current.read_text(encoding="utf-8").splitlines(),
            fromfile=backup.name,
            tofile=current.name,
            lineterm="",
        )
        text = "\n".join(diff) or "No changes."
    if console is not None:
        console.print(ui.diff_syntax(text))
    else:
        print(text)


def _edit_proposal(actions: list[dict], console, session) -> str:
    proposed = build_proposed_config(actions)
    if proposed is None:
        if console is not None:
            console.print(ui.error_panel("Could not build a proposed config."))
        else:
            print("Could not build a proposed config.")
        return "reject"

    handle, path = tempfile.mkstemp(prefix="dailypapers-proposal-", suffix=".yaml")
    os.close(handle)
    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(proposed, f, allow_unicode=True, sort_keys=False)
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        try:
            subprocess.run([*shlex.split(editor), path], check=False)
        except OSError as exc:
            if console is not None:
                console.print(ui.error_panel(f"Editor failed: {exc}"))
            else:
                print(f"Editor failed: {exc}")
            return "reject"
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            if console is not None:
                console.print(ui.error_panel("Edited config is not a YAML mapping."))
            else:
                print("Edited config is not a YAML mapping.")
            return "reject"
        replace(data)
        save()
        if console is not None:
            console.print("Applied edited config.", style="green")
        else:
            print("Applied edited config.")
        return "edited"
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _confirm_proposal(proposal: dict, console, session) -> str:
    text = format_proposal(proposal)
    if console is not None:
        console.print(ui.proposal_panel(text))
    else:
        print(text)
    if proposal["errors"]:
        return "invalid"
    if not proposal["has_changes"]:
        if console is not None:
            console.print("No config changes to apply.", style="yellow")
        else:
            print("No config changes to apply.")
        return "noop"
    prompt = "Apply? [a]pply / [e]dit / [r]eject: "
    choice = _read_line(session, prompt).strip().lower()
    if choice in ("a", "apply", "y", "yes"):
        return "apply"
    if choice in ("e", "edit"):
        return _edit_proposal(proposal["actions"], console, session)
    return "reject"


def _stream_ai_response(
    messages: list[dict],
    screen: Screen | None = None,
    *,
    console=None,
    session=None,
    confirm_actions=None,
) -> None:
    final_chat = ""
    final_actions: list[dict] = []
    printed_text = 0
    rich = console is not None
    status = None

    if rich:
        status = console.status("Thinking...", spinner="dots")
        status.start()
    elif screen is not None:
        screen.show_thinking()

    try:
        for _reasoning, text, chat, actions, is_final in parse_response_stream(messages):
            if not rich and len(text) > printed_text:
                new = text[printed_text:]
                printed_text = len(text)
                if screen is not None:
                    screen.write(new)
                else:
                    print(new, end="", flush=True)
            if is_final:
                final_chat = chat
                final_actions = actions
    finally:
        if status is not None:
            status.stop()
        if screen is not None and not rich:
            screen.hide_thinking()

    if rich:
        ui.print_markdown(console, final_chat or ("Proposed config changes." if final_actions else ""))
    elif screen is not None:
        screen.writeln()
    elif printed_text:
        print()

    if final_actions:
        proposal = build_proposal(final_actions)
        if confirm_actions is not None:
            decision = confirm_actions(proposal)
            if decision == "apply":
                results = apply_actions(final_actions)
            elif decision == "edited":
                results = []
                _render_status(console, screen)
            else:
                results = []
                if decision == "reject":
                    if console is not None:
                        console.print("Changes rejected.", style="yellow")
                    elif screen is not None:
                        screen.writeln("Changes rejected.")
                    else:
                        print("Changes rejected.")
        else:
            results = apply_actions(final_actions)

        if results:
            action = final_actions[0] if len(final_actions) == 1 else {"action": "none"}
            _render_results(console, screen, action, results)
            if console is not None or screen is not None:
                _render_status(console, screen)

    messages.append({"role": "assistant", "content": final_chat})


def run_tui(initial_messages: list[dict] | None = None) -> None:
    rich = _use_rich()
    console = Console() if rich else None
    session = _make_session() if rich else None
    screen = None if rich else Screen()
    if not rich:
        _init_readline()

    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    if initial_messages:
        messages = initial_messages + messages[1:]

    if console is not None:
        ui.render_header(console)
        if initial_messages:
            ui.render_history(console, initial_messages)
    elif screen is not None:
        screen.render_header()
        if initial_messages:
            screen.render_message_history(initial_messages)

    while True:
        try:
            user_input = _read_line(session).strip()
        except (EOFError, KeyboardInterrupt):
            if not rich:
                _save_readline()
            if console is not None:
                console.print("\nBye.", style="green")
            else:
                print(_green("\nBye."))
            return

        if not user_input:
            continue

        if user_input.lower() in ("/quit", "/q", "quit", "exit", "q", "done"):
            if not rich:
                _save_readline()
            if console is not None:
                console.print("Bye.", style="green")
            else:
                print(_green("Bye."))
            return

        slash_action = _parse_slash_command(user_input)
        if slash_action is not None:
            action = slash_action
            name = action.get("action")
            if name == "show_help":
                if console is not None:
                    console.print(ui.help_table())
                else:
                    _print_help()
                continue
            if name in ("show_config", "show_list"):
                if console is not None:
                    ui.render_header(console)
                    if name == "show_list":
                        console.print(ui.keyword_tables())
                else:
                    _print_header()
                continue
            if name == "show_preview":
                try:
                    _handle_preview(console, screen, action)
                except Exception as exc:
                    _render_error(console, screen, exc)
                continue
            if name == "show_stats":
                try:
                    _handle_stats(console, screen, action)
                except Exception as exc:
                    _render_error(console, screen, exc)
                continue
            if name == "show_diff":
                try:
                    _show_diff(console)
                except Exception as exc:
                    _render_error(console, screen, exc)
                continue
            if name == "undo":
                try:
                    restored = undo()
                except Exception as exc:
                    _render_error(console, screen, exc)
                    continue
                if restored:
                    message = "Restored previous config."
                    style = "green"
                else:
                    message = "No previous config version to restore."
                    style = "yellow"
                if console is not None:
                    console.print(message, style=style)
                    ui.render_header(console)
                else:
                    print(message)
                    _print_header()
                continue
            results = execute_action(action)
            _render_results(console, screen, action, results)
            _render_status(console, screen)
            continue

        messages[0] = {"role": "system", "content": build_system_prompt()}
        messages.append({"role": "user", "content": user_input})

        try:
            _stream_ai_response(
                messages,
                screen,
                console=console,
                session=session,
                confirm_actions=lambda proposal: _confirm_proposal(proposal, console, session),
            )
        except (EOFError, KeyboardInterrupt):
            if not rich:
                _save_readline()
            if console is not None:
                console.print("\nBye.", style="green")
            else:
                print(_green("\nBye."))
            return
        except Exception as exc:
            _render_error(console, screen, exc)
            if messages and messages[-1]["role"] == "user":
                messages.pop()
