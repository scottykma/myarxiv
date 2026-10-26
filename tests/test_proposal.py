import pytest

from src import config
from src.chat.proposal import (
    apply_actions,
    build_proposal,
    build_proposed_config,
    format_proposal,
)


@pytest.mark.unit
class TestBuildProposal:
    def test_add_keyword(self, temp_config_dir):
        proposal = build_proposal([{"action": "add_keywords", "keywords": ["flow matching"]}])
        assert proposal["has_changes"] is True
        assert proposal["changes"][0]["op"] == "+"
        assert proposal["changes"][0]["value"] == "flow matching"
        assert proposal["errors"] == []

    def test_add_duplicate_is_note(self, temp_config_dir):
        proposal = build_proposal([{"action": "add_keywords", "keywords": ["agent"]}])
        assert proposal["has_changes"] is False
        assert any("Already present" in note for note in proposal["notes"])

    def test_remove_keyword(self, temp_config_dir):
        proposal = build_proposal([{"action": "remove_keywords", "keywords": ["agent"]}])
        assert proposal["changes"][0]["op"] == "-"
        assert proposal["changes"][0]["value"] == "agent"

    def test_remove_missing_is_note(self, temp_config_dir):
        proposal = build_proposal([{"action": "remove_keywords", "keywords": ["missing"]}])
        assert proposal["has_changes"] is False
        assert any("Not found" in note for note in proposal["notes"])

    def test_add_and_remove_exclude(self, temp_config_dir):
        proposal = build_proposal([
            {"action": "add_exclude", "keywords": ["nlp"]},
            {"action": "remove_exclude", "keywords": ["survey"]},
        ])
        assert proposal["changes"][0]["field"] == "exclude"
        assert proposal["changes"][0]["op"] == "+"
        assert proposal["changes"][1]["op"] == "-"

    def test_set_categories(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_categories", "categories": ["cs.CV"]}])
        assert proposal["changes"][0]["field"] == "categories"
        assert proposal["changes"][0]["after"] == "cs.CV"

    def test_invalid_categories(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_categories", "categories": ["foo"]}])
        assert proposal["has_changes"] is False
        assert "Unknown categories" in proposal["errors"][0]

    def test_empty_categories(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_categories", "categories": []}])
        assert "No categories" in proposal["errors"][0]

    def test_set_scores(self, temp_config_dir):
        proposal = build_proposal([
            {"action": "set_min_score", "value": 5},
            {"action": "set_max_papers", "value": 10},
        ])
        assert len(proposal["changes"]) == 2

    def test_invalid_score(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_min_score", "value": 99}])
        assert proposal["has_changes"] is False
        assert "Invalid score" in proposal["errors"][0]

    def test_invalid_max(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_max_papers", "value": 99}])
        assert "Invalid max papers" in proposal["errors"][0]

    def test_unchanged_value_is_not_a_change(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_min_score", "value": 7}])
        assert proposal["has_changes"] is False
        assert proposal["errors"] == []

    def test_set_weight(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_keyword_weight", "keyword": "agent", "weight": 3}])
        assert proposal["changes"][0]["field"] == "weight:agent"
        assert proposal["changes"][0]["after"] == 3

    def test_invalid_weight_keyword(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_keyword_weight", "keyword": "missing", "weight": 3}])
        assert "not in include list" in proposal["errors"][0]

    def test_invalid_weight(self, temp_config_dir):
        proposal = build_proposal([{"action": "set_keyword_weight", "keyword": "agent", "weight": 9}])
        assert "Invalid weight" in proposal["errors"][0]


@pytest.mark.unit
class TestFormatProposal:
    def test_formats_changes_notes_errors(self):
        proposal = {
            "changes": [
                {"op": "+", "field": "include", "value": "DiT", "weight": 3},
                {"op": "-", "field": "include", "value": "old"},
                {"op": "~", "field": "min_score", "before": 5, "after": 7},
            ],
            "notes": ["Already present: agent"],
            "errors": ["Unknown categories: foo"],
        }
        text = format_proposal(proposal)
        assert "+ include: DiT (weight 3)" in text
        assert "- include: old" in text
        assert "5 -> 7" in text
        assert "Already present" in text
        assert "Unknown categories" in text

    def test_empty_proposal(self):
        text = format_proposal({"changes": [], "notes": [], "errors": []})
        assert "(none)" in text


@pytest.mark.unit
class TestBuildProposedConfig:
    def test_does_not_mutate_live_config(self, temp_config_dir):
        before = list(config.get("interests.keywords_include"))
        proposed = build_proposed_config([{"action": "add_keywords", "keywords": ["new"]}])
        assert proposed is not None
        assert "new" in proposed["interests"]["keywords_include"]
        assert config.get("interests.keywords_include") == before

    def test_apply_actions_persists(self, temp_config_dir):
        results = apply_actions([{"action": "add_keywords", "keywords": ["persisted"]}])
        assert any("Added" in message for _color, message in results)
        config.reload()
        assert "persisted" in config.get("interests.keywords_include")
