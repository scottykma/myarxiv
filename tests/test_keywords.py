import pytest

from src.keywords import (
    clean_keyword,
    contains_all_tokens,
    contains_phrase,
    content_tokens,
    covers_keyword,
    keyword_matches_text,
    matched_content_tokens,
    token_coverage,
)


@pytest.mark.unit
class TestKeywordNormalization:
    def test_clean_collapses_whitespace(self):
        assert clean_keyword("  video   generation  ") == "video generation"

    def test_clean_none(self):
        assert clean_keyword(None) == ""

    def test_content_tokens_remove_stopwords(self):
        tokens = content_tokens("memory mechanism for video generation")
        assert tokens == ["memory", "mechanism", "video", "generation"]

    def test_content_tokens_deduplicate(self):
        assert content_tokens("video video generation") == ["video", "generation"]

    def test_content_tokens_only_stopwords(self):
        assert content_tokens("for in the") == []


@pytest.mark.unit
class TestPhraseMatching:
    def test_exact_phrase(self):
        assert contains_phrase("Long video generation with memory", "video generation")

    def test_phrase_allows_plural(self):
        assert contains_phrase("Large Language Models for vision", "large language model")

    def test_phrase_requires_order(self):
        assert not contains_phrase("generation of video", "video generation")

    def test_empty_keyword(self):
        assert not contains_phrase("anything", "")

    def test_none_text(self):
        assert not contains_phrase(None, "video")


@pytest.mark.unit
class TestTokenMatching:
    def test_short_token_does_not_match_substring(self):
        assert not contains_all_tokens("Image editing with diffusion", "DiT")

    def test_short_token_does_not_match_ai_inside_word(self):
        assert not contains_all_tokens("This paper said nothing", "AI")

    def test_all_tokens_present(self):
        assert contains_all_tokens("Video generation with memory", "memory video generation")

    def test_empty_text(self):
        assert not contains_all_tokens(None, "video")

    def test_stopword_only_keyword(self):
        assert not contains_all_tokens("Transformers for vision", "for")

    def test_stopwords_ignored(self):
        assert covers_keyword(
            "Video generation with memory",
            "memory mechanism for video generation",
        )

    def test_partial_coverage_below_threshold(self):
        assert not covers_keyword(
            "Transformers for image generation",
            "memory mechanism for video generation",
        )

    def test_token_coverage(self):
        assert token_coverage("Video generation with memory", "memory mechanism for video generation") == 0.75

    def test_token_coverage_without_content_tokens(self):
        assert token_coverage("anything", "for") == 0.0

    def test_matched_content_tokens(self):
        assert matched_content_tokens("Video generation with memory", "memory mechanism video") == [
            "memory",
            "video",
        ]


@pytest.mark.unit
class TestKeywordMatchesText:
    def test_matches_title(self):
        assert keyword_matches_text("Video generation with memory", "video generation")

    def test_stopword_only_keyword_never_matches(self):
        assert not keyword_matches_text("Transformers for image generation", "for")

    def test_empty_text(self):
        assert not keyword_matches_text("", "video")
