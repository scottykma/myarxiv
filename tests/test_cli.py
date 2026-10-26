import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src import config
from src.cli import build_parser, main
from src.pipeline.fetcher import ArxivPaper


def _make_preview_result():
    result = MagicMock()
    result.get_short_id.return_value = "2505.1"
    result.title = "Video generation with memory"
    result.summary = "abstract"
    result.authors = []
    result.published = datetime.now(timezone.utc)
    result.entry_id = "url"
    result.pdf_url = "pdf"
    result.categories = ["cs.CV"]
    result.comment = ""
    paper = ArxivPaper(result)
    return {
        "fetched": 1,
        "candidates": [{"paper": paper, "score": 5, "keywords": ["video generation"]}],
        "excluded": [],
        "stats": {"video generation": 1},
        "include_keywords": ["video generation"],
        "exclude_keywords": [],
    }


@pytest.mark.unit
class TestBuildParser:
    def test_parses_add(self):
        args = build_parser().parse_args(["add", "DiT", "--exclude"])
        assert args.command == "add"
        assert args.items == ["DiT"]
        assert args.exclude is True

    def test_parses_set(self):
        args = build_parser().parse_args(["set", "score", "6"])
        assert args.key == "score"
        assert args.value == ["6"]

    def test_parses_preview(self):
        args = build_parser().parse_args(["preview", "--days", "2", "--json"])
        assert args.days == 2
        assert args.json is True


