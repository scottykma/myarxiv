import json
from unittest.mock import MagicMock, patch

import pytest

from src.chat.engine import (
    _parse_function_call,
    _split_response,
    _try_parse_json_actions,
    build_system_prompt,
    execute_action,
    parse_response,
    parse_response_stream,
)


def _make_stream_chunks(content_text: str) -> list[MagicMock]:
    chunk = MagicMock()
    delta = MagicMock()
    delta.reasoning_content = "thinking..."
    delta.content = content_text
    chunk.choices = [MagicMock(delta=delta)]
    return [chunk]


@pytest.mark.unit
class TestBuildSystemPrompt:
    def test_includes_config(self, temp_config_dir):
        prompt = build_system_prompt()
        assert "keywords_include:" in prompt
        assert "/ADD(" in prompt
        assert "Researcher Profile" in prompt


@pytest.mark.unit
class TestSplitResponse:
    def test_chat_only(self):
        chat, actions, _ = _split_response("You are monitoring cs.CV and cs.AI.", "thinking")
        assert "cs.CV" in chat
        assert len(actions) == 0

    def test_action_only(self):
        chat, actions, _ = _split_response("/ADD(DiT)\n/REMOVE(deep learning)", "thinking")
        assert len(actions) == 2
        assert actions[0]["action"] == "add_keywords"

    def test_mixed(self):
        chat, actions, _ = _split_response("Sure!\n/ADD(DiT)", "thinking")
        assert "Sure" in chat
        assert len(actions) == 1

    def test_json_fallback(self):
        chat, actions, _ = _split_response('[{"action": "add_keywords", "keywords": ["DiT"]}]', "thinking")
        assert len(actions) == 1

    def test_empty_response(self):
        chat, actions, _ = _split_response("", "thinking")
        assert "trouble" in chat.lower()
        assert len(actions) == 0


@pytest.mark.unit
class TestParseResponse:
    def test_streaming(self, temp_config_dir, mock_env, monkeypatch):
        mock_client = MagicMock()
        mock_client.call.return_value = _make_stream_chunks("Sure!\n/ADD(DiT)")[0]
        mock_client.call.return_value = _make_stream_chunks("Sure!\n/ADD(DiT)")[0]

        def _fake_chunks(*a, **k):
            stream = _make_stream_chunks("Sure!\n/ADD(DiT)")
            for s in stream:
                delta = s.choices[0].delta
                reasoning = ""
                text = ""
                if delta.reasoning_content:
                    reasoning += delta.reasoning_content
                if delta.content:
                    text += delta.content
                yield reasoning, text, False
            yield reasoning, text, True

        monkeypatch.setattr("src.chat.engine.get_fast", lambda: mock_client)
        monkeypatch.setattr("src.chat.engine._parse_stream", _fake_chunks)

        messages = [{"role": "system", "content": build_system_prompt()}, {"role": "user", "content": "add DiT"}]
        chat, actions, reasoning = parse_response(messages)
        assert "Sure" in chat
        assert len(actions) == 1
        assert "thinking" in reasoning

    def test_session(self, temp_config_dir, mock_env, monkeypatch):
        def _fake_chunks(*a, **k):
            yield "thinking...", "/ADD(multi-agent)", False
            yield "thinking...", "/ADD(multi-agent)", True

        monkeypatch.setattr("src.chat.engine._parse_stream", _fake_chunks)

        messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": "add agent"},
            {"role": "assistant", "content": "/ADD(agent)"},
            {"role": "user", "content": "also add multi-agent"},
        ]
        chat, actions, reasoning = parse_response(messages)
        assert len(actions) == 1


