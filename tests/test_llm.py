import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.llm import LLMClient, get_fast, get_pro


@pytest.mark.unit
class TestLLMClient:
    def test_init_fast(self, temp_config_dir, mock_env):
        client = LLMClient("fast")
        assert client.model == "deepseek-v4-flash"
        assert "api.deepseek.com" in client.base_url

    def test_init_pro(self, temp_config_dir, mock_env):
        client = LLMClient("pro")
        assert client.model == "deepseek-v4-flash"

    def test_init_missing_key(self, temp_config_dir, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import src.llm
        src.llm._fast_instance = None
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMClient("fast")

    def test_call(self, temp_config_dir, mock_env):
        client = LLMClient("fast")
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = MagicMock()
        resp = client.call([{"role": "user", "content": "hi"}], temperature=0.5, max_tokens=100, thinking=True)
        assert resp is not None

    def test_call_no_temperature(self, temp_config_dir, mock_env):
        client = LLMClient("fast")
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = MagicMock()
        resp = client.call([{"role": "user", "content": "hi"}], max_tokens=100)
        assert resp is not None

    def test_call_stream(self, temp_config_dir, mock_env):
        client = LLMClient("fast")
        client._client = MagicMock()
        client._client.chat.completions.create.return_value = MagicMock()
        resp = client.call([{"role": "user", "content": "hi"}], stream=True, thinking=False)
        assert resp is not None

    def test_parse_json(self):
        result = LLMClient.parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_with_fences(self):
        result = LLMClient.parse_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}

    def test_parse_json_list(self):
        result = LLMClient.parse_json('[{"a": 1}, {"b": 2}]')
        assert len(result) == 2


@pytest.mark.unit
class TestSingletons:
    def test_get_fast_returns_same_instance(self, temp_config_dir, mock_env, monkeypatch):
        import src.llm
        src.llm._fast_instance = None
        src.llm._pro_instance = None
        c1 = get_fast()
        c2 = get_fast()
        assert c1 is c2

    def test_get_pro_returns_same_instance(self, temp_config_dir, mock_env, monkeypatch):
        import src.llm
        src.llm._fast_instance = None
        src.llm._pro_instance = None
        c1 = get_pro()
        c2 = get_pro()
        assert c1 is c2

    def test_cache_reset(self, temp_config_dir, mock_env, monkeypatch):
        import src.llm
        src.llm._fast_instance = MagicMock()
        c = get_fast()
        assert isinstance(c, MagicMock)
        src.llm._fast_instance = None
