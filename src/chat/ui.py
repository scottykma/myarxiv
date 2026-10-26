from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from src.config import get


def status_text() -> str:
    include = get("interests.keywords_include", [])
    exclude = get("interests.keywords_exclude", [])
    categories = get("interests.categories", [])
    return (
        f" keywords {len(include)} · exclude {len(exclude)} · "
        f"{', '.join(categories) if categories else 'no categories'} · "
        f"max {get('daily.max_papers', 20)} · min {get('daily.min_relevance_score', 5)} "
        f"| /help · Ctrl-D exit "
    )


def render_header(console: Console) -> None:
    include = list(get("interests.keywords_include", []))
    exclude = list(get("interests.keywords_exclude", []))
    weights = dict(get("interests.keyword_weights", {}) or {})
    categories = list(get("interests.categories", []))

    table = Table.grid(padding=(0, 2))
    table.add_column(style="cyan", no_wrap=True)
    table.add_column()
    table.add_row("Keywords", f"{len(include)} · " + (", ".join(include) if include else "(none)"))
    table.add_row("Exclude", f"{len(exclude)} · " + (", ".join(exclude) if exclude else "(none)"))
    table.add_row("Weights", ", ".join(f"{k}×{v}" for k, v in weights.items() if v != 1) or "(default 1)")
    table.add_row("Categories", ", ".join(categories) if categories else "(none)")
    table.add_row(
        "Daily",
        f"max {get('daily.max_papers', 20)} · min score {get('daily.min_relevance_score', 5)}",
    )
    console.print(Panel(table, title="MyArxiv · Interest Manager", border_style="cyan"))


def render_history(console: Console, messages: list[dict]) -> None:
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if role == "user":
            console.print(Text.assemble(("> ", "green"), (content, "default")))
        elif role == "assistant" and content:
            console.print(Markdown(content))


def keyword_tables(stats: dict[str, int] | None = None) -> Group:
    include = list(get("interests.keywords_include", []))
    exclude = list(get("interests.keywords_exclude", []))
    weights = dict(get("interests.keyword_weights", {}) or {})
    tables = [
        _keyword_table("Include", include, weights, stats),
        _keyword_table("Exclude", exclude, {}, None),
    ]
    return Group(*tables)


def _keyword_table(
    title: str,
    keywords: list[str],
    weights: dict[str, int],
    stats: dict[str, int] | None,
) -> Table:
    table = Table(title=f"{title} ({len(keywords)})", title_justify="left", header_style="bold cyan")
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Keyword", overflow="fold")
    table.add_column("Weight", justify="center", width=6)
    if stats is not None:
        table.add_column("Hits", justify="right", width=5)
    for index, keyword in enumerate(keywords, 1):
        row = [str(index), Text(keyword), str(weights.get(keyword, 1))]
        if stats is not None:
            row.append(str(stats.get(keyword, 0)))
        table.add_row(*row)
    return table


def preview_table(result: dict) -> Table:
    weights = result.get("keyword_weights", {})
    table = Table(
        title=f"Candidates · fetched {result['fetched']} · showing {len(result['candidates'])}",
        title_justify="left",
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Score", justify="right", width=5)
    table.add_column("Title", overflow="fold", ratio=3)
    table.add_column("Matched keywords", overflow="fold", ratio=2)
    for index, row in enumerate(result["candidates"], 1):
        title = row["paper"].title
        if len(title) > 90:
            title = title[:89] + "…"
        matched = ", ".join(
            f"{keyword}×{weights[keyword]}" if weights.get(keyword, 1) != 1 else keyword
            for keyword in row["keywords"]
        ) or "-"
        table.add_row(str(index), str(row["score"]), Text(title), Text(matched))
    return table


def excluded_table(result: dict) -> Table:
    table = Table(title=f"Excluded by keyword ({len(result['excluded'])})", title_justify="left")
    table.add_column("Keyword", style="red")
    table.add_column("Title", overflow="fold")
    for item in result["excluded"]:
        table.add_row(Text(item["keyword"]), Text(item["paper"].title))
    return table


def llm_table(result: dict) -> Table:
    table = Table(title="LLM selection", title_justify="left", header_style="bold cyan")
    table.add_column("Score", justify="right", width=5)
    table.add_column("Title", overflow="fold", ratio=3)
    table.add_column("Reason", overflow="fold", ratio=2)
    for paper, score, reason in result.get("llm_results", []):
        table.add_row(str(score), Text(paper.title), Text(reason))
    return table


def stats_table(stats: dict[str, int], weights: dict[str, int] | None = None) -> Table:
    weights = weights or {}
    table = Table(title="Keyword hits", title_justify="left", header_style="bold cyan")
    table.add_column("Hits", justify="right", width=5)
    table.add_column("Weight", justify="center", width=6)
    table.add_column("Keyword", overflow="fold")
    for keyword, count in sorted(stats.items(), key=lambda item: (-item[1], item[0])):
        table.add_row(str(count), str(weights.get(keyword, 1)), Text(keyword))
    return table


def help_table() -> Table:
    table = Table(title="Slash commands", title_justify="left", header_style="bold cyan")
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Description")
    for command, description in [
        ("/add k1, k2", "Add include keywords"),
        ("/rm k1, k2", "Remove include keywords"),
        ("/exclude k1, k2", "Add exclude keywords"),
        ("/unexclude k1, k2", "Remove exclude keywords"),
        ("/cats c1, c2", "Set arXiv categories"),
        ("/score N", "Set min relevance score (1-10)"),
        ("/max N", "Set max papers/day (1-50)"),
        ("/weight term N", "Set keyword weight (1-5)"),
        ("/list", "Show keyword table"),
        ("/preview [days] [llm]", "Preview candidates; add llm for full scoring"),
        ("/stats [days]", "Show per-keyword hit counts"),
        ("/diff", "Diff the previous saved config"),
        ("/undo", "Restore the previous saved config"),
        ("/show", "Display current config"),
        ("/help", "Show this help"),
        ("/quit, exit, q", "Exit"),
    ]:
        table.add_row(command, description)
    return table


def print_markdown(console: Console, text: str) -> None:
    if text.strip():
        console.print(Markdown(text))


def proposal_panel(text: str) -> Panel:
    return Panel(Text(text), title="Proposed changes", border_style="yellow", title_align="left")


def diff_syntax(text: str) -> Syntax:
    return Syntax(text, "diff", theme="ansi_dark", line_numbers=False)


def error_panel(text: str) -> Panel:
    return Panel(Text(text), title="Error", border_style="red", title_align="left")