@pytest.mark.unit
class TestParseFunctionCall:
    def test_add(self):
        r = _parse_function_call("/ADD(DiT, attention)")
        assert r == {"action": "add_keywords", "keywords": ["DiT", "attention"]}

    def test_remove(self):
        r = _parse_function_call("/REMOVE(deep learning)")
        assert r == {"action": "remove_keywords", "keywords": ["deep learning"]}

    def test_exclude(self):
        r = _parse_function_call("/EXCLUDE(nlp, robotics)")
        assert r == {"action": "add_exclude", "keywords": ["nlp", "robotics"]}

    def test_cats(self):
        r = _parse_function_call("/CATS(cs.CV, cs.AI)")
        assert r == {"action": "set_categories", "categories": ["cs.CV", "cs.AI"]}

    def test_score(self):
        r = _parse_function_call("/SCORE(8)")
        assert r == {"action": "set_min_score", "value": 8}

    def test_max(self):
        r = _parse_function_call("/MAX(15)")
        assert r == {"action": "set_max_papers", "value": 15}

    def test_weight(self):
        r = _parse_function_call("/WEIGHT(video generation, 3)")
        assert r == {"action": "set_keyword_weight", "keyword": "video generation", "weight": 3}

    def test_weight_invalid(self):
        assert _parse_function_call("/WEIGHT(video generation, abc)") is None

    def test_plain_text(self):
        assert _parse_function_call("hello world") is None

    def test_case_insensitive(self):
        r = _parse_function_call("/add(DiT)")
        assert r["action"] == "add_keywords"


