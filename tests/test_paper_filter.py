import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.pipeline.filter import (
    _fallback_single,
    _parse_batch_response,
    chat_final_score,
    excluded_by_keyword,
    flash_title_score,
    keyword_hit_counts,
    keyword_prefilter,
    keyword_score,
)


def _setup_mock_llm(monkeypatch, model="fast"):
    mock_client = MagicMock()
    mock_client.model = "deepseek-v4-flash" if model == "fast" else "deepseek-v4-flash"
    mock_client.call.return_value = MagicMock(choices=[MagicMock(message=MagicMock(content="{}"))])
    mock_client.parse_json.side_effect = lambda s: json.loads(
        s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    monkeypatch.setattr("src.pipeline.filter.get_fast", lambda: mock_client)
    monkeypatch.setattr("src.pipeline.filter.get_pro", lambda: mock_client)
    return mock_client


@pytest.mark.unit
class TestKeywordScoring:
    def test_short_keyword_does_not_match_substring(self, temp_config_dir):
        result = MagicMock()
        result.get_short_id.return_value = "1"
        result.title = "Image editing with diffusion transformers"
        result.summary = ""
        result.authors = []
        result.published = datetime.now(timezone.utc)
        result.entry_id = "url"
        result.pdf_url = "pdf"
        result.categories = ["cs.CV"]
        result.comment = ""
        paper = ArxivPaper(result)
        score, matched = keyword_score(paper, ["DiT"])
        assert score == 0
        assert matched == []

    def test_stopword_only_keyword_is_ignored(self, temp_config_dir):
        paper = ArxivPaper(_make_result("Transformers for image generation"))
        score, matched = keyword_score(paper, ["for"])
        assert score == 0
        assert matched == []

    def test_long_keyword_uses_partial_coverage(self, temp_config_dir):
        paper = ArxivPaper(_make_result("Video generation with memory"))
        score, matched = keyword_score(paper, ["memory mechanism for video generation"])
        assert score > 0
        assert matched == ["memory mechanism for video generation"]

    def test_keyword_weight_multiplies_score(self, temp_config_dir):
        paper = ArxivPaper(_make_result("Video generation"))
        base, _ = keyword_score(paper, ["video generation"])
        boosted, _ = keyword_score(paper, ["video generation"], keyword_weights={"video generation": 3})
        assert boosted == base * 3

    def test_invalid_keyword_weights_are_ignored(self, temp_config_dir):
        paper = ArxivPaper(_make_result("Video generation"))
        score, _ = keyword_score(
            paper,
            ["video generation"],
            keyword_weights={"video generation": 99, "other": "bad"},
        )
        assert score > 0

    def test_excluded_by_keyword(self, temp_config_dir):
        paper = ArxivPaper(_make_result("Time series forecasting with transformers"))
        assert excluded_by_keyword(paper, ["time series forecasting"]) == "time series forecasting"
        assert excluded_by_keyword(paper, ["video generation"]) is None

    def test_excluded_by_keyword_skips_stopwords(self, temp_config_dir):
        paper = ArxivPaper(_make_result("Transformers for image generation"))
        assert excluded_by_keyword(paper, ["for"]) is None

    def test_keyword_hit_counts(self, temp_config_dir):
        papers = [
            ArxivPaper(_make_result("Video generation", "video generation model")),
            ArxivPaper(_make_result("World model", "world model for agents")),
        ]
        counts = keyword_hit_counts(papers, ["video generation", "world model", "DiT"])
        assert counts == {"video generation": 1, "world model": 1, "DiT": 0}


@pytest.mark.unit
class TestParseBatchResponse:
    def test_valid_response(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        paper = ArxivPaper(_make_result("Video generation"))
        existing = []
        indices = _parse_batch_response(
            json.dumps([{"index": 0, "score": 8, "reason": "ok"}]),
            [paper],
            existing,
        )
        assert indices == {0}
        assert existing == [(paper, 8, "ok")]

    def test_single_object_response(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        paper = ArxivPaper(_make_result("Video generation"))
        existing = []
        indices = _parse_batch_response(
            json.dumps({"index": 0, "score": 7, "reason": "ok"}),
            [paper],
            existing,
        )
        assert indices == {0}

    def test_duplicate_and_invalid_indices_are_ignored(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        batch = [ArxivPaper(_make_result("A")), ArxivPaper(_make_result("B"))]
        existing = []
        indices = _parse_batch_response(
            json.dumps([
                {"index": 0, "score": 8, "reason": "ok"},
                {"index": 0, "score": 9, "reason": "duplicate"},
                {"index": 5, "score": 9, "reason": "out of range"},
                {"index": 1, "score": 11, "reason": "bad score"},
                "not an object",
            ]),
            batch,
            existing,
        )
        assert indices == {0}
        assert len(existing) == 1

    def test_no_valid_items_raises(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        paper = ArxivPaper(_make_result("Video generation"))
        with pytest.raises(ValueError, match="No valid scored"):
            _parse_batch_response(json.dumps([{"index": 9, "score": 8}]), [paper], [])

    def test_non_list_response_raises(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        paper = ArxivPaper(_make_result("Video generation"))
        with pytest.raises(ValueError, match="not a JSON array"):
            _parse_batch_response(json.dumps("nope"), [paper], [])

    def test_boolean_index_and_score_are_ignored(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        paper = ArxivPaper(_make_result("Video generation"))
        with pytest.raises(ValueError, match="No valid scored"):
            _parse_batch_response(
                json.dumps([{"index": True, "score": 8}, {"index": 0, "score": True}]),
                [paper],
                [],
            )

    def test_invalid_score_type_is_ignored(self, temp_config_dir, monkeypatch):
        _setup_mock_llm(monkeypatch, "fast")
        paper = ArxivPaper(_make_result("Video generation"))
        with pytest.raises(ValueError, match="No valid scored"):
            _parse_batch_response(
                json.dumps([{"index": 0, "score": "not-a-number"}]),
                [paper],
                [],
            )


@pytest.mark.unit
class TestFallbackSingle:
    def test_rejects_out_of_range_score(self, temp_config_dir, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.parse_json.return_value = {"score": 99, "reason": "bad"}
        paper = ArxivPaper(_make_result("Video generation"))
        existing = []
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            _fallback_single(mock_client, [paper], existing)
        assert existing == []


@pytest.mark.unit
class TestBatchMissingFallback:
    def test_flash_missing_paper_is_scored_individually(self, temp_config_dir, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 8, "reason": "batch"}
            ])))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(
                {"score": 7, "reason": "single"}
            )))]),
        ]
        papers = [ArxivPaper(_make_result("A")), ArxivPaper(_make_result("B"))]
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(papers, include_keywords=["a"], exclude_keywords=[], batch_size=2)
        assert len(result) == 2

    def test_pro_missing_paper_is_scored_individually(self, temp_config_dir, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "pro")
        mock_client.call.side_effect = [
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 8, "reason": "batch"}
            ])))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps(
                {"score": 7, "reason": "single"}
            )))]),
        ]
        papers = [
            (ArxivPaper(_make_result("A")), 0, ""),
            (ArxivPaper(_make_result("B")), 0, ""),
        ]
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(papers, min_score=0, max_papers=10, batch_size=2)
        assert len(result) == 2


