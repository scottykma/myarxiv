from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.pipeline.fetcher import ArxivPaper
from src.report import build_plain_text, build_report


def _paper(sample_arxiv_result, authors=2, pdf=True):
    result = MagicMock()
    result.get_short_id.return_value = "2505.12345"
    result.title = "A Novel Approach to Large Language Models"
    result.summary = "This paper presents a new method for training language models."
    author_mocks = []
    for index in range(authors):
        author = MagicMock()
        author.name = f"Author {index}"
        author_mocks.append(author)
    result.authors = author_mocks
    result.published = datetime(2025, 5, 28, tzinfo=timezone.utc)
    result.entry_id = "https://arxiv.org/abs/2505.12345"
    result.pdf_url = "https://arxiv.org/pdf/2505.12345" if pdf else ""
    result.categories = ["cs.CL", "cs.AI"]
    result.comment = "Accepted at ACL 2025"
    return ArxivPaper(result)


@pytest.mark.unit
class TestBuildReport:
    def test_includes_summary_and_actions(self, temp_config_dir, sample_arxiv_result):
        report = build_report([(_paper(sample_arxiv_result), 9, "Highly relevant")], fetched=225, prefiltered=60)
        assert "Daily arXiv Digest" in report
        assert "225" in report
        assert "60" in report
        assert "Why it matters" in report
        assert "Read paper" in report
        assert ">PDF<" in report
        assert "Top 9/10" in report
        assert "Highly relevant" in report

    def test_more_than_five_authors(self, temp_config_dir, sample_arxiv_result):
        report = build_report([(_paper(sample_arxiv_result, authors=6), 8, "ok")])
        assert "et al." in report

    def test_without_pdf_or_comment(self, temp_config_dir, sample_arxiv_result):
        paper = _paper(sample_arxiv_result, pdf=False)
        paper.comment = ""
        report = build_report([(paper, 6, "")])
        assert ">PDF<" not in report
        assert "Note" not in report
        assert "Why it matters" not in report

    def test_escapes_untrusted_content(self, temp_config_dir, sample_arxiv_result):
        paper = _paper(sample_arxiv_result)
        paper.title = "<script>alert(1)</script>"
        paper.abstract = "<img src=x>"
        report = build_report([(paper, 9, "<b>reason</b>")])
        assert "<script>" not in report
        assert "&lt;script&gt;" in report
        assert "<img" not in report
        assert "&lt;b&gt;reason&lt;/b&gt;" in report

    def test_dark_theme(self, temp_config_dir, sample_arxiv_result):
        report = build_report([(_paper(sample_arxiv_result), 9, "ok")], theme="dark")
        assert "#0E0D0C" in report
        assert "#F3EDE3" in report
        assert 'color-scheme" content="dark"' in report
        assert "#7FB08A" in report


@pytest.mark.unit
class TestBuildPlainText:
    def test_includes_paper_details(self, temp_config_dir, sample_arxiv_result):
        text = build_plain_text([(_paper(sample_arxiv_result), 9, "Highly relevant")], fetched=225, prefiltered=60)
        assert "MyArxiv" in text
        assert "225 fetched" in text
        assert "60 candidates" in text
        assert "1 selected" in text
        assert "9/10" in text
        assert "Author 0" in text
        assert "Highly relevant" in text
        assert "Abstract:" in text
        assert "https://arxiv.org/abs/2505.12345" in text

    def test_without_funnel_metadata(self, temp_config_dir, sample_arxiv_result):
        text = build_plain_text([(_paper(sample_arxiv_result), 7, "")])
        assert "1 papers selected" in text
        assert "Authors:" in text
        assert "PDF:" in text

    def test_note_and_categories(self, temp_config_dir, sample_arxiv_result):
        text = build_plain_text([(_paper(sample_arxiv_result), 8, "reason")])
        assert "Accepted at ACL 2025" in text
        assert "Categories: cs.CL, cs.AI" in text