@pytest.mark.unit
class TestExecuteAction:
    @pytest.fixture(autouse=True)
    def setup_config(self, temp_config_dir):
        import src.config
        src.config.reload()

    def test_add_keywords(self):
        results = execute_action({"action": "add_keywords", "keywords": ["gnn"]})
        from src.config import get
        assert "gnn" in get("interests.keywords_include")

    def test_remove_keywords(self):
        results = execute_action({"action": "remove_keywords", "keywords": ["agent"]})
        from src.config import get
        assert "agent" not in get("interests.keywords_include")

    def test_set_categories(self):
        results = execute_action({"action": "set_categories", "categories": ["cs.CV"]})
        from src.config import get
        assert get("interests.categories") == ["cs.CV"]

    def test_add_exclude(self):
        results = execute_action({"action": "add_exclude", "keywords": ["robotics"]})
        from src.config import get
        assert "robotics" in get("interests.keywords_exclude")

    def test_remove_exclude(self):
        execute_action({"action": "add_exclude", "keywords": ["robotics"]})
        results = execute_action({"action": "remove_exclude", "keywords": ["robotics"]})
        from src.config import get
        assert "robotics" not in get("interests.keywords_exclude")

    def test_set_max_papers(self):
        results = execute_action({"action": "set_max_papers", "value": 20})
        from src.config import get
        assert get("daily.max_papers") == 20

    def test_set_min_score(self):
        results = execute_action({"action": "set_min_score", "value": 5})
        from src.config import get
        assert get("daily.min_relevance_score") == 5

    def test_set_min_score_none_value(self):
        results = execute_action({"action": "set_min_score", "value": None})
        assert "Invalid" in results[0][1]

    def test_set_max_papers_none_value(self):
        results = execute_action({"action": "set_max_papers", "value": None})
        assert "Invalid" in results[0][1]

    def test_add_exclude_already_exists(self):
        execute_action({"action": "add_exclude", "keywords": ["robotics"]})
        results = execute_action({"action": "add_exclude", "keywords": ["robotics"]})
        assert "Already" in results[0][1]

    def test_add_keywords_already_exists(self):
        from src.config import get
        existing = get("interests.keywords_include", [])
        if existing:
            results = execute_action({"action": "add_keywords", "keywords": [existing[0]]})
            assert "Already" in results[0][1]

    def test_remove_keywords_not_found(self):
        results = execute_action({"action": "remove_keywords", "keywords": ["nonexistent"]})
        assert "Not found" in results[0][1]

    def test_remove_exclude_not_found(self):
        results = execute_action({"action": "remove_exclude", "keywords": ["nonexistent"]})
        assert "Not in" in results[0][1]

    def test_none_action(self):
        results = execute_action({"not_action": "x"})
        assert len(results) == 0

    def test_invalid_categories_are_rejected(self):
        from src.config import get
        before = get("interests.categories")
        results = execute_action({"action": "set_categories", "categories": ["foo"]})
        assert "Unknown categories" in results[0][1]
        assert get("interests.categories") == before

    def test_invalid_score_is_rejected(self):
        from src.config import get
        before = get("daily.min_relevance_score")
        results = execute_action({"action": "set_min_score", "value": 99})
        assert "Invalid score" in results[0][1]
        assert get("daily.min_relevance_score") == before

    def test_invalid_max_is_rejected(self):
        from src.config import get
        before = get("daily.max_papers")
        results = execute_action({"action": "set_max_papers", "value": 99})
        assert "Invalid max papers" in results[0][1]
        assert get("daily.max_papers") == before

    def test_case_insensitive_duplicate(self):
        from src.config import get, set
        set("interests.keywords_include", ["DiT"])
        results = execute_action({"action": "add_keywords", "keywords": ["dit"]})
        assert "Already" in results[0][1]
        assert get("interests.keywords_include") == ["DiT"]

    def test_empty_add(self):
        results = execute_action({"action": "add_keywords", "keywords": []})
        assert "No keywords" in results[0][1]

    def test_string_keywords_are_split(self):
        from src.config import get
        execute_action({"action": "add_keywords", "keywords": "gnn, vlm"})
        keywords = get("interests.keywords_include")
        assert "gnn" in keywords
        assert "vlm" in keywords

    def test_action_is_persisted(self):
        from src.config import reload
        execute_action({"action": "add_keywords", "keywords": ["persisted"]})
        reload()
        from src.config import get
        assert "persisted" in get("interests.keywords_include")

    def test_missing_keywords_returns_message(self):
        results = execute_action({"action": "add_keywords"})
        assert "No keywords" in results[0][1]

    def test_non_list_keywords_are_stringified(self):
        from src.config import get
        execute_action({"action": "add_keywords", "keywords": 123})
        assert "123" in get("interests.keywords_include")

    def test_empty_remove_returns_message(self):
        results = execute_action({"action": "remove_keywords", "keywords": []})
        assert "No keywords" in results[0][1]

    def test_missing_categories_returns_message(self):
        results = execute_action({"action": "set_categories"})
        assert "No categories" in results[0][1]

    def test_categories_string_is_split(self):
        from src.config import get
        execute_action({"action": "set_categories", "categories": "cs.CV, cs.AI"})
        assert get("interests.categories") == ["cs.CV", "cs.AI"]

    def test_save_error_is_reported(self, monkeypatch):
        def _fail_save(*args, **kwargs):
            raise OSError("read-only")

        monkeypatch.setattr("src.chat.engine.save", _fail_save)
        results = execute_action({"action": "add_keywords", "keywords": ["new"]})
        assert any("Failed to save" in message for _color, message in results)

    def test_set_keyword_weight(self):
        from src.config import get
        results = execute_action({"action": "set_keyword_weight", "keyword": "agent", "weight": 3})
        assert "set to 3" in results[0][1]
        assert get("interests.keyword_weights") == {"agent": 3}

    def test_set_keyword_weight_missing(self):
        results = execute_action({"action": "set_keyword_weight", "keyword": "missing", "weight": 3})
        assert "not in include list" in results[0][1]

    def test_set_keyword_weight_invalid(self):
        results = execute_action({"action": "set_keyword_weight", "keyword": "agent", "weight": 9})
        assert "Invalid weight" in results[0][1]

    def test_set_keyword_weight_unchanged(self):
        execute_action({"action": "set_keyword_weight", "keyword": "agent", "weight": 2})
        results = execute_action({"action": "set_keyword_weight", "keyword": "agent", "weight": 2})
        assert "already" in results[0][1]

    def test_remove_keyword_drops_weight(self):
        from src.config import get, set
        set("interests.keyword_weights", {"agent": 3, "other": 2})
        execute_action({"action": "remove_keywords", "keywords": ["agent"]})
        assert "agent" not in get("interests.keyword_weights")
        assert get("interests.keyword_weights")["other"] == 2

    def test_persist_false_does_not_write(self):
        from src.config import get, reload
        before = get("interests.keywords_include")
        execute_action({"action": "add_keywords", "keywords": ["temporary"]}, persist=False)
        assert "temporary" in get("interests.keywords_include")
        reload()
        assert get("interests.keywords_include") == before


