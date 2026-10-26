import html
import textwrap
from datetime import datetime

from src.config import get
from src.pipeline.fetcher import ArxivPaper


def _score_color(score: int, theme: str = "light") -> str:
    if theme == "dark":
        if score >= get("report.score_green", 8):
            return "#7FB08A"
        if score >= get("report.score_orange", 5):
            return "#E0A458"
        return "#E07A7A"
    if score >= get("report.score_green", 8):
        return "#3F6B4A"
    if score >= get("report.score_orange", 5):
        return "#B7791F"
    return "#9B2C2C"


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _authors(paper: ArxivPaper) -> str:
    authors = [str(author) for author in getattr(paper, "authors", []) if author]
    if not authors:
        return "Unknown authors"
    if len(authors) > 5:
        return ", ".join(authors[:5]) + " et al."
    return ", ".join(authors)


def _published(paper: ArxivPaper) -> str:
    published = getattr(paper, "published", None)
    if isinstance(published, datetime):
        return published.strftime("%b %d, %Y")
    return ""


def _tags(categories: list[str]) -> str:
    return "".join(f'<span class="tag">{_esc(category)}</span>' for category in categories)


def _css_light() -> str:
    return (
        "body{margin:0;padding:0;background:#F6F1E7;color:#211A16;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"
        "-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}"
        "table{border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt}"
        "img{border:0;height:auto;line-height:100%;outline:none;text-decoration:none}"
        ".wrapper{width:100%;background:#F6F1E7;padding:24px 12px}"
        ".container{width:100%;max-width:680px;margin:0 auto}"
        ".preheader{display:none!important;visibility:hidden;mso-hide:all;font-size:1px;"
        "line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden}"
        ".header{background:#211A16;border-radius:18px 18px 0 0;padding:28px 28px 24px;color:#FDF8EF}"
        ".brand{font-size:10px;letter-spacing:2.4px;text-transform:uppercase;color:#D9A38F;font-weight:700}"
        ".header h1{margin:8px 0 6px;font-family:Georgia,'Times New Roman',serif;"
        "font-size:27px;line-height:1.25;font-weight:700;color:#FDF8EF;letter-spacing:-0.2px}"
        ".header-meta{font-size:13px;color:#D8CBB9;line-height:1.6}"
        ".header-chips{margin-top:14px;font-size:11px;color:#E8DCCB}"
        ".header-chips span{display:inline-block;padding:4px 9px;margin-right:5px;"
        "border:1px solid rgba(253,248,239,.30);border-radius:999px}"
        ".summary{background:#FFFDF8;border-left:1px solid #E5DCCB;border-right:1px solid #E5DCCB;"
        "padding:14px 28px;border-bottom:1px solid #E5DCCB}"
        ".summary td{font-size:12px;color:#6B6257;line-height:1.5}"
        ".summary strong{color:#211A16;font-size:13px}"
        ".card-wrap{padding:16px 0 0}"
        ".card{width:100%;background:#FFFDF8;border:1px solid #E5DCCB;border-radius:14px;overflow:hidden}"
        ".card-body{padding:22px 24px 20px}"
        ".rank{font-size:11px;letter-spacing:1.4px;color:#8A7F72;font-weight:700}"
        ".score{display:inline-block;padding:4px 10px;border-radius:999px;color:#FFFFFF;"
        "font-size:11px;font-weight:700;letter-spacing:.3px}"
        ".paper-title{margin:8px 0 5px;font-family:Georgia,'Times New Roman',serif;"
        "font-size:18px;line-height:1.4;color:#211A16;font-weight:700}"
        ".paper-title a{color:#211A16;text-decoration:none}"
        ".authors{font-size:12px;color:#6B6257;line-height:1.6}"
        ".reason{margin:14px 0 0;padding:12px 14px;background:#FBF3E4;border-left:3px solid #B5451F;"
        "border-radius:0 8px 8px 0;font-size:13px;line-height:1.65;color:#4A3F35}"
        ".reason-label{display:block;margin-bottom:4px;font-size:10px;letter-spacing:1.2px;"
        "text-transform:uppercase;color:#B5451F;font-weight:700}"
        ".abstract{margin:14px 0 0;font-size:13px;line-height:1.7;color:#5B5146}"
        ".abstract-label{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;"
        "color:#8A7F72;font-weight:700;margin-bottom:4px}"
        ".meta{margin:14px 0 0;font-size:11px;color:#8A7F72;line-height:1.8}"
        ".tag{display:inline-block;padding:2px 7px;margin-right:4px;border-radius:999px;"
        "background:#F1E6D4;color:#7A3B22;font-size:10px;font-weight:600}"
        ".actions{margin:16px 0 0}"
        ".button{display:inline-block;padding:9px 14px;border-radius:8px;background:#B5451F;"
        "color:#FFFFFF!important;font-size:12px;font-weight:700;text-decoration:none;margin-right:6px}"
        ".button-secondary{background:#EFE6D6;color:#3F3A33!important}"
        ".footer{padding:20px 8px 8px;text-align:center;color:#8A7F72;font-size:11px;line-height:1.7}"
        ".footer a{color:#6B6257;text-decoration:none}"
        "@media(max-width:600px){"
        ".wrapper{padding:10px 6px}"
        ".header{padding:22px 18px 18px;border-radius:12px 12px 0 0}"
        ".header h1{font-size:22px}"
        ".summary{padding:12px 18px}"
        ".card-body{padding:18px 18px 16px}"
        ".paper-title{font-size:16px}"
        ".reason,.abstract{font-size:12px}"
        ".button{padding:8px 11px;font-size:11px}"
        "}"
        "@media(prefers-color-scheme:dark){"
        "body,.wrapper{background:#171310!important}"
        ".summary,.card{background:#211C18!important;border-color:#3A3029!important}"
        ".paper-title,.paper-title a,.summary strong{color:#F5EFE4!important}"
        ".authors,.summary td,.meta{color:#B8A995!important}"
        ".reason{background:#2A211B!important;color:#E8DCCB!important;border-left-color:#D97757!important}"
        ".abstract{color:#E8DCCB!important}"
        ".footer{color:#8A7F72!important}"
        "}"
    )