@pytest.mark.unit
class TestListCommand:
    def test_prints_interests(self, temp_config_dir, capsys):
        assert main(["list"]) == 0
        out = capsys.readouterr().out
        assert "Include" in out
        assert "agent" in out
        assert "Categories" in out

    def test_json_output(self, temp_config_dir, capsys):
        assert main(["list", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert "agent" in data["include"]
        assert data["categories"] == ["cs.AI", "cs.CL"]
        assert "keyword_weights" in data

    def test_shows_weights(self, temp_config_dir, capsys):
        config.reload()
        config.set("interests.keyword_weights", {"agent": 3})
        assert main(["list"]) == 0
        assert "weight 3" in capsys.readouterr().out


@pytest.mark.unit
class TestAddCommand:
    def test_adds_keyword(self, temp_config_dir, capsys):
        assert main(["add", "gnn"]) == 0
        assert "gnn" in config.get("interests.keywords_include")
        assert "Added" in capsys.readouterr().out

    def test_adds_case_insensitive_duplicate(self, temp_config_dir, capsys):
        config.reload()
        config.set("interests.keywords_include", ["DiT"])
        assert main(["add", "dit"]) == 0
        assert config.get("interests.keywords_include") == ["DiT"]
        assert "Already present" in capsys.readouterr().out

    def test_adds_to_exclude(self, temp_config_dir):
        assert main(["add", "--exclude", "nlp, robotics"]) == 0
        assert config.get("interests.keywords_exclude") == ["survey", "nlp", "robotics"]

    def test_empty_input_returns_error(self, temp_config_dir, capsys):
        assert main(["add", ",,"]) == 1
        assert "No keywords" in capsys.readouterr().out


@pytest.mark.unit
class TestRmCommand:
    def test_removes_by_text(self, temp_config_dir):
        assert main(["rm", "agent"]) == 0
        assert "agent" not in config.get("interests.keywords_include")

    def test_removes_by_index(self, temp_config_dir):
        config.reload()
        first = config.get("interests.keywords_include")[0]
        assert main(["rm", "1"]) == 0
        assert first not in config.get("interests.keywords_include")

    def test_removes_from_exclude(self, temp_config_dir):
        assert main(["rm", "--exclude", "survey"]) == 0
        assert config.get("interests.keywords_exclude") == []

    def test_invalid_index_returns_error(self, temp_config_dir, capsys):
        assert main(["rm", "99"]) == 1
        assert "out of range" in capsys.readouterr().err

    def test_missing_keyword_is_reported(self, temp_config_dir, capsys):
        assert main(["rm", "nonexistent"]) == 0
        assert "Not found" in capsys.readouterr().out


@pytest.mark.unit
class TestSetCommand:
    def test_sets_score(self, temp_config_dir):
        assert main(["set", "score", "6"]) == 0
        assert config.get("daily.min_relevance_score") == 6

    def test_sets_max(self, temp_config_dir):
        assert main(["set", "max", "10"]) == 0
        assert config.get("daily.max_papers") == 10

    def test_sets_categories(self, temp_config_dir):
        assert main(["set", "cats", "cs.CV,", "cs.AI"]) == 0
        assert config.get("interests.categories") == ["cs.CV", "cs.AI"]

    def test_sets_weight(self, temp_config_dir):
        assert main(["set", "weight", "agent", "3"]) == 0
        assert config.get("interests.keyword_weights")["agent"] == 3

    def test_weight_requires_existing_keyword(self, temp_config_dir, capsys):
        assert main(["set", "weight", "missing", "3"]) == 1
        assert "not in include list" in capsys.readouterr().err

    def test_rejects_invalid_weight(self, temp_config_dir, capsys):
        assert main(["set", "weight", "agent", "9"]) == 1
        assert "Invalid weight" in capsys.readouterr().err

    def test_rejects_invalid_score(self, temp_config_dir, capsys):
        assert main(["set", "score", "99"]) == 1
        assert "Invalid score" in capsys.readouterr().err

    def test_rejects_invalid_category(self, temp_config_dir, capsys):
        assert main(["set", "cats", "foo"]) == 1
        assert "Unknown categories" in capsys.readouterr().err

    def test_rejects_empty_categories(self, temp_config_dir, capsys):
        assert main(["set", "cats", ","]) == 1
        assert "No categories" in capsys.readouterr().err


@pytest.mark.unit
class TestPreviewCommand:
    def test_plain_output(self, temp_config_dir, capsys):
        with patch("src.cli.preview_papers", return_value=_make_preview_result()):
            assert main(["preview"]) == 0
        out = capsys.readouterr().out
        assert "Video generation with memory" in out

    def test_json_output(self, temp_config_dir, capsys):
        with patch("src.cli.preview_papers", return_value=_make_preview_result()):
            assert main(["preview", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["candidates"][0]["paper"]["arxiv_id"] == "2505.1"

    def test_llm_flag(self, temp_config_dir):
        with patch("src.cli.preview_papers", return_value=_make_preview_result()) as mock_preview:
            assert main(["preview", "--llm"]) == 0
        assert mock_preview.call_args.kwargs["use_llm"] is True


@pytest.mark.unit
class TestStatsCommand:
    def test_plain_output(self, temp_config_dir, capsys):
        with patch("src.cli.preview_papers", return_value=_make_preview_result()):
            assert main(["stats"]) == 0
        out = capsys.readouterr().out
        assert "video generation" in out

    def test_json_output(self, temp_config_dir, capsys):
        with patch("src.cli.preview_papers", return_value=_make_preview_result()):
            assert main(["stats", "--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data == {"video generation": 1}

    def test_empty_stats(self, temp_config_dir, capsys):
        result = _make_preview_result()
        result["stats"] = {}
        with patch("src.cli.preview_papers", return_value=result):
            assert main(["stats"]) == 0
        assert "no keywords" in capsys.readouterr().out


@pytest.mark.unit
class TestDiffUndo:
    def test_diff_and_undo(self, temp_config_dir, capsys):
        config.reload()
        assert main(["set", "score", "6"]) == 0
        assert main(["set", "score", "7"]) == 0
        capsys.readouterr()

        assert main(["diff"]) == 0
        diff_out = capsys.readouterr().out
        assert "score" in diff_out or "6" in diff_out

        assert main(["undo"]) == 0
        assert config.get("daily.min_relevance_score") == 6

    def test_undo_without_backup(self, temp_config_dir, capsys):
        assert main(["undo"]) == 1
        assert "No previous config" in capsys.readouterr().out

    def test_diff_without_backup(self, temp_config_dir, capsys):
        assert main(["diff"]) == 0
        assert "No previous config" in capsys.readouterr().out

    def test_handler_error_is_reported(self, temp_config_dir, capsys):
        with patch("src.cli.preview_papers", side_effect=ValueError("boom")):
            assert main(["preview"]) == 1
        assert "Error: boom" in capsys.readouterr().err


@pytest.mark.unit
class TestMain:
    def test_no_command_runs_tui(self, temp_config_dir, monkeypatch):
        with patch("src.chat.terminal.run_tui") as mock_tui:
            assert main([]) == 0
        mock_tui.assert_called_once()