@pytest.mark.unit
class TestTryParseJsonActions:
    def test_dict_action(self):
        result = _try_parse_json_actions('{"action": "add_keywords", "keywords": ["DiT"]}')
        assert len(result) == 1
        assert result[0]["action"] == "add_keywords"

    def test_list_of_actions(self):
        result = _try_parse_json_actions('[{"action": "add_keywords", "keywords": ["DiT"]}]')
        assert len(result) == 1

    def test_invalid_json(self):
        result = _try_parse_json_actions("not json")
        assert result == []

    def test_json_without_action_key(self):
        result = _try_parse_json_actions('{"other": 1}')
        assert result == []

    def test_code_block_json(self):
        result = _try_parse_json_actions('```json\n{"action": "add_keywords", "keywords": ["DiT"]}\n```')
        assert len(result) == 1


@pytest.mark.unit
class TestParseFunctionCallExtra:
    def test_max_invalid(self):
        r = _parse_function_call("/MAX(abc)")
        assert r is None

    def test_score_invalid(self):
        r = _parse_function_call("/SCORE(abc)")
        assert r is None

    def test_unexclude(self):
        r = _parse_function_call("/UNEXCLUDE(survey)")
        assert r == {"action": "remove_exclude", "keywords": ["survey"]}


@pytest.mark.unit
class TestParseResponseStream:
    def test_streaming_yields(self, temp_config_dir, mock_env, monkeypatch):
        def _fake_chunks(*a, **k):
            yield "thinking...", "Sure!\n/ADD(DiT)", False
            yield "thinking...", "Sure!\n/ADD(DiT)", True

        monkeypatch.setattr("src.chat.engine._parse_stream", _fake_chunks)

        messages = [{"role": "system", "content": build_system_prompt()}, {"role": "user", "content": "add DiT"}]
        items = list(parse_response_stream(messages))
        assert len(items) >= 1
        final = items[-1]
        assert final[4] is True


@pytest.mark.unit
class TestBuildSystemPromptExtra:
    def test_with_profile_data(self, temp_config_dir):
        from src.config import set, reload
        reload()
        set("profile.name", "Test")
        set("profile.affiliation", "MIT")
        set("profile.interests", ["CV"])
        set("profile.recent_papers", [{"title": "Paper", "year": "2025"}])
        prompt = build_system_prompt()
        assert "Test" in prompt
        assert "MIT" in prompt
        assert "CV" in prompt

    def test_empty_profile(self, temp_config_dir):
        from src.config import set, reload
        reload()
        set("profile.name", "")
        set("profile.affiliation", "")
        set("profile.interests", [])
        set("profile.recent_papers", [])
        prompt = build_system_prompt()
        assert "(none)" in prompt


@pytest.mark.unit
class TestParseStreamErrors:
    def test_missing_api_key(self, monkeypatch, temp_config_dir):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        import src.llm
        src.llm._fast_instance = None
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            from src.llm import LLMClient
            LLMClient("fast")


@pytest.mark.unit
class TestParseStreamDirect:
    def test_parse_stream_returns_data(self, temp_config_dir, mock_env, monkeypatch):
        from src.chat.engine import _parse_stream

        mock_chunk = MagicMock()
        mock_delta = MagicMock()
        mock_delta.reasoning_content = "thinking..."
        mock_delta.content = "Hello world"
        mock_chunk.choices = [MagicMock(delta=mock_delta)]

        mock_client = MagicMock()
        mock_client.call.return_value = [mock_chunk]
        monkeypatch.setattr("src.chat.engine.get_fast", lambda: mock_client)
        import src.llm
        src.llm._fast_instance = None

        messages = [{"role": "user", "content": "hi"}]
        items = list(_parse_stream(messages))
        assert len(items) >= 1
        assert items[-1][2] is True
