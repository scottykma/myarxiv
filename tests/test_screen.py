import pytest

from src.chat.screen import Screen, _action_icon, _bold, _dim, _green, _cyan, _yellow


@pytest.mark.unit
class TestScreenRenderHeader:
    def test_first_call_prints_header(self, temp_config_dir, capsys):
        screen = Screen()
        screen.render_header()
        out = capsys.readouterr().out
        assert "MyArxiv" in out
        assert "Keywords" in out
        assert "Exclude" in out
        assert "Categories" in out
        assert "Max/Day" in out
        assert "Min Score" in out

    def test_second_call_is_noop(self, temp_config_dir, capsys):
        screen = Screen()
        screen.render_header()
        capsys.readouterr()
        screen.render_header()
        out = capsys.readouterr().out
        assert out == ""

    def test_header_includes_configured_keywords(self, temp_config_dir, capsys):
        from src.config import set, reload
        reload()
        set("interests.keywords_include", ["DiT", "attention"])
        screen = Screen()
        screen.render_header()
        out = capsys.readouterr().out
        assert "DiT" in out
        assert "attention" in out


@pytest.mark.unit
class TestScreenRenderMessageHistory:
    def test_prints_user_messages(self, capsys):
        screen = Screen()
        screen.render_message_history([
            {"role": "user", "content": "hello"},
        ])
        out = capsys.readouterr().out
        assert "hello" in out

    def test_prints_assistant_messages(self, capsys):
        screen = Screen()
        screen.render_message_history([
            {"role": "assistant", "content": "Hi there!"},
        ])
        out = capsys.readouterr().out
        assert "Hi there!" in out

    def test_skips_system_messages(self, capsys):
        screen = Screen()
        screen.render_message_history([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "hello"},
        ])
        out = capsys.readouterr().out
        assert "helpful assistant" not in out
        assert "hello" in out

    def test_preserves_message_order(self, capsys):
        screen = Screen()
        screen.render_message_history([
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "second"},
            {"role": "user", "content": "third"},
        ])
        out = capsys.readouterr().out
        pos_first = out.index("first")
        pos_second = out.index("second")
        pos_third = out.index("third")
        assert pos_first < pos_second < pos_third

    def test_empty_messages(self, capsys):
        screen = Screen()
        screen.render_message_history([])
        out = capsys.readouterr().out
        assert out == ""


@pytest.mark.unit
class TestScreenThinking:
    def test_show_thinking_prints_indicator(self, capsys):
        screen = Screen()
        screen.show_thinking()
        out = capsys.readouterr().out
        assert "Thinking" in out
        assert screen._thinking is True

    def test_hide_thinking_clears_line(self, capsys):
        screen = Screen()
        screen._thinking = True
        screen.hide_thinking()
        out = capsys.readouterr().out
        assert "\r\033[K" in out
        assert screen._thinking is False

    def test_hide_thinking_noop_when_not_thinking(self, capsys):
        screen = Screen()
        screen._thinking = False
        screen.hide_thinking()
        out = capsys.readouterr().out
        assert out == ""


@pytest.mark.unit
class TestScreenWrite:
    def test_write_prints_text(self, capsys):
        screen = Screen()
        screen.write("hello")
        out = capsys.readouterr().out
        assert "hello" in out

    def test_write_auto_hides_thinking(self, capsys):
        screen = Screen()
        screen._thinking = True
        screen.write("hello")
        out = capsys.readouterr().out
        assert "\r\033[K" in out
        assert "hello" in out
        assert screen._thinking is False

    def test_write_flushes(self, capsys):
        screen = Screen()
        screen.write("streaming")
        out = capsys.readouterr().out
        assert "streaming" in out

    def test_write_partial_tokens(self, capsys):
        screen = Screen()
        screen.write("Hel")
        screen.write("lo")
        out = capsys.readouterr().out
        assert "Hello" in out


@pytest.mark.unit
class TestScreenWriteln:
    def test_writeln_prints_text_with_newline(self, capsys):
        screen = Screen()
        screen.writeln("hello")
        out = capsys.readouterr().out
        assert "hello\n" in out

    def test_writeln_empty(self, capsys):
        screen = Screen()
        screen.writeln()
        out = capsys.readouterr().out
        assert "\n" in out

    def test_writeln_auto_hides_thinking(self, capsys):
        screen = Screen()
        screen._thinking = True
        screen.writeln("hello")
        out = capsys.readouterr().out
        assert "\r\033[K" in out
        assert screen._thinking is False