def _make_result(title, abstract=""):
    result = MagicMock()
    result.get_short_id.return_value = str(abs(hash(title)))
    result.title = title
    result.summary = abstract
    result.authors = []
    result.published = datetime.now(timezone.utc)
    result.entry_id = "url"
    result.pdf_url = "pdf"
    result.categories = ["cs.CV"]
    result.comment = ""
    return result


@pytest.mark.unit
class TestKeywordPrefilter:
    def test_title_match_boosts_score(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        result = keyword_prefilter([paper], include_keywords=["language model"], exclude_keywords=[])
        assert len(result) == 1
        assert result[0] is paper

    def test_exclude_discards(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        result = keyword_prefilter([paper], include_keywords=["language"], exclude_keywords=["novel"])
        assert len(result) == 0

    def test_truncates_to_top_n(self, temp_config_dir):
        from src.pipeline.fetcher import ArxivPaper
        papers = []
        for i in range(10):
            result = MagicMock()
            result.title = f"Deep Learning Paper {i}"
            result.summary = "This is an abstract about deep learning"
            result.get_short_id.return_value = f"2505.{i}"
            result.published = datetime.now(timezone.utc)
            result.entry_id = f"url{i}"
            result.pdf_url = f"pdf{i}"
            result.authors = []
            result.categories = ["cs.AI"]
            result.comment = None
            papers.append(ArxivPaper(result))
        result = keyword_prefilter(papers, include_keywords=["deep learning"], exclude_keywords=[], top_n=3)
        assert len(result) == 3

    def test_empty_input(self):
        result = keyword_prefilter([], include_keywords=["test"], exclude_keywords=[])
        assert result == []

    def test_uses_config_defaults(self, temp_config_dir, sample_arxiv_result):
        paper = ArxivPaper(sample_arxiv_result)
        result = keyword_prefilter([paper])
        assert len(result) == 1


@pytest.mark.unit
class TestFlashTitleScore:
    def test_empty_papers(self, temp_config_dir, mock_env):
        result = flash_title_score([])
        assert result == []

    def test_batch_scoring(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 9, "reason": "Highly relevant"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(
                [paper],
                include_keywords=["llm"],
                exclude_keywords=["survey"],
            )
            assert len(result) == 1
            assert result[0][1] == 9

    def test_sort_and_truncate(self, temp_config_dir, mock_env, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": j, "score": (5 - j), "reason": "ok"}
                for j in range(5)
            ])))
        ])

        papers = []
        for i in range(5):
            r = MagicMock()
            r.title = f"Paper {i}"
            r.abstract = f"Abstract {i}"
            r.get_short_id.return_value = f"2505.{i}"
            r.authors = []
            r.categories = ["cs.AI"]
            papers.append(ArxivPaper(r))

        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(papers, include_keywords=["paper"], exclude_keywords=[], top_n=2)
            assert len(result) == 2
            assert result[0][1] > result[1][1]

    def test_batch_error_falls_back(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.side_effect = [
            Exception("batch fail"),
            MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
                "score": 7, "reason": "fallback"
            })))]),
        ]

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(
                [paper],
                include_keywords=["llm"],
                exclude_keywords=["survey"],
                batch_size=1,
            )
            assert len(result) == 1

    def test_fallback_continues_on_error(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch, "fast")
        mock_client.call.side_effect = Exception("fail")

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = flash_title_score(
                [paper],
                include_keywords=["llm"],
                exclude_keywords=["survey"],
                batch_size=1,
            )
            assert result == []


