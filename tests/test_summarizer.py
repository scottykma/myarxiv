import json
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.pipeline.summarizer import summarize_papers


def _setup_mock_llm(monkeypatch):
    mock_client = MagicMock()
    mock_client.call.return_value = MagicMock(choices=[
        MagicMock(message=MagicMock(content=json.dumps({
            "summary": "A summary", "keywords": ["kw"]
        })))
    ])
    mock_client.parse_json.side_effect = lambda s: json.loads(
        s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    monkeypatch.setattr("src.pipeline.summarizer.get_fast", lambda: mock_client)
    return mock_client


@pytest.mark.unit
class TestSummarizePapers:
    def test_successful_summary(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch)
        paper = ArxivPaper(sample_arxiv_result)

        with patch("src.pipeline.summarizer.time.sleep", return_value=None):
            results = summarize_papers([(paper, 9, "Very relevant")])
            assert len(results) == 1
            assert results[0]["score"] == 9
            assert "A summary" == results[0]["summary"]

    def test_fallback_on_parse_error(self, temp_config_dir, mock_env, sample_arxiv_result, monkeypatch):
        mock_client = MagicMock()
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content="not json"))
        ])
        mock_client.parse_json.side_effect = json.JSONDecodeError("bad", "", 0)
        monkeypatch.setattr("src.pipeline.summarizer.get_fast", lambda: mock_client)

        paper = ArxivPaper(sample_arxiv_result)
        with patch("src.pipeline.summarizer.time.sleep", return_value=None):
            results = summarize_papers([(paper, 9, "test")])
            assert len(results) == 1
            assert results[0]["keywords"] == []

    def test_missing_api_key(self, monkeypatch, temp_config_dir):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import src.llm
        src.llm._fast_instance = None
        from src.llm import LLMClient
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMClient("fast")