@pytest.mark.unit
class TestScreenShowActions:
    def test_prints_action_results(self, capsys):
        screen = Screen()
        screen.show_actions(
            {"action": "add_keywords"},
            [("green", "Added: DiT")],
        )
        out = capsys.readouterr().out
        assert "DiT" in out

    def test_prints_multiple_results(self, capsys):
        screen = Screen()
        screen.show_actions(
            {"action": "remove_keywords"},
            [("green", "Removed: foo"), ("green", "Removed: bar")],
        )
        out = capsys.readouterr().out
        assert "foo" in out
        assert "bar" in out

    def test_uses_action_icon(self, capsys):
        screen = Screen()
        screen.show_actions(
            {"action": "add_keywords"},
            [("green", "Added: DiT")],
        )
        out = capsys.readouterr().out
        assert "\u2705" in out

    def test_empty_action_uses_default_icon(self, capsys):
        screen = Screen()
        screen.show_actions(
            {"action": "unknown_action"},
            [("green", "Done")],
        )
        out = capsys.readouterr().out
        assert "\u2022" in out


@pytest.mark.unit
class TestScreenShowContinuePrompt:
    def test_prints_prompt(self, capsys):
        screen = Screen()
        screen.show_continue_prompt()
        out = capsys.readouterr().out
        assert "Press Enter" in out

    def test_prompt_is_dimmed(self, capsys):
        screen = Screen()
        screen.show_continue_prompt()
        out = capsys.readouterr().out
        assert "\033[2m" in out


@pytest.mark.unit
class TestScreenShowConfigStatus:
    def test_prints_status(self, temp_config_dir, capsys):
        screen = Screen()
        screen.show_config_status()
        out = capsys.readouterr().out
        assert "Keywords" in out
        assert "Exclude" in out
        assert "Cats" in out
        assert "Max" in out
        assert "Min" in out

    def test_includes_current_values(self, temp_config_dir, capsys):
        from src.config import set, reload
        reload()
        set("interests.keywords_include", ["DiT", "attention"])
        set("interests.keywords_exclude", ["nlp"])
        set("interests.categories", ["cs.CV"])
        set("daily.max_papers", 15)
        set("daily.min_relevance_score", 5)
        screen = Screen()
        screen.show_config_status()
        out = capsys.readouterr().out
        assert "DiT" not in out
        assert "nlp" not in out
        assert "cs.CV" in out
        assert "Max" in out
        assert "Min" in out

    def test_empty_keywords_shows_none(self, temp_config_dir, capsys):
        from src.config import set, reload
        reload()
        set("interests.categories", [])
        screen = Screen()
        screen.show_config_status()
        out = capsys.readouterr().out
        assert "none" in out


@pytest.mark.unit
class TestScreenActionIcon:
    def test_known_actions(self):
        assert _action_icon("add_keywords") == "\u2705"
        assert _action_icon("remove_keywords") == "\U0001f5d1\ufe0f"
        assert _action_icon("add_exclude") == "\U0001f6ab"
        assert _action_icon("remove_exclude") == "\u267b\ufe0f"
        assert _action_icon("set_categories") == "\U0001f4c2"
        assert _action_icon("set_max_papers") == "\U0001f4ca"
        assert _action_icon("set_min_score") == "\U0001f3af"
        assert _action_icon("suggest") == "\U0001f4a1"
        assert _action_icon("none") == "\u2139\ufe0f"

    def test_unknown_action(self):
        assert _action_icon("bogus") == "\u2022"


@pytest.mark.unit
class TestScreenAnsiHelpers:
    def test_bold(self):
        assert _bold("x").startswith("\033[1m")
        assert _bold("x").endswith("\033[0m")

    def test_dim(self):
        assert _dim("x").startswith("\033[2m")
        assert _dim("x").endswith("\033[0m")

    def test_green(self):
        assert _green("x").startswith("\033[32m")
        assert _green("x").endswith("\033[0m")

    def test_cyan(self):
        assert _cyan("x").startswith("\033[36m")
        assert _cyan("x").endswith("\033[0m")

    def test_yellow(self):
        assert _yellow("x").startswith("\033[33m")
        assert _yellow("x").endswith("\033[0m")


@pytest.mark.unit
class TestScreenStateTransitions:
    def test_thinking_to_writing(self, capsys):
        screen = Screen()
        screen.show_thinking()
        capsys.readouterr()
        screen.write("hello")
        out = capsys.readouterr().out
        assert "hello" in out

    def test_thinking_not_cleared_by_writeln(self, capsys):
        screen = Screen()
        screen.show_thinking()
        capsys.readouterr()
        screen.writeln("done")
        out = capsys.readouterr().out
        assert "done" in out
        assert screen._thinking is False


@pytest.mark.unit
class TestScreenMessageHistoryEdgeCases:
    def test_message_without_role(self, capsys):
        screen = Screen()
        screen.render_message_history([
            {"content": "orphan"},
        ])
        out = capsys.readouterr().out
        assert out == ""

    def test_mixed_roles(self, capsys):
        screen = Screen()
        screen.render_message_history([
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "system", "content": "ignore2"},
            {"role": "user", "content": "u2"},
        ])
        out = capsys.readouterr().out
        assert "ignore" not in out
        assert "u1" in out
        assert "a1" in out
        assert "u2" in out
