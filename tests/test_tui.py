import os
from unittest.mock import MagicMock, patch

import pytest

from src.chat.terminal import _action_icon, _bold, _clear_screen, _cyan, _dim, _green, _init_readline, _parse_slash_command, _print_header, _print_help, _save_readline, _yellow


@pytest.mark.unit
class TestParseSlashCommand:
    def test_not_slash(self):
        assert _parse_slash_command("hello world") is None

    def test_unknown_slash(self):
        assert _parse_slash_command("/unknown") is None

    def test_help(self):
        r = _parse_slash_command("/help")
        assert r == {"action": "show_help"}

    def test_add_keywords(self):
        r = _parse_slash_command("/add DiT, attention")
        assert r == {"action": "add_keywords", "keywords": ["DiT", "attention"]}

    def test_add_single(self):
        r = _parse_slash_command("/add DiT")
        assert r == {"action": "add_keywords", "keywords": ["DiT"]}

    def test_rm_keywords(self):
        r = _parse_slash_command("/rm deep, wide")
        assert r == {"action": "remove_keywords", "keywords": ["deep", "wide"]}

    def test_exclude(self):
        r = _parse_slash_command("/exclude nlp, robotics")
        assert r == {"action": "add_exclude", "keywords": ["nlp", "robotics"]}

    def test_unexclude(self):
        r = _parse_slash_command("/unexclude survey")
        assert r == {"action": "remove_exclude", "keywords": ["survey"]}

    def test_cats(self):
        r = _parse_slash_command("/cats cs.CV, cs.AI")
        assert r == {"action": "set_categories", "categories": ["cs.CV", "cs.AI"]}

    def test_score(self):
        r = _parse_slash_command("/score 8")
        assert r == {"action": "set_min_score", "value": 8}

    def test_score_invalid(self):
        r = _parse_slash_command("/score abc")
        assert r == {"action": "set_min_score", "value": None}

    def test_max(self):
        r = _parse_slash_command("/max 15")
        assert r == {"action": "set_max_papers", "value": 15}

    def test_empty_string(self):
        assert _parse_slash_command("") is None


@pytest.mark.unit
class TestActionIcon:
    def test_known_action(self):
        assert _action_icon("add_keywords") == "\u2705"

    def test_unknown_action(self):
        assert _action_icon("unknown") == "\u2022"


@pytest.mark.unit
class TestAnsiHelpers:
    def test_bold(self):
        assert _bold("hello").startswith("\033[1m")
        assert _bold("hello").endswith("\033[0m")

    def test_green(self):
        assert "\033[32m" in _green("ok")

    def test_cyan(self):
        assert "\033[36m" in _cyan("label")

    def test_yellow(self):
        assert "\033[33m" in _yellow("warn")

    def test_dim(self):
        assert "\033[2m" in _dim("faded")

    def test_clear_screen(self, capsys):
        _clear_screen()
        out = capsys.readouterr().out
        assert "\033[H\033[J" in out


@pytest.mark.unit
class TestPrintHeader:
    def test_includes_keywords(self, temp_config_dir, capsys):
        _print_header()
        out = capsys.readouterr().out
        assert "large language model" in out
        assert "agent" in out

    def test_includes_exclude(self, temp_config_dir, capsys):
        _print_header()
        out = capsys.readouterr().out
        assert "survey" in out

    def test_includes_categories(self, temp_config_dir, capsys):
        _print_header()
        out = capsys.readouterr().out
        assert "cs.AI" in out

    def test_includes_max_score(self, temp_config_dir, capsys):
        _print_header()
        out = capsys.readouterr().out
        assert "20" in out
        assert "7" in out


@pytest.mark.unit
class TestPrintHelp:
    def test_shows_all_commands(self, capsys):
        _print_help()
        out = capsys.readouterr().out
        assert "/add" in out
        assert "/rm" in out
        assert "/exclude" in out
        assert "/unexclude" in out
        assert "/cats" in out
        assert "/score" in out
        assert "/max" in out
        assert "/show" in out
        assert "/help" in out
        assert "/quit" in out


