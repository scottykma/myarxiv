from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.pipeline.preview import build_preview, format_preview, preview_papers, preview_to_json


def _make_paper(title, abstract="", arxiv_id="2505.1"):
    result = MagicMock()
    result.get_short_id.return_value = arxiv_id
    result.title = title
    result.summary = abstract
    author = MagicMock()
    author.name = "Author"
    result.authors = [author]
    result.published = datetime.now(timezone.utc)
    result.entry_id = f"https://arxiv.org/abs/{arxiv_id}"
    result.pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    result.categories = ["cs.CV"]
    result.comment = ""
    return ArxivPaper(result)


@pytest.mark.unit
class TestBuildPreview:
    def test_scores_candidates(self, temp_config_dir):
        paper = _make_paper("Video generation with memory", "A video generation model")
        result = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        assert result["fetched"] == 1
        assert result["candidates"][0]["paper"] is paper
        assert result["candidates"][0]["score"] > 0
        assert "video generation" in result["candidates"][0]["keywords"]

    def test_excludes_papers(self, temp_config_dir):
        paper = _make_paper("Time series forecasting with transformers")
        result = build_preview([paper], include_keywords=["video"], exclude_keywords=["time series forecasting"])
        assert result["candidates"] == []
        assert result["excluded"][0]["keyword"] == "time series forecasting"

    def test_sorts_by_score(self, temp_config_dir):
        low = _make_paper("Video generation", arxiv_id="1")
        high = _make_paper("Video generation with memory", "video generation memory", arxiv_id="2")
        result = build_preview([low, high], include_keywords=["video generation", "memory"], exclude_keywords=[])
        assert result["candidates"][0]["paper"] is high

    def test_top_n_truncates(self, temp_config_dir):
        papers = [_make_paper(f"Video generation {i}", arxiv_id=str(i)) for i in range(5)]
        result = build_preview([*papers], include_keywords=["video generation"], exclude_keywords=[], top_n=2)
        assert len(result["candidates"]) == 2

    def test_stats_include_zero_hits(self, temp_config_dir):
        paper = _make_paper("Video generation", arxiv_id="1")
        result = build_preview([paper], include_keywords=["video generation", "world model"], exclude_keywords=[])
        assert result["stats"]["world model"] == 0

    def test_keyword_weight_boosts_score(self, temp_config_dir):
        import src.config

        paper = _make_paper("Video generation", arxiv_id="1")
        base = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        src.config.set("interests.keyword_weights", {"video generation": 3})
        boosted = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        assert boosted["candidates"][0]["score"] > base["candidates"][0]["score"]
        assert boosted["keyword_weights"]["video generation"] == 3


@pytest.mark.unit
class TestFormatPreview:
    def test_formats_candidates(self, temp_config_dir):
        paper = _make_paper("Video generation with memory", arxiv_id="1")
        result = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        text = format_preview(result)
        assert "Fetched 1 papers" in text
        assert "Video generation with memory" in text

    def test_formats_empty(self, temp_config_dir):
        text = format_preview({"fetched": 0, "candidates": [], "excluded": [], "stats": {}})
        assert "no candidates" in text

    def test_shows_excluded_and_stats(self, temp_config_dir):
        excluded = _make_paper("Time series forecasting", arxiv_id="1")
        result = build_preview([excluded], include_keywords=["video"], exclude_keywords=["time series forecasting"])
        text = format_preview(result, show_excluded=True, show_stats=True)
        assert "Excluded by keyword" in text
        assert "Keyword hits" in text
        assert "time series forecasting" in text

    def test_shows_empty_excluded_and_stats(self, temp_config_dir):
        paper = _make_paper("Video generation", arxiv_id="1")
        result = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        result["excluded"] = []
        result["stats"] = {}
        text = format_preview(result, show_excluded=True, show_stats=True)
        assert "(none)" in text
        assert "(no keywords configured)" in text

    def test_truncates_long_title(self, temp_config_dir):
        paper = _make_paper("Video generation " + "x" * 200, arxiv_id="1")
        result = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        text = format_preview(result)
        assert "…" in text

    def test_formats_llm_results(self, temp_config_dir):
        paper = _make_paper("Video generation", arxiv_id="1")
        result = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        result["llm_results"] = [(paper, 8, "relevant")]
        text = format_preview(result)
        assert "LLM selection" in text
        assert "relevant" in text


@pytest.mark.unit
class TestPreviewToJson:
    def test_serializes_papers(self, temp_config_dir):
        paper = _make_paper("Video generation", arxiv_id="2505.1")
        result = build_preview([paper], include_keywords=["video generation"], exclude_keywords=[])
        data = preview_to_json(result)
        assert data["candidates"][0]["paper"]["arxiv_id"] == "2505.1"
        assert data["candidates"][0]["score"] > 0
        assert "keyword_weights" in data
        assert data["llm_results"] == []


@pytest.mark.unit
class TestPreviewPapers:
    def test_calls_fetcher(self, temp_config_dir):
        paper = _make_paper("Video generation", arxiv_id="1")
        with patch("src.pipeline.preview.fetch_daily_papers", return_value=[paper]) as mock_fetch:
            result = preview_papers(days=2, top_n=5, use_cache=False)
        mock_fetch.assert_called_once_with(lookback_days=2, use_cache=False)
        assert result["fetched"] == 1

    def test_llm_scoring(self, temp_config_dir):
        paper = _make_paper("Video generation", arxiv_id="1")
        with patch("src.pipeline.preview.fetch_daily_papers", return_value=[paper]):
            with patch("src.pipeline.preview.chat_final_score", return_value=[(paper, 8, "ok")]) as mock_score:
                result = preview_papers(use_llm=True)
        assert result["llm_results"] == [(paper, 8, "ok")]
        mock_score.assert_called_once()
