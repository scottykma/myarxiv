import json
from unittest.mock import MagicMock, patch

import pytest

from src.profile.fetcher import ScholarProfile
from src.profile.generator import generate_interests


def _setup_mock_llm(monkeypatch):
    mock_client = MagicMock()
    mock_client.call.return_value = MagicMock(choices=[
        MagicMock(message=MagicMock(content="{}"))
    ])
    mock_client.parse_json.side_effect = lambda s: json.loads(
        s.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    )
    monkeypatch.setattr("src.profile.generator.get_fast", lambda: mock_client)
    return mock_client


@pytest.mark.unit
class TestGenerateInterests:
    def test_success(self, temp_config_dir, mock_env, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch)
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content=json.dumps({
                'keywords_include': ['large language model', 'attention mechanism'],
                'keywords_exclude': ['image classification'],
                'categories': ['cs.CL', 'cs.AI', 'cs.LG'],
            })))
        ])

        profile = ScholarProfile()
        profile.name = "Test Author"
        profile.publications = [
            {"title": "Paper 1", "year": "2025", "citation_count": 50},
        ]

        interests = generate_interests(profile)
        assert "keywords_include" in interests
        assert "keywords_exclude" in interests
        assert "categories" in interests
        assert len(interests["keywords_include"]) == 2

    def test_invalid_json(self, temp_config_dir, mock_env, monkeypatch):
        mock_client = _setup_mock_llm(monkeypatch)
        mock_client.call.return_value = MagicMock(choices=[
            MagicMock(message=MagicMock(content="invalid json"))
        ])
        mock_client.parse_json.side_effect = json.JSONDecodeError("bad", "", 0)

        profile = ScholarProfile()
        with pytest.raises(ValueError):
            generate_interests(profile)

    def test_missing_api_key(self, monkeypatch, temp_config_dir):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import src.llm
        src.llm._fast_instance = None
        from src.llm import LLMClient
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMClient("fast")
