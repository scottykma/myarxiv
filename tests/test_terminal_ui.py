import io
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

import src.chat.terminal as terminal
from src import config
from src.chat.proposal import build_proposal
from src.chat.terminal import (
    _build_completer,
    _confirm_proposal,
    _edit_proposal,
    _handle_preview,
    _handle_stats,
    _make_session,
    _parse_slash_command,
    _print_header,
    _print_help,
    _read_line,
    _render_message,
    _render_results,
    _render_status,
    _show_diff,
    _stdio_is_tty,
    _stream_ai_response,
    _use_rich,
    run_tui,
)


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=140, color_system=None)
    return console, buffer


def _paper(title="Video generation with memory"):
    return SimpleNamespace(title=title)


def _preview_result(with_llm: bool = False) -> dict:
    result = {
        "fetched": 2,
        "candidates": [{"paper": _paper(), "score": 9, "keywords": ["video generation"]}],
        "excluded": [{"paper": _paper("Time series"), "keyword": "time series"}],
        "stats": {"video generation": 1, "world model": 0},
        "keyword_weights": {"video generation": 3},
        "include_keywords": ["video generation"],
        "exclude_keywords": ["time series"],
    }
    if with_llm:
        result["llm_results"] = [(_paper(), 8, "relevant")]
    return result


class FakeSession:
    def __init__(self, inputs):
        self.inputs = iter(inputs)
        self.prompts = []

    def prompt(self, prompt="", **kwargs):
        self.prompts.append(prompt)
        return next(self.inputs)


@pytest.mark.unit
class TestTerminalBasics:
    def test_stdio_is_tty(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
        monkeypatch.setattr(sys, "stdout", SimpleNamespace(isatty=lambda: True))
        assert _stdio_is_tty() is True
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: False))
        assert _stdio_is_tty() is False

    def test_use_rich(self, monkeypatch):
        monkeypatch.setattr(terminal, "_RICH_AVAILABLE", True)
        monkeypatch.setattr(terminal, "_stdio_is_tty", lambda: True)
        assert _use_rich() is True
        monkeypatch.setattr(terminal, "_RICH_AVAILABLE", False)
        assert _use_rich() is False

    def test_parse_new_commands(self):
        assert _parse_slash_command("/list") == {"action": "show_list"}
        assert _parse_slash_command("/diff") == {"action": "show_diff"}
        assert _parse_slash_command("/undo") == {"action": "undo"}
        assert _parse_slash_command("/preview 3 llm") == {
            "action": "show_preview",
            "days": 3,
            "use_llm": True,
        }
        assert _parse_slash_command("/preview bad") == {
            "action": "show_preview",
            "days": None,
            "use_llm": False,
        }
        assert _parse_slash_command("/stats 2") == {"action": "show_stats", "days": 2}
        assert _parse_slash_command("/stats bad") == {"action": "show_stats", "days": None}

    def test_parse_weight(self):
        assert _parse_slash_command("/weight video generation 3") == {
            "action": "set_keyword_weight",
            "keyword": "video generation",
            "weight": 3,
        }
        assert _parse_slash_command("/weight video")["weight"] is None
        assert _parse_slash_command("/weight video bad")["weight"] is None

    def test_print_header_includes_weights(self, temp_config_dir, capsys):
        config.set("interests.keyword_weights", {"agent": 3})
        _print_header()
        out = capsys.readouterr().out
        assert "Weights" in out
        assert "agent×3" in out

    def test_print_help_new_commands(self, capsys):
        _print_help()
        out = capsys.readouterr().out
        assert "/preview" in out
        assert "/weight" in out


