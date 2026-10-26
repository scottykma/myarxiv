import io
from types import SimpleNamespace

import pytest
from rich.console import Console

from src.chat import ui


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, width=120, color_system=None)
    return console, buffer


@pytest.mark.unit
class TestStatus:
    def test_status_text(self, temp_config_dir):
        text = ui.status_text()
        assert "keywords 2" in text
        assert "exclude 1" in text
        assert "cs.AI" in text


@pytest.mark.unit
class TestRenderHeader:
    def test_header(self, temp_config_dir):
        console, buffer = _console()
        ui.render_header(console)
        output = buffer.getvalue()
        assert "MyArxiv" in output
        assert "Keywords" in output
        assert "Weights" in output
        assert "Categories" in output


@pytest.mark.unit
class TestRenderHistory:
    def test_history(self):
        console, buffer = _console()
        ui.render_history(console, [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "**hi**"},
            {"role": "system", "content": "ignored"},
        ])
        output = buffer.getvalue()
        assert "hello" in output
        assert "hi" in output
        assert "ignored" not in output


@pytest.mark.unit
class TestKeywordTables:
    def test_include_and_exclude(self, temp_config_dir):
        console, buffer = _console()
        console.print(ui.keyword_tables())
        output = buffer.getvalue()
        assert "Include" in output
        assert "Exclude" in output
        assert "large language model" in output

    def test_with_stats_and_weights(self, temp_config_dir):
        from src.config import set

        set("interests.keyword_weights", {"agent": 3})
        console, buffer = _console()
        console.print(ui.keyword_tables({"agent": 5}))
        output = buffer.getvalue()
        assert "Hits" in output
        assert "5" in output


@pytest.mark.unit
class TestPreviewTables:
    def _result(self):
        paper = SimpleNamespace(title="Video generation with memory")
        return {
            "fetched": 2,
            "candidates": [{"paper": paper, "score": 9, "keywords": ["video generation"]}],
            "excluded": [{"paper": SimpleNamespace(title="Time series"), "keyword": "time series"}],
            "stats": {"video generation": 1},
            "keyword_weights": {"video generation": 3},
            "llm_results": [(paper, 8, "relevant")],
        }

    def test_preview_table(self):
        console, buffer = _console()
        console.print(ui.preview_table(self._result()))
        output = buffer.getvalue()
        assert "Video generation" in output
        assert "video generation×3" in output

    def test_excluded_table(self):
        console, buffer = _console()
        console.print(ui.excluded_table(self._result()))
        assert "Time series" in buffer.getvalue()

    def test_stats_table(self):
        console, buffer = _console()
        console.print(ui.stats_table({"agent": 4}, {"agent": 2}))
        output = buffer.getvalue()
        assert "agent" in output
        assert "4" in output

    def test_llm_table(self):
        console, buffer = _console()
        console.print(ui.llm_table(self._result()))
        output = buffer.getvalue()
        assert "LLM selection" in output
        assert "relevant" in output


@pytest.mark.unit
class TestMisc:
    def test_help_table(self):
        console, buffer = _console()
        console.print(ui.help_table())
        output = buffer.getvalue()
        assert "/preview" in output
        assert "/weight" in output

    def test_markdown(self):
        console, buffer = _console()
        ui.print_markdown(console, "**hello**")
        assert "hello" in buffer.getvalue()

    def test_empty_markdown(self):
        console, buffer = _console()
        ui.print_markdown(console, "")
        assert buffer.getvalue() == ""

    def test_panels_and_syntax(self):
        console, buffer = _console()
        console.print(ui.proposal_panel("+ keyword"))
        console.print(ui.error_panel("bad"))
        console.print(ui.diff_syntax("+ added"))
        output = buffer.getvalue()
        assert "Proposed changes" in output
        assert "bad" in output
        assert "added" in output
