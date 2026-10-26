import pytest

from src.interests import (
    add_keywords,
    canonical_keyword,
    category_help,
    drop_weights,
    parse_categories,
    remove_keywords,
    unique_keywords,
    validate_max_papers,
    validate_score,
    validate_weight,
)


@pytest.mark.unit
class TestAddKeywords:
    def test_adds_new_keywords(self):
        updated, added, duplicates = add_keywords(["video"], ["DiT"])
        assert updated == ["video", "DiT"]
        assert added == ["DiT"]
        assert duplicates == []

    def test_deduplicates_case_insensitively(self):
        updated, added, duplicates = add_keywords(["DiT"], ["dit", "video"])
        assert updated == ["DiT", "video"]
        assert added == ["video"]
        assert duplicates == ["DiT"]

    def test_preserves_existing_order(self):
        updated, _, _ = add_keywords(["world model", "DiT"], ["flow matching"])
        assert updated == ["world model", "DiT", "flow matching"]

    def test_ignores_empty_values(self):
        updated, added, duplicates = add_keywords(["video"], ["", "  "])
        assert updated == ["video"]
        assert added == []
        assert duplicates == []


@pytest.mark.unit
class TestRemoveKeywords:
    def test_removes_case_insensitively(self):
        updated, removed, missing = remove_keywords(["DiT", "video"], ["dit"])
        assert updated == ["video"]
        assert removed == ["DiT"]
        assert missing == []

    def test_reports_missing(self):
        updated, removed, missing = remove_keywords(["video"], ["DiT"])
        assert updated == ["video"]
        assert removed == []
        assert missing == ["DiT"]

    def test_deduplicates_current_list(self):
        updated, removed, _ = remove_keywords(["video", "video", "DiT"], ["video"])
        assert updated == ["DiT"]
        assert removed == ["video"]


@pytest.mark.unit
class TestCategories:
    def test_parses_comma_separated(self):
        valid, invalid = parse_categories(["cs.CV, cs.AI"])
        assert valid == ["cs.CV", "cs.AI"]
        assert invalid == []

    def test_canonicalizes_case(self):
        valid, invalid = parse_categories(["CS.CV"])
        assert valid == ["cs.CV"]
        assert invalid == []

    def test_reports_invalid(self):
        valid, invalid = parse_categories(["cs.CV", "foo"])
        assert valid == ["cs.CV"]
        assert invalid == ["foo"]

    def test_ignores_empty(self):
        valid, invalid = parse_categories(["", "  "])
        assert valid == []
        assert invalid == []

    def test_category_help_lists_categories(self):
        assert "cs.CV" in category_help()


@pytest.mark.unit
class TestValidation:
    def test_valid_score(self):
        assert validate_score("7") == 7

    def test_score_out_of_range(self):
        with pytest.raises(ValueError, match="1-10"):
            validate_score(0)
        with pytest.raises(ValueError, match="1-10"):
            validate_score(11)

    def test_score_non_numeric(self):
        with pytest.raises(ValueError, match="Invalid score"):
            validate_score("abc")

    def test_valid_max(self):
        assert validate_max_papers(20) == 20

    def test_max_out_of_range(self):
        with pytest.raises(ValueError, match="1-50"):
            validate_max_papers(0)
        with pytest.raises(ValueError, match="1-50"):
            validate_max_papers(51)

    def test_max_non_numeric(self):
        with pytest.raises(ValueError, match="Invalid max"):
            validate_max_papers(None)

    def test_valid_weight(self):
        assert validate_weight("3") == 3

    def test_weight_out_of_range(self):
        with pytest.raises(ValueError, match="1-5"):
            validate_weight(0)
        with pytest.raises(ValueError, match="1-5"):
            validate_weight(6)

    def test_weight_non_numeric(self):
        with pytest.raises(ValueError, match="Invalid weight"):
            validate_weight("abc")


@pytest.mark.unit
class TestWeightHelpers:
    def test_canonical_keyword(self):
        assert canonical_keyword(["DiT", "video"], "dit") == "DiT"
        assert canonical_keyword(["DiT"], "  DIT ") == "DiT"
        assert canonical_keyword(["DiT"], "missing") is None
        assert canonical_keyword(["DiT"], "") is None

    def test_drop_weights(self):
        assert drop_weights({"DiT": 3, "video": 2}, ["dit"]) == {"video": 2}


@pytest.mark.unit
class TestUniqueKeywords:
    def test_removes_duplicates_and_empties(self):
        assert unique_keywords(["DiT", "dit", "", " video "]) == ["DiT", "video"]