@pytest.mark.unit
class TestCompleter:
    def test_command_completion(self, temp_config_dir):
        from prompt_toolkit.document import Document

        completer = _build_completer()
        completions = list(completer.get_completions(Document("/", 1), None))
        assert any(c.text == "/add" for c in completions)
        assert any(c.text == "/preview" for c in completions)

    def test_keyword_completion(self, temp_config_dir):
        from prompt_toolkit.document import Document

        completer = _build_completer()
        project = terminal.get("interests.keywords_include")[0]
        prefix = project[:2]
        completions = list(completer.get_completions(Document(f"/rm {prefix}", len(prefix) + 4), None))
        assert any(c.text == project for c in completions)

    def test_unexclude_exclude_weight_completion(self, temp_config_dir):
        from prompt_toolkit.document import Document

        completer = _build_completer()
        for command, expected in [
            ("/exclude su", "survey"),
            ("/unexclude su", "survey"),
            ("/weight ag", "agent"),
        ]:
            completions = list(completer.get_completions(Document(command, len(command)), None))
            assert any(c.text == expected for c in completions)

    def test_no_completion_for_plain_text(self, temp_config_dir):
        from prompt_toolkit.document import Document

        completer = _build_completer()
        assert list(completer.get_completions(Document("hello", 5), None)) == []

    def test_no_completion_for_other_command(self, temp_config_dir):
        from prompt_toolkit.document import Document

        completer = _build_completer()
        assert list(completer.get_completions(Document("/add foo", 8), None)) == []

    def test_completer_disabled(self, monkeypatch):
        monkeypatch.setattr(terminal, "_PROMPT_AVAILABLE", False)
        assert _build_completer() is None