def _css_dark() -> str:
    return (
        "body{margin:0;padding:0;background:#0E0D0C;color:#F3EDE3;color-scheme:dark;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;"
        "-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}"
        "table{border-collapse:collapse;mso-table-lspace:0pt;mso-table-rspace:0pt}"
        "img{border:0;height:auto;line-height:100%;outline:none;text-decoration:none}"
        ".wrapper{width:100%;background:#0E0D0C;padding:24px 12px}"
        ".container{width:100%;max-width:680px;margin:0 auto}"
        ".preheader{display:none!important;visibility:hidden;mso-hide:all;font-size:1px;"
        "line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden}"
        ".header{background:#151311;border:1px solid #2E2822;border-bottom:0;"
        "border-radius:18px 18px 0 0;padding:28px 28px 24px;color:#F7F0E6}"
        ".brand{font-size:10px;letter-spacing:2.4px;text-transform:uppercase;color:#E0A58C;font-weight:700}"
        ".header h1{margin:8px 0 6px;font-family:Georgia,'Times New Roman',serif;"
        "font-size:27px;line-height:1.25;font-weight:700;color:#F7F0E6;letter-spacing:-0.2px}"
        ".header-meta{font-size:13px;color:#B8AA9A;line-height:1.6}"
        ".header-chips{margin-top:14px;font-size:11px;color:#D8C9B7}"
        ".header-chips span{display:inline-block;padding:4px 9px;margin-right:5px;"
        "border:1px solid rgba(247,240,230,.18);border-radius:999px;background:#1D1916}"
        ".summary{background:#181513;border:1px solid #2E2822;border-top:0;"
        "padding:14px 28px;border-bottom:1px solid #2E2822}"
        ".summary td{font-size:12px;color:#A89C8E;line-height:1.5}"
        ".summary strong{color:#F3EDE3;font-size:13px}"
        ".card-wrap{padding:16px 0 0}"
        ".card{width:100%;background:#181513;border:1px solid #2E2822;border-radius:14px;overflow:hidden}"
        ".card-body{padding:22px 24px 20px}"
        ".rank{font-size:11px;letter-spacing:1.4px;color:#8E8173;font-weight:700}"
        ".score{display:inline-block;padding:4px 10px;border-radius:999px;color:#12100E;"
        "font-size:11px;font-weight:800;letter-spacing:.3px}"
        ".paper-title{margin:8px 0 5px;font-family:Georgia,'Times New Roman',serif;"
        "font-size:18px;line-height:1.4;color:#F3EDE3;font-weight:700}"
        ".paper-title a{color:#F3EDE3;text-decoration:none}"
        ".authors{font-size:12px;color:#B8AA9A;line-height:1.6}"
        ".reason{margin:14px 0 0;padding:12px 14px;background:#211B17;border-left:3px solid #E07A5F;"
        "border-radius:0 8px 8px 0;font-size:13px;line-height:1.65;color:#E8DCCB}"
        ".reason-label{display:block;margin-bottom:4px;font-size:10px;letter-spacing:1.2px;"
        "text-transform:uppercase;color:#F0A58B;font-weight:700}"
        ".abstract{margin:14px 0 0;font-size:13px;line-height:1.7;color:#D8CFC4}"
        ".abstract-label{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;"
        "color:#8E8173;font-weight:700;margin-bottom:4px}"
        ".meta{margin:14px 0 0;font-size:11px;color:#8E8173;line-height:1.8}"
        ".tag{display:inline-block;padding:2px 7px;margin-right:4px;border-radius:999px;"
        "background:#2A2420;color:#F0C9A8;font-size:10px;font-weight:600}"
        ".actions{margin:16px 0 0}"
        ".button{display:inline-block;padding:9px 14px;border-radius:8px;background:#C65D43;"
        "color:#FFF8F0!important;font-size:12px;font-weight:700;text-decoration:none;margin-right:6px}"
        ".button-secondary{background:#2A2420;color:#E8DCCB!important}"
        ".footer{padding:20px 8px 8px;text-align:center;color:#8E8173;font-size:11px;line-height:1.7}"
        ".footer a{color:#B8AA9A;text-decoration:none}"
        "@media(max-width:600px){"
        ".wrapper{padding:10px 6px}"
        ".header{padding:22px 18px 18px;border-radius:12px 12px 0 0}"
        ".header h1{font-size:22px}"
        ".summary{padding:12px 18px}"
        ".card-body{padding:18px 18px 16px}"
        ".paper-title{font-size:16px}"
        ".reason,.abstract{font-size:12px}"
        ".button{padding:8px 11px;font-size:11px}"
        "}"
    )


