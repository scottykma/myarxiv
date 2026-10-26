import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.main import _main, _score_color, _write_run_stats, build_report, load_seen_ids, save_seen_ids, run


@pytest.mark.unit
class TestBuildReport:
    def test_empty_summarized(self, temp_config_dir):
        report = build_report([])
        assert "Daily arXiv Digest" in report
        assert "0 papers" in report

    def test_report_structure(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        report = build_report([(paper, 9, "Highly relevant")])
        assert paper.title in report
        assert "9/10" in report
        assert paper.arxiv_id in report
        assert "<html>" in report
        assert "class=\"card\"" in report
        assert _score_color(9) in report
        assert paper.abstract in report

    def test_report_with_comment(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        report = build_report([(paper, 9, "R")])
        assert "ACL 2025" in report

    def test_score_color(self):
        assert _score_color(9) == "#3F6B4A"
        assert _score_color(6) == "#B7791F"
        assert _score_color(3) == "#9B2C2C"

    def test_dark_score_color(self):
        assert _score_color(9, "dark") == "#7FB08A"
        assert _score_color(6, "dark") == "#E0A458"
        assert _score_color(3, "dark") == "#E07A7A"

    def test_escapes_untrusted_html(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        paper.title = "<script>alert(1)</script>"
        paper.abstract = "<img src=x onerror=alert(1)>"
        paper.comment = "<b>note</b>"
        report = build_report([(paper, 9, "<b>reason</b>")])
        assert "<script>" not in report
        assert "&lt;script&gt;" in report
        assert "<img" not in report
        assert "&lt;b&gt;reason&lt;/b&gt;" in report


@pytest.mark.unit
class TestSeenIds:
    def test_load_nonexistent(self, tmp_path, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", tmp_path / "nonexistent.json")
        assert load_seen_ids() == set()

    def test_load_valid(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            json.dump({"ids": ["2505.1"], "updated": "2025-05-28"}, f)
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == {"2505.1"}

    def test_load_corrupted(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            f.write("not json")
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == set()

    def test_load_canonicalizes_versions(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            json.dump({"ids": ["2505.1v1", "2505.2"]}, f)
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == {"2505.1", "2505.2"}

    def test_load_non_mapping(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            json.dump(["2505.1"], f)
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == set()

    def test_load_non_list_ids(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        with open(seen_path, "w") as f:
            json.dump({"ids": "2505.1"}, f)
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        assert load_seen_ids() == set()

    def test_save_seen_ids(self, tmp_path, monkeypatch, sample_arxiv_result):
        import src.main
        seen_path = tmp_path / "seen.json"
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        paper = ArxivPaper(sample_arxiv_result)
        save_seen_ids([paper], {"2505.99999"})
        with open(seen_path) as f:
            data = json.load(f)
        assert "2505.12345" in data["ids"]
        assert "2505.99999" in data["ids"]

    def test_save_canonicalizes_versions(self, tmp_path, monkeypatch, sample_arxiv_result):
        import src.main
        seen_path = tmp_path / "seen.json"
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        sample_arxiv_result.get_short_id.return_value = "2505.12345v4"
        paper = ArxivPaper(sample_arxiv_result)
        save_seen_ids([paper], {"2505.99999v2"})
        with open(seen_path) as f:
            data = json.load(f)
        assert data["ids"] == ["2505.12345", "2505.99999"]

    def test_save_cleans_temp_when_replace_fails(self, tmp_path, monkeypatch):
        import src.main
        seen_path = tmp_path / "seen.json"
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)
        def _fail_replace(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(src.main.os, "replace", _fail_replace)
        with pytest.raises(OSError):
            save_seen_ids([], set())
        assert not seen_path.with_name(seen_path.name + ".tmp").exists()

    def test_uses_configured_seen_path(self, temp_config_dir, tmp_path, sample_arxiv_result):
        import src.config
        custom = tmp_path / "custom_seen.json"
        src.config.set("paths.seen_papers", str(custom))
        save_seen_ids([ArxivPaper(sample_arxiv_result)], set())
        assert custom.exists()
        assert "2505.12345" in load_seen_ids()


def _mock_paper(title="Test Paper"):
    paper = MagicMock()
    paper.arxiv_id = "test1"
    paper.title = title
    paper.authors = []
    paper.abstract = "Abstract"
    paper.published = datetime.now(timezone.utc)
    paper.url = "http://arxiv.org/abs/test1"
    paper.pdf_url = "http://arxiv.org/pdf/test1"
    paper.categories = ["cs.AI"]
    paper.comment = ""
    return paper


@pytest.mark.integration
class TestRun:
    def test_run_no_papers(self, temp_config_dir, mock_env):
        with patch("src.main.fetch_daily_papers", return_value=[]):
            run()

    def test_run_all_seen(self, temp_config_dir, mock_env, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", src.main.ROOT / "tests" / "fixture_seen.json")

        mock_paper = MagicMock()
        mock_paper.arxiv_id = "test1"
        mock_paper.title = "Test Paper About AI"
        mock_paper.abstract = "Abstract"
        mock_paper.categories = ["cs.AI"]

        with patch("src.main.fetch_daily_papers", return_value=[mock_paper]):
            with patch("src.main.load_seen_ids", return_value={"test1"}):
                run()

    def test_run_final_score_empty(self, temp_config_dir, mock_env, monkeypatch):
        import src.main
        monkeypatch.setattr(src.main, "SEEN_PATH", src.main.ROOT / "tests" / "fixture_seen.json")

        mock_paper = MagicMock()
        mock_paper.arxiv_id = "test1"
        mock_paper.title = "Test Paper About AI"
        mock_paper.abstract = "Abstract"
        mock_paper.categories = ["cs.AI"]

        with patch("src.main.fetch_daily_papers", return_value=[mock_paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[]):
                    with patch("src.main.save_seen_ids"):
                        run()

    def test_run_full_pipeline(self, temp_config_dir, mock_env, monkeypatch, tmp_path):
        import src.main
        seen_path = tmp_path / "seen.json"
        monkeypatch.setattr(src.main, "SEEN_PATH", seen_path)

        mock_paper = MagicMock()
        mock_paper.arxiv_id = "test1"
        mock_paper.title = "Test Paper"
        mock_paper.authors = []
        mock_paper.abstract = "Abstract"
        mock_paper.published = datetime.now(timezone.utc)
        mock_paper.url = "http://arxiv.org/abs/test1"
        mock_paper.pdf_url = "http://arxiv.org/pdf/test1"
        mock_paper.categories = ["cs.AI"]
        mock_paper.comment = ""

        with patch("src.main.fetch_daily_papers", return_value=[mock_paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[(mock_paper, 9, "ok")]):
                    with patch("src.main.send_report", return_value={"email": True}):
                        stats = run()
        seen = json.loads(seen_path.read_text())["ids"]
        assert seen == ["test1"]
        assert stats["email_sent"] is True

    def test_run_email_failure_does_not_mark_seen(self, temp_config_dir, mock_env):
        paper = _mock_paper()
        with patch("src.main.fetch_daily_papers", return_value=[paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[(paper, 9, "ok")]):
                    with patch("src.main.send_report", return_value={"email": False}):
                        with patch("src.main.save_seen_ids") as mock_save:
                            stats = run()
        assert stats["email_sent"] is False
        mock_save.assert_not_called()

    def test_run_dry_run_writes_report_without_sending(self, temp_config_dir, mock_env, tmp_path):
        import src.config
        report_path = tmp_path / "report.html"
        src.config.set("paths.report", str(report_path))
        src.config.save()

        paper = _mock_paper()
        with patch("src.main.fetch_daily_papers", return_value=[paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[(paper, 9, "ok")]):
                    with patch("src.main.send_report") as mock_send:
                        with patch("src.main.save_seen_ids") as mock_save:
                            stats = run(dry_run=True)
        assert report_path.exists()
        assert report_path.with_suffix(".txt").exists()
        assert stats["dry_run"] is True
        mock_send.assert_not_called()
        mock_save.assert_not_called()

    def test_run_writes_stats(self, temp_config_dir, mock_env, tmp_path):
        import src.config
        stats_path = tmp_path / "last_run.json"
        src.config.set("paths.last_run", str(stats_path))
        src.config.save()

        paper = _mock_paper()
        with patch("src.main.fetch_daily_papers", return_value=[paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.chat_final_score", return_value=[(paper, 9, "ok")]):
                    with patch("src.main.send_report", return_value={"email": True}):
                        with patch("src.main.save_seen_ids"):
                            run()
        data = json.loads(stats_path.read_text())
        assert data["fetched"] == 1
        assert data["selected"] == 1
        assert data["email_sent"] is True

    def test_run_prefilter_empty_does_not_save(self, temp_config_dir, mock_env):
        paper = _mock_paper()
        with patch("src.main.fetch_daily_papers", return_value=[paper]):
            with patch("src.main.load_seen_ids", return_value=set()):
                with patch("src.main.keyword_prefilter", return_value=[]):
                    with patch("src.main.save_seen_ids") as mock_save:
                        stats = run()
        assert stats["prefiltered"] == 0
        mock_save.assert_not_called()


@pytest.mark.unit
class TestRunStats:
    def test_stats_write_error_is_logged(self, temp_config_dir, tmp_path, monkeypatch):
        import src.config
        target = tmp_path / "last_run.json"
        src.config.set("paths.last_run", str(target))
        def _fail_replace(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("src.main.os.replace", _fail_replace)
        _write_run_stats({"fetched": 1})
        assert not target.with_name(target.name + ".tmp").exists()

    def test_main_parses_dry_run(self, monkeypatch):
        import sys
        import src.main
        monkeypatch.setattr(sys, "argv", ["main", "--dry-run", "--lookback-days", "2"])
        with patch("src.main.run", return_value={"selected": 1, "email_sent": False}) as mock_run:
            _main()
        mock_run.assert_called_once_with(dry_run=True, lookback_days=2)

    def test_main_fails_when_delivery_fails(self, monkeypatch):
        import sys
        import src.main
        monkeypatch.setattr(sys, "argv", ["main"])
        with patch("src.main.run", return_value={"selected": 1, "email_sent": False}):
            with pytest.raises(SystemExit) as excinfo:
                _main()
        assert excinfo.value.code == 1