@pytest.mark.unit
class TestChatFinalScore:
    def test_empty_papers(self, temp_config_dir, mock_env):
        result = chat_final_score([])
        assert result == []

    def test_pro_batch_scoring(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 8, "reason": "relevant"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(
                [(paper, 9, "pre-reason")],
                min_score=5,
                max_papers=5,
            )
            assert len(result) == 1
            assert result[0][1] == 8

    def test_below_threshold(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 3, "reason": "irrelevant"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(
                [(paper, 9, "pre-reason")],
                min_score=7,
                max_papers=5,
            )
            assert len(result) == 0

    def test_truncates_to_max(self, temp_config_dir, mock_env, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": j, "score": 10 - j, "reason": "good"}
                for j in range(5)
            ])))
        ])

        papers = []
        for i in range(5):
            r = MagicMock()
            r.title = f"Paper {i}"
            r.abstract = f"Abstract {i}"
            r.get_short_id.return_value = f"2505.{i}"
            r.authors = []
            r.categories = ["cs.AI"]
            papers.append((ArxivPaper(r), 10 - i, "reason"))

        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(papers, min_score=0, max_papers=2)
            assert len(result) == 2

    def test_pro_error_falls_to_flash(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_pro = _setup_mock_llm(monkeypatch, "pro")
        mock_pro.call.side_effect = Exception("pro fail")

        mock_fast = _setup_mock_llm(monkeypatch, "fast")
        mock_fast.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps([
                {"index": 0, "score": 7, "reason": "flash fallback"}
            ])))
        ])

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.filter.time.sleep", return_value=None):
            result = chat_final_score(
                [(paper, 9, "pre")],
                min_score=5,
                max_papers=5,
                batch_size=1,
            )
            assert len(result) == 1