@pytest.mark.integration
class TestRunTui:
    def test_exit_on_ctrl_c(self, temp_config_dir, monkeypatch, capsys):
        def _raise_eof(*a, **k):
            raise EOFError()
        monkeypatch.setattr("builtins.input", _raise_eof)
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "Bye" in out

    def test_exit_on_quit_command(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "Bye" in out

    def test_slash_help_displays_commands(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["/help", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "Slash Commands" in out or "/add" in out

    def test_slash_show_displays_config(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["/show", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "large language model" in out

    def test_slash_add_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/add gnn", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert "gnn" in get("interests.keywords_include")

    def test_empty_input_skips(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["", "  ", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "Bye" in out

    def test_ai_conversation_flow(self, temp_config_dir, mock_env, monkeypatch, capsys):
        inputs = iter(["add DiT", "a", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)

        def _fake_stream(messages):
            yield "thinking...", "Sure!\n/ADD(DiT)", "", [], False
            yield "thinking...", "Sure!\n/ADD(DiT)", "Sure!", [{"action": "add_keywords", "keywords": ["DiT"]}], True

        monkeypatch.setattr("src.chat.terminal.parse_response_stream", _fake_stream)

        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert "DiT" in get("interests.keywords_include")

        out = capsys.readouterr().out
        assert "thinking..." in out or "Sure!" in out or "ADD" in out

    def test_ai_error_recovery(self, temp_config_dir, mock_env, monkeypatch, capsys):
        inputs = iter(["add DiT", "a", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)

        def _fake_error(messages):
            raise RuntimeError("API down")
            yield

        monkeypatch.setattr("src.chat.terminal.parse_response_stream", _fake_error)

        from src.chat.terminal import run_tui
        run_tui()

        out = capsys.readouterr().out
        assert "Error" in out or "Saved" in out

    def test_slash_score_invalid_handles_none(self, temp_config_dir, monkeypatch):
        inputs = iter(["/score abc", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()

    def test_slash_rm_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/rm agent", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert "agent" not in get("interests.keywords_include")

    def test_slash_exclude_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/exclude nlp", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert "nlp" in get("interests.keywords_exclude")

    def test_slash_unexclude_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/unexclude survey", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert "survey" not in get("interests.keywords_exclude")

    def test_slash_cats_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/cats cs.CV", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert get("interests.categories") == ["cs.CV"]

    def test_slash_score_valid_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/score 5", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert get("daily.min_relevance_score") == 5

    def test_slash_max_executes(self, temp_config_dir, monkeypatch):
        inputs = iter(["/max 20", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        from src.config import get
        run_tui()
        assert get("daily.max_papers") == 20

    def test_slash_show_after_add(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["/add diffusion", "", "/show", "", "quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "diffusion" in out

    def test_quit_alias_q(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["q"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "Bye" in out

    def test_quit_alias_exit(self, temp_config_dir, monkeypatch, capsys):
        inputs = iter(["exit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui()
        out = capsys.readouterr().out
        assert "Bye" in out

    def test_streaming_delta_print(self, temp_config_dir, mock_env, monkeypatch, capsys):
        def _fake_stream(messages):
            yield "think", "Hel", "", [], False
            yield "thinking...", "Hel", "", [], False
            yield "thinking...", "Hello world", "Hello world", [], True

        monkeypatch.setattr("src.chat.terminal.parse_response_stream", _fake_stream)

        from src.chat.terminal import _stream_ai_response
        from src.chat.engine import build_system_prompt

        messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": "hello"},
        ]

        _stream_ai_response(messages)

        out = capsys.readouterr().out
        assert "Hel" in out
        assert "world" in out

    def test_streaming_with_screen_shows_thinking(self, temp_config_dir, mock_env, monkeypatch, capsys):
        def _fake_stream(messages):
            yield "thinking...", "", "", [], False
            yield "thinking...", "Hi there", "Hi there", [], True

        monkeypatch.setattr("src.chat.terminal.parse_response_stream", _fake_stream)

        from src.chat.terminal import _stream_ai_response
        from src.chat.engine import build_system_prompt
        from src.chat.screen import Screen

        messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": "hello"},
        ]

        screen = Screen()
        _stream_ai_response(messages, screen)

        out = capsys.readouterr().out
        assert "Thinking" in out
        assert "Hi there" in out


@pytest.mark.unit
class TestReadlineHelpers:
    def test_init_readline_no_module(self, monkeypatch):
        import builtins
        orig = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "readline":
                raise ImportError()
            return orig(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        _init_readline()

    def test_init_readline_file_not_found(self, monkeypatch):
        if not os.path.exists(os.path.expanduser("~/.daily_papers_history")):
            _init_readline()

    def test_save_readline_no_module(self, monkeypatch):
        import builtins
        orig = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "readline":
                raise ImportError()
            return orig(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        _save_readline()

    def test_save_readline_success(self, monkeypatch):
        _save_readline()


@pytest.mark.unit
class TestStreamAiResponseNullScreen:
    def test_no_screen_with_actions(self, temp_config_dir, mock_env, monkeypatch, capsys):
        def _fake_stream(messages):
            yield "thinking...", "Sure!\n/ADD(DiT)", "Sure!", [{"action": "add_keywords", "keywords": ["DiT"]}], True

        monkeypatch.setattr("src.chat.terminal.parse_response_stream", _fake_stream)

        from src.chat.terminal import _stream_ai_response
        from src.chat.engine import build_system_prompt

        messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": "add DiT"},
        ]

        _stream_ai_response(messages)

        out = capsys.readouterr().out
        assert "Sure" in out
        assert "ADD" in out


@pytest.mark.unit
class TestReadlineFileNotFound:
    def test_init_readline_with_file_not_found(self, monkeypatch):
        import builtins
        orig = builtins.__import__

        def _raise_fnf(*args):
            raise FileNotFoundError()

        readline_mock = type("fake_readline", (), {
            "read_history_file": _raise_fnf,
        })()

        def fake_import(name, *a, **k):
            if name == "readline":
                return readline_mock
            return orig(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        from src.chat.terminal import _init_readline
        _init_readline()


@pytest.mark.integration
class TestRunTuiInitialMessages:
    def test_with_initial_messages(self, temp_config_dir, monkeypatch):
        inputs = iter(["quit"])
        monkeypatch.setattr("builtins.input", lambda prompt=None: next(inputs))
        monkeypatch.setattr("src.chat.terminal._init_readline", lambda: None)
        monkeypatch.setattr("src.chat.terminal._save_readline", lambda: None)
        from src.chat.terminal import run_tui
        run_tui(initial_messages=[{"role": "user", "content": "hello"}])