def _summary_row(fetched: int | None, prefiltered: int | None, selected: int, top_score: int) -> str:
    funnel = ""
    if fetched is not None:
        funnel = f"<strong>{fetched}</strong> fetched"
        if prefiltered is not None:
            funnel += f" &rarr; <strong>{prefiltered}</strong> candidates"
        funnel += f" &rarr; <strong>{selected}</strong> selected"
    else:
        funnel = f"<strong>{selected}</strong> papers selected"
    return (
        "<table role=\"presentation\" width=\"100%\"><tr>"
        f"<td>{funnel}</td>"
        f"<td align=\"right\">Top score <strong>{top_score}/10</strong></td>"
        "</tr></table>"
    )


def build_report(
    scored: list[tuple[ArxivPaper, int, str]],
    *,
    fetched: int | None = None,
    prefiltered: int | None = None,
    theme: str = "light",
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    user_name = get("profile.name") or get("user.name", "Researcher")
    categories = list(get("interests.categories", []))
    selected = len(scored)
    css = _css_dark() if theme == "dark" else _css_light()
    color_scheme = "dark" if theme == "dark" else "light dark"
    top_score = max((score for _paper, score, _reason in scored), default=0)
    category_text = ", ".join(categories) if categories else "all categories"

    preheader = (
        f"{selected} papers selected from {fetched} fetched"
        if fetched is not None
        else f"{selected} papers selected"
    )
    if top_score:
        preheader += f" · top score {top_score}/10"

    lines = [
        "<!DOCTYPE html>",
        "<html><head><meta charset=\"utf-8\">",
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">",
        f"<meta name=\"color-scheme\" content=\"{color_scheme}\">",
        "<meta name=\"x-apple-disable-message-reformatting\">",
        "<title>MyArxiv · arXiv Digest</title>",
        f"<style>{css}</style></head>",
        "<body>",
        f"<div class=\"preheader\">{_esc(preheader)}</div>",
        "<table role=\"presentation\" width=\"100%\" class=\"wrapper\"><tr><td align=\"center\">",
        "<table role=\"presentation\" width=\"100%\" class=\"container\">",
        "<tr><td class=\"header\">",
        "<div class=\"brand\">MyArxiv</div>",
        "<h1>Daily arXiv Digest</h1>",
        f"<div class=\"header-meta\">{today} &middot; {_esc(user_name)}</div>",
        "<div class=\"header-chips\">",
        f"<span>{selected} papers</span><span>{_esc(category_text)}</span>",
        f"<span>Top {top_score}/10</span>",
        "</div></td></tr>",
        f"<tr><td class=\"summary\">{_summary_row(fetched, prefiltered, selected, top_score)}</td></tr>",
        "<tr><td>",
        "<table role=\"presentation\" width=\"100%\">",
    ]

    for index, (paper, score, reason) in enumerate(scored, 1):
        url = _esc(getattr(paper, "url", ""))
        pdf_url = getattr(paper, "pdf_url", "")
        published = _published(paper)
        authors = _authors(paper)
        comment = getattr(paper, "comment", "")
        paper_categories = list(getattr(paper, "categories", []))

        meta_parts = []
        if published:
            meta_parts.append(_esc(published))
        meta_parts.append(_tags(paper_categories))
        if comment:
            meta_parts.append(f"<span>{_esc(comment)}</span>")

        lines.extend([
            "<tr><td class=\"card-wrap\">",
            "<table role=\"presentation\" width=\"100%\" class=\"card\"><tr><td class=\"card-body\">",
            "<table role=\"presentation\" width=\"100%\"><tr>",
            f"<td class=\"rank\">PAPER {index:02d}</td>",
            f"<td align=\"right\"><span class=\"score\" style=\"background:{_score_color(score, theme)}\">{score}/10</span></td>",
            "</tr></table>",
            f"<div class=\"paper-title\"><a href=\"{url}\">{_esc(paper.title)}</a></div>",
            f"<div class=\"authors\">{_esc(authors)}</div>",
        ])
        if reason:
            lines.extend([
                "<div class=\"reason\">",
                "<span class=\"reason-label\">Why it matters</span>",
                f"{_esc(reason)}",
                "</div>",
            ])
        lines.extend([
            "<div class=\"abstract\">",
            "<div class=\"abstract-label\">Abstract</div>",
            f"{_esc(paper.abstract)}",
            "</div>",
            f"<div class=\"meta\">{' &middot; '.join(meta_parts)}</div>",
            "<div class=\"actions\">",
            f"<a class=\"button\" href=\"{url}\">Read paper</a>",
        ])
        if pdf_url:
            lines.append(f"<a class=\"button button-secondary\" href=\"{_esc(pdf_url)}\">PDF</a>")
        lines.extend([
            "</div>",
            "</td></tr></table>",
            "</td></tr>",
        ])

    lines.extend([
        "</table>",
        "</td></tr>",
        "<tr><td class=\"footer\">",
        f"Generated by <strong>MyArxiv</strong> &middot; {today}<br>",
        f"{_esc(category_text)} &middot; {selected} papers",
        "</td></tr>",
        "</table>",
        "</td></tr></table>",
        "</body></html>",
    ])
    return "\n".join(lines)


def build_plain_text(
    scored: list[tuple[ArxivPaper, int, str]],
    *,
    fetched: int | None = None,
    prefiltered: int | None = None,
) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    categories = ", ".join(get("interests.categories", [])) or "all categories"
    lines = [
        "MyArxiv — Your arXiv Digest",
        f"{today} · {categories}",
    ]
    if fetched is not None:
        summary = f"{fetched} fetched"
        if prefiltered is not None:
            summary += f" → {prefiltered} candidates"
        summary += f" → {len(scored)} selected"
        lines.append(summary)
    else:
        lines.append(f"{len(scored)} papers selected")

    for index, (paper, score, reason) in enumerate(scored, 1):
        lines.extend([
            "",
            f"{index}. [{score}/10] {paper.title}",
            f"   Authors: {_authors(paper)}",
        ])
        published = _published(paper)
        if published:
            lines.append(f"   Published: {published}")
        if reason:
            lines.append(f"   Why it matters: {reason}")
        if getattr(paper, "categories", []):
            lines.append(f"   Categories: {', '.join(paper.categories)}")
        if getattr(paper, "comment", ""):
            lines.append(f"   Note: {paper.comment}")
        lines.append(f"   arXiv: {getattr(paper, 'url', '')}")
        if getattr(paper, "pdf_url", ""):
            lines.append(f"   PDF: {paper.pdf_url}")
        lines.append("   Abstract:")
        lines.append(textwrap.fill(paper.abstract, width=96, initial_indent="     ", subsequent_indent="     "))

    lines.extend([
        "",
        "—",
        f"Generated by MyArxiv · {today}",
    ])
    return "\n".join(lines)
