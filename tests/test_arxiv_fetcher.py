import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import (
    ARXIV_CATEGORIES,
    ArxivPaper,
    _cache_path,
    _date_range_query,
    _load_cache,
    _make_client,
    _save_cache,
    canonical_id,
    fetch_daily_papers,
)


@pytest.mark.unit
class TestArxivPaper:
    def test_init_from_result(self, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        assert paper.arxiv_id == "2505.12345"
        assert paper.title == "A Novel Approach to Large Language Models"
        assert len(paper.authors) == 2
        assert "new method" in paper.abstract
        assert paper.categories == ["cs.CL", "cs.AI"]
        assert paper.comment == "Accepted at ACL 2025"

    def test_to_dict(self, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        d = paper.to_dict()
        assert d["arxiv_id"] == "2505.12345"
        assert d["title"] == "A Novel Approach to Large Language Models"
        assert "published" in d
        assert "url" in d

    def test_repr(self, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        r = repr(paper)
        assert "2505.12345" in r
        assert "Novel Approach" in r

    def test_versioned_id_is_canonicalized(self, sample_arxiv_result):
        sample_arxiv_result.get_short_id.return_value = "2505.12345v2"
        paper = ArxivPaper(sample_arxiv_result)
        assert paper.arxiv_id == "2505.12345"

    def test_empty_comment(self):
        result = MagicMock()
        result.get_short_id.return_value = "2505.1"
        result.title = "Test"
        result.authors = []
        result.summary = "Abstract"
        result.published = datetime.now(timezone.utc)
        result.entry_id = "http://example.com"
        result.pdf_url = "http://example.com/pdf"
        result.categories = ["cs.AI"]
        result.comment = None
        paper = ArxivPaper(result)
        assert paper.comment == ""


@pytest.mark.unit
class TestDateRangeQuery:
    def test_builds_query(self):
        q = _date_range_query(["cs.AI", "cs.CL"], 1)
        assert "cat:cs.AI" in q
        assert "cat:cs.CL" in q
        assert "submittedDate:[" in q
        assert " TO " in q


@pytest.mark.unit
class TestFetchPapers:
    def test_with_default_categories(self, temp_config_dir):
        mock_client = MagicMock()
        mock_paper = MagicMock()
        mock_paper.published = datetime.now(timezone.utc)
        mock_paper.get_short_id.return_value = "2505.1"
        mock_paper.title = "Test Paper"
        mock_paper.authors = []
        mock_paper.summary = "Abstract"
        mock_paper.entry_id = "url"
        mock_paper.pdf_url = "pdf"
        mock_paper.categories = ["cs.AI"]
        mock_paper.comment = ""
        mock_client.results.return_value = [mock_paper]

        with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
            papers = fetch_daily_papers()
            assert len(papers) == 1
            assert papers[0].arxiv_id == "2505.1"

    def test_invalid_category_bypasses_cache(self, temp_config_dir, capsys):
        papers = fetch_daily_papers(categories=["nonexistent.category"], use_cache=False)
        assert len(papers) == 0

    def test_unique_deduplication(self, temp_config_dir):
        mock_client = MagicMock()
        mock_paper = MagicMock()
        mock_paper.published = datetime.now(timezone.utc)
        mock_paper.get_short_id.return_value = "2505.1"
        mock_paper.title = "Test Paper"
        mock_paper.authors = []
        mock_paper.summary = "Abstract"
        mock_paper.entry_id = "url"
        mock_paper.pdf_url = "pdf"
        mock_paper.categories = ["cs.AI"]
        mock_paper.comment = ""
        mock_client.results.return_value = [mock_paper, mock_paper]

        with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
            papers = fetch_daily_papers()
            assert len(papers) == 1

    def test_exception_handling_raises_without_papers(self, temp_config_dir):
        mock_client = MagicMock()
        mock_client.results.side_effect = Exception("API error")

        with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
            with patch("src.pipeline.fetcher._save_cache") as mock_save:
                with pytest.raises(RuntimeError, match="arXiv fetch failed"):
                    fetch_daily_papers(categories=["cs.AI"], use_cache=False)
                mock_save.assert_not_called()

    def test_empty_result_does_not_cache(self, temp_config_dir):
        mock_client = MagicMock()
        mock_client.results.return_value = []

        with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
            with patch("src.pipeline.fetcher._save_cache") as mock_save:
                papers = fetch_daily_papers(categories=["cs.AI"], use_cache=False)
                assert papers == []
                mock_save.assert_not_called()

    def test_versioned_duplicates_are_collapsed(self, temp_config_dir):
        first = MagicMock()
        first.published = datetime.now(timezone.utc)
        first.get_short_id.return_value = "2505.1v1"
        first.title = "Test"
        first.authors = []
        first.summary = "Abstract"
        first.entry_id = "url"
        first.pdf_url = "pdf"
        first.categories = ["cs.AI"]
        first.comment = ""
        second = MagicMock()
        second.published = datetime.now(timezone.utc)
        second.get_short_id.return_value = "2505.1v2"
        second.title = "Test"
        second.authors = []
        second.summary = "Abstract"
        second.entry_id = "url"
        second.pdf_url = "pdf"
        second.categories = ["cs.AI"]
        second.comment = ""

        mock_client = MagicMock()
        mock_client.results.return_value = [first, second]

        with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
            with patch("src.pipeline.fetcher._save_cache"):
                papers = fetch_daily_papers(categories=["cs.AI"], use_cache=False)
        assert len(papers) == 1
        assert papers[0].arxiv_id == "2505.1"

    def test_use_cache_false(self, temp_config_dir):
        mock_client = MagicMock()
        mock_paper = MagicMock()
        mock_paper.published = datetime.now(timezone.utc)
        mock_paper.get_short_id.return_value = "2505.1"
        mock_paper.title = "Test"
        mock_paper.authors = []
        mock_paper.summary = "Abstract"
        mock_paper.entry_id = "url"
        mock_paper.pdf_url = "pdf"
        mock_paper.categories = ["cs.AI"]
        mock_paper.comment = ""
        mock_client.results.return_value = [mock_paper]

        with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
            with patch("src.pipeline.fetcher._save_cache"):
                papers = fetch_daily_papers(categories=["cs.AI"], use_cache=False)
                assert len(papers) == 1

    def test_monday_lookback_expanded_to_3_days(self, temp_config_dir):
        monday = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)
        mock_client = MagicMock()
        mock_client.results.return_value = []

        with patch("src.pipeline.fetcher.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta

            with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
                with patch("src.pipeline.fetcher._date_range_query") as mock_query:
                    mock_query.return_value = "fake_query"
                    fetch_daily_papers(categories=["cs.AI"])
                    mock_query.assert_called_once()
                    assert mock_query.call_args[0][1] == 3

    def test_non_monday_uses_config_lookback(self, temp_config_dir):
        tuesday = datetime(2026, 6, 9, 12, 0, 0, tzinfo=timezone.utc)
        mock_client = MagicMock()
        mock_client.results.return_value = []

        with patch("src.pipeline.fetcher.datetime") as mock_dt:
            mock_dt.now.return_value = tuesday
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta

            with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
                with patch("src.pipeline.fetcher._date_range_query") as mock_query:
                    mock_query.return_value = "fake_query"
                    fetch_daily_papers(categories=["cs.AI"])
                    mock_query.assert_called_once()
                    assert mock_query.call_args[0][1] == 1

    def test_explicit_lookback_overrides_monday(self, temp_config_dir):
        monday = datetime(2026, 6, 8, 12, 0, 0, tzinfo=timezone.utc)
        mock_client = MagicMock()
        mock_client.results.return_value = []

        with patch("src.pipeline.fetcher.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            mock_dt.timezone = timezone
            mock_dt.timedelta = timedelta

            with patch("src.pipeline.fetcher._make_client", return_value=mock_client):
                with patch("src.pipeline.fetcher._date_range_query") as mock_query:
                    mock_query.return_value = "fake_query"
                    fetch_daily_papers(categories=["cs.AI"], lookback_days=5)
                    mock_query.assert_called_once()
                    assert mock_query.call_args[0][1] == 5


@pytest.mark.unit
class TestConstants:
    def test_arxiv_categories_contains_key_categories(self):
        assert "cs.AI" in ARXIV_CATEGORIES
        assert "cs.CL" in ARXIV_CATEGORIES
        assert "cs.LG" in ARXIV_CATEGORIES

    def test_canonical_id_strips_version(self):
        assert canonical_id("2505.12345v3") == "2505.12345"
        assert canonical_id("quant-ph/0201082v1") == "quant-ph/0201082"
        assert canonical_id("2505.12345") == "2505.12345"


@pytest.mark.unit
class TestArxivPaperExtra:
    def test_from_dict(self):
        d = {
            "arxiv_id": "2505.1",
            "title": "Test",
            "authors": ["A"],
            "abstract": "abs",
            "published": "2025-05-28T00:00:00+00:00",
            "url": "http://a", "pdf_url": "http://b",
            "categories": ["cs.AI"], "comment": "note",
        }
        p = ArxivPaper.from_dict(d)
        assert p.arxiv_id == "2505.1"
        assert p.title == "Test"
        assert p.comment == "note"

    def test_from_dict_strips_version(self):
        d = {
            "arxiv_id": "2505.1v7",
            "title": "Test",
            "authors": ["A"],
            "abstract": "abs",
            "published": "2025-05-28T00:00:00+00:00",
            "url": "http://a", "pdf_url": "http://b",
            "categories": ["cs.AI"], "comment": "",
        }
        assert ArxivPaper.from_dict(d).arxiv_id == "2505.1"


@pytest.mark.unit
class TestCacheOperations:
    def test_cache_path_format(self):
        p = _cache_path(["cs.CV", "cs.AI"], 1)
        assert p.name.endswith(".json")
        assert "cs.AI" in p.name

    def test_load_cache_nonexistent(self, tmp_path):
        from src.pipeline.fetcher import _CACHE_DIR
        import src.pipeline.fetcher as af
        orig = af._CACHE_DIR
        af._CACHE_DIR = tmp_path
        try:
            result = _load_cache(["cs.AI"], 1)
            assert result is None
        finally:
            af._CACHE_DIR = orig

    def test_load_cache_corrupted(self, tmp_path):
        import src.pipeline.fetcher as af
        orig = af._CACHE_DIR
        af._CACHE_DIR = tmp_path
        try:
            p = _cache_path(["cs.AI"], 1)
            p.write_text("not json")
            result = _load_cache(["cs.AI"], 1)
            assert result is None
        finally:
            af._CACHE_DIR = orig

    def test_load_cache_wrong_date(self, tmp_path):
        import src.pipeline.fetcher as af
        orig = af._CACHE_DIR
        af._CACHE_DIR = tmp_path
        try:
            p = _cache_path(["cs.AI"], 1)
            yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y%m%d")
            data = {
                "fetch_date": yesterday,
                "papers": [],
                "categories": ["cs.AI"],
                "lookback_days": 1,
            }
            p.write_text(json.dumps(data))
            result = _load_cache(["cs.AI"], 1)
            assert result is None
        finally:
            af._CACHE_DIR = orig

    def test_save_cache_removes_stale_files(self, tmp_path):
        import src.pipeline.fetcher as af
        orig = af._CACHE_DIR
        af._CACHE_DIR = tmp_path
        try:
            stale = tmp_path / "arxiv_stale.json"
            stale.write_text(json.dumps({"fetch_date": "20000101"}))
            _save_cache([], ["cs.AI"], 1)
            assert not stale.exists()
            assert _cache_path(["cs.AI"], 1).exists()
        finally:
            af._CACHE_DIR = orig

    def test_save_cache_survives_corrupt_stale_file(self, tmp_path):
        import src.pipeline.fetcher as af
        orig = af._CACHE_DIR
        af._CACHE_DIR = tmp_path
        try:
            corrupt = tmp_path / "arxiv_corrupt.json"
            corrupt.write_text("not json")
            _save_cache([], ["cs.AI"], 1)
            assert _cache_path(["cs.AI"], 1).exists()
        finally:
            af._CACHE_DIR = orig


@pytest.mark.unit
class TestMakeClient:
    def test_creates_client(self, temp_config_dir):
        client = _make_client()
        assert client is not None