@pytest.mark.unit
class TestSession:
    def test_no_session_when_not_rich(self, monkeypatch):
        monkeypatch.setattr(terminal, "_use_rich", lambda: False)
        assert _make_session() is None

    def test_session_builds(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr(terminal, "_use_rich", lambda: True)
        monkeypatch.setattr(terminal, "PromptSession", MagicMock())
        monkeypatch.setattr(terminal, "FileHistory", MagicMock())
        session = _make_session()
        assert session is not None

    def test_session_falls_back_to_memory_history(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr(terminal, "_use_rich", lambda: True)
        monkeypatch.setattr(terminal, "PromptSession", MagicMock())
        monkeypatch.setattr(terminal, "FileHistory", MagicMock(side_effect=OSError("no home")))
        session = _make_session()
        assert session is not None

    def test_real_prompt_toolkit_session(self, temp_config_dir, monkeypatch):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        monkeypatch.setattr(terminal, "_use_rich", lambda: True)
        with create_pipe_input() as pipe:
            session = _make_session(input=pipe, output=DummyOutput())
            pipe.send_text("hello\r")
            assert _read_line(session) == "hello"
        assert session is not None

    def test_read_line_uses_session(self):
        session = MagicMock()
        session.prompt.return_value = "hello"
        assert _read_line(session) == "hello"
        session.prompt.assert_called_once()

    def test_read_line_uses_input(self, monkeypatch):
        monkeypatch.setattr(terminal, "_stdio_is_tty", lambda: False)
        monkeypatch.setattr("builtins.input", lambda prompt: "typed")
        assert _read_line(None) == "typed"


@pytest.mark.unit
class TestRendering:
    def test_render_message_console(self):
        console, buffer = _console()
        _render_message(None, console, "hello")
        assert "hello" in buffer.getvalue()

    def test_render_message_screen(self):
        screen = MagicMock()
        _render_message(screen, None, "hello")
        screen.writeln.assert_called_once_with("hello")

    def test_render_message_plain(self, capsys):
        _render_message(None, None, "hello")
        assert "hello" in capsys.readouterr().out

    def test_render_message_empty_plain(self, capsys):
        _render_message(None, None, "")
        assert capsys.readouterr().out == ""

    def test_render_results_console(self):
        console, buffer = _console()
        _render_results(console, None, {"action": "add_keywords"}, [("green", "Added: x")])
        assert "Added: x" in buffer.getvalue()

    def test_render_results_plain(self, capsys):
        _render_results(None, None, {"action": "add_keywords"}, [("green", "Added: x")])
        assert "Added: x" in capsys.readouterr().out

    def test_render_status_console(self):
        console, buffer = _console()
        _render_status(console, None)
        assert "keywords" in buffer.getvalue()

    def test_render_status_screen(self):
        screen = MagicMock()
        _render_status(None, screen)
        screen.show_config_status.assert_called_once()


@pytest.mark.unit
class TestHandlers:
    def test_handle_preview_console(self):
        console, buffer = _console()
        with patch("src.chat.terminal.preview_papers", return_value=_preview_result(True)):
            _handle_preview(console, None, {"days": 3, "use_llm": True})
        output = buffer.getvalue()
        assert "Candidates" in output
        assert "LLM selection" in output

    def test_handle_preview_plain(self, capsys):
        with patch("src.chat.terminal.preview_papers", return_value=_preview_result()):
            _handle_preview(None, None, {"days": 1, "use_llm": False})
        assert "Video generation" in capsys.readouterr().out

    def test_handle_stats_console(self):
        console, buffer = _console()
        with patch("src.chat.terminal.preview_papers", return_value=_preview_result()):
            _handle_stats(console, None, {"days": 1})
        assert "Keyword hits" in buffer.getvalue()

    def test_handle_stats_plain(self, capsys):
        with patch("src.chat.terminal.preview_papers", return_value=_preview_result()):
            _handle_stats(None, None, {"days": 1})
        out = capsys.readouterr().out
        assert "Fetched 2" in out
        assert "weight 3" in out

    def test_show_diff_without_backup(self, temp_config_dir, capsys):
        _show_diff(None)
        assert "No previous" in capsys.readouterr().out

    def test_show_diff_with_backup(self, temp_config_dir, capsys):
        config.set("daily.max_papers", 15)
        config.save()
        config.set("daily.max_papers", 10)
        _show_diff(None)
        assert "max_papers" in capsys.readouterr().out

    def test_show_diff_console(self, temp_config_dir):
        config.set("daily.max_papers", 15)
        config.save()
        config.set("daily.max_papers", 10)
        console, buffer = _console()
        _show_diff(console)
        assert "max_papers" in buffer.getvalue()


@pytest.mark.unit
class TestEditProposal:
    def test_editor_success(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr("src.chat.terminal.build_proposed_config", lambda actions: {"daily": {"max_papers": 10}})
        result = _edit_proposal([], None, None)
        assert result == "edited"
        assert config.get("daily.max_papers") == 10

    def test_editor_oserror(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr("src.chat.terminal.build_proposed_config", lambda actions: {"daily": {}})
        monkeypatch.setattr("src.chat.terminal.subprocess.run", MagicMock(side_effect=OSError("no editor")))
        assert _edit_proposal([], None, None) == "reject"

    def test_invalid_edited_yaml(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr("src.chat.terminal.build_proposed_config", lambda actions: {"daily": {}})

        def _write_invalid(command, check=False):
            with open(command[-1], "w") as f:
                f.write("- not a mapping\n")

        monkeypatch.setattr("src.chat.terminal.subprocess.run", _write_invalid)
        assert _edit_proposal([], None, None) == "reject"

    def test_no_proposed_config(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr("src.chat.terminal.build_proposed_config", lambda actions: None)
        assert _edit_proposal([], None, None) == "reject"

    def test_editor_success_console(self, temp_config_dir, monkeypatch):
        monkeypatch.setattr("src.chat.terminal.build_proposed_config", lambda actions: {"daily": {"max_papers": 10}})
        console, buffer = _console()
        assert _edit_proposal([], console, None) == "edited"
        assert "Applied edited config" in buffer.getvalue()


@pytest.mark.unit
class TestConfirmProposal:
    def test_errors(self):
        assert _confirm_proposal({"errors": ["bad"], "has_changes": False, "changes": []}, None, None) == "invalid"

    def test_no_changes(self):
        assert _confirm_proposal({"errors": [], "has_changes": False, "changes": []}, None, None) == "noop"

    def test_apply(self, monkeypatch):
        monkeypatch.setattr("src.chat.terminal._read_line", lambda session, prompt="> ": "a")
        proposal = {"errors": [], "has_changes": True, "changes": [], "actions": []}
        assert _confirm_proposal(proposal, None, None) == "apply"

    def test_reject(self, monkeypatch):
        monkeypatch.setattr("src.chat.terminal._read_line", lambda session, prompt="> ": "r")
        proposal = {"errors": [], "has_changes": True, "changes": [], "actions": []}
        assert _confirm_proposal(proposal, None, None) == "reject"

    def test_edit(self, monkeypatch):
        monkeypatch.setattr("src.chat.terminal._read_line", lambda session, prompt="> ": "e")
        monkeypatch.setattr("src.chat.terminal._edit_proposal", lambda actions, console, session: "edited")
        proposal = {"errors": [], "has_changes": True, "changes": [], "actions": []}
        assert _confirm_proposal(proposal, None, None) == "edited"


@pytest.mark.unit
class TestStreamRich:
    def test_rich_apply(self, temp_config_dir):
        console, buffer = _console()
        messages = [{"role": "user", "content": "add"}]

        def _fake_stream(messages):
            yield "", "Sure\n/ADD(DiT)", "Sure", [{"action": "add_keywords", "keywords": ["DiT"]}], True

        with patch("src.chat.terminal.parse_response_stream", _fake_stream):
            _stream_ai_response(messages, console=console, confirm_actions=lambda proposal: "apply")
        assert "Sure" in buffer.getvalue()
        assert "DiT" in config.get("interests.keywords_include")

    def test_rich_reject(self, temp_config_dir):
        console, buffer = _console()
        messages = [{"role": "user", "content": "add"}]

        def _fake_stream(messages):
            yield "", "Sure\n/ADD(DiT)", "Sure", [{"action": "add_keywords", "keywords": ["DiT"]}], True

        with patch("src.chat.terminal.parse_response_stream", _fake_stream):
            _stream_ai_response(messages, console=console, confirm_actions=lambda proposal: "reject")
        assert "Changes rejected" in buffer.getvalue()
        assert "DiT" not in config.get("interests.keywords_include")

    def test_rich_edited(self, temp_config_dir):
        console, buffer = _console()
        messages = [{"role": "user", "content": "add"}]

        def _fake_stream(messages):
            yield "", "Sure\n/ADD(DiT)", "Sure", [{"action": "add_keywords", "keywords": ["DiT"]}], True

        with patch("src.chat.terminal.parse_response_stream", _fake_stream):
            _stream_ai_response(messages, console=console, confirm_actions=lambda proposal: "edited")
        assert "keywords" in buffer.getvalue()

    def test_rich_no_actions(self):
        console, buffer = _console()
        messages = [{"role": "user", "content": "hi"}]

        def _fake_stream(messages):
            yield "", "Hello", "Hello", [], True

        with patch("src.chat.terminal.parse_response_stream", _fake_stream):
            _stream_ai_response(messages, console=console)
        assert "Hello" in buffer.getvalue()


@pytest.mark.unit
class TestRunTuiRich:
    def test_rich_commands(self, temp_config_dir, monkeypatch):
        console, buffer = _console()
        session = FakeSession([
            "/help",
            "/list",
            "/show",
            "/stats",
            "/preview 3 llm",
            "/diff",
            "/undo",
            "/weight agent 3",
            "quit",
        ])
        monkeypatch.setattr(terminal, "_use_rich", lambda: True)
        monkeypatch.setattr(terminal, "Console", lambda: console)
        monkeypatch.setattr(terminal, "_make_session", lambda: session)
        with patch("src.chat.terminal.preview_papers", return_value=_preview_result(True)):
            run_tui()
        output = buffer.getvalue()
        assert "Slash commands" in output
        assert "Keyword hits" in output
        assert "LLM selection" in output
        assert config.get("interests.keyword_weights")["agent"] == 3

    def test_rich_initial_messages(self, temp_config_dir, monkeypatch):
        console, buffer = _console()
        session = FakeSession(["quit"])
        monkeypatch.setattr(terminal, "_use_rich", lambda: True)
        monkeypatch.setattr(terminal, "Console", lambda: console)
        monkeypatch.setattr(terminal, "_make_session", lambda: session)
        run_tui(initial_messages=[{"role": "user", "content": "hello"}])
        assert "hello" in buffer.getvalue()

    def test_rich_real_prompt_toolkit_loop(self, temp_config_dir, monkeypatch):
        from prompt_toolkit.input import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        console, buffer = _console()
        monkeypatch.setattr(terminal, "_use_rich", lambda: True)
        monkeypatch.setattr(terminal, "Console", lambda: console)
        with create_pipe_input() as pipe:
            session = _make_session(input=pipe, output=DummyOutput())
            monkeypatch.setattr(terminal, "_make_session", lambda: session)
            pipe.send_text("/list\rquit\r")
            run_tui()
        assert "Include" in buffer.getvalue()


@pytest.mark.unit
class TestRunTuiPlainNewCommands:
    def test_plain_commands(self, temp_config_dir, monkeypatch):
        inputs = iter(["/list", "/stats", "/preview", "/diff", "/undo", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        with patch("src.chat.terminal.preview_papers", return_value=_preview_result()):
            run_tui()

    def test_preview_error_is_reported(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["/preview", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        with patch("src.chat.terminal.preview_papers", side_effect=RuntimeError("fetch failed")):
            run_tui()
        assert "fetch failed" in capsys.readouterr().out
