# Developer Guide

## Architecture

```text
setup_wizard.py     Google Scholar → profile fetcher → interest generator → config.yaml
update.py           CLI / TUI → interests.py validation → config.yaml (atomic save + backup)
src/main.py         daily pipeline → report → email → seen_papers.json
```

```text
update.py (no args)              update.py <command>
        │                                │
        ▼                                ▼
src/chat/engine.py                src/cli.py
  LLM conversation                  list/add/rm/set/preview/stats/diff/undo
  execute_action()                  interests.py + keywords.py
        └──────────────┬─────────────────┘
                       ▼
                 src/config.py
```

## Module roles

| Module | Responsibility |
|---|---|
| `config.py` | YAML load/get/set, atomic save, one-step backup/undo, env access |
| `interests.py` | keyword merge/remove, case-insensitive dedupe, category/score/max validation |
| `keywords.py` | phrase/token matching with stopwords, plural variants, word boundaries |
| `cli.py` | `update.py` subcommands; preview and diff/undo |
| `llm.py` | `LLMClient` (DeepSeek/OpenAI-compatible), `get_fast`/`get_pro` singletons |
| `main.py` | daily pipeline, seen cache, `--dry-run`, `last_run.json` |
| `report.py` | responsive HTML digest + plain-text alternative |
| `chat/engine.py` | conversation prompt, streaming parse, validated actions |
| `chat/proposal.py` | reviewable action diff, proposed config, apply |
| `chat/ui.py` | rich tables, markdown, diff rendering |
| `chat/terminal.py` | prompt-toolkit/rich TUI with plain fallback |
| `pipeline/fetcher.py` | arXiv query, `ArxivPaper`, same-day cache, canonical IDs |
| `pipeline/filter.py` | phrase-aware keyword prefilter + LLM batch scoring |
| `pipeline/preview.py` | preview/stats without email or seen updates |
| `pipeline/notifier.py` | SMTP (STARTTLS or SSL) |
| `profile/fetcher.py` | Semantic Scholar + Google Scholar profile fetching |
| `profile/generator.py` | LLM initial interest generation |

## Daily run flow

```text
fetch_daily_papers()
    │  no cache on error/empty; raises if the API fails before any result
    ▼
load_seen_ids()                    canonical IDs (v1/v2 collapse)
    │
    ▼
keyword_prefilter()                exclude titles; score title/abstract coverage → top N
    │
    ▼
chat_final_score()                 LLM batches; missing/invalid indices retried per paper
    │                          keep score ≥ min_relevance_score, top max_papers
    ▼
build_report()                     escaped HTML + plain text
    │
    ▼
send_report()
    │ success only
    ▼
save_seen_ids(filtered)            only delivered papers are marked seen
    ▼
last_run.json                      counts + per-keyword hits
```

Use `python -m src.main --dry-run` to write `daily_report.html` without email or seen changes.

## Interest update flow

- `python update.py` opens the rich TUI; it still uses the LLM conversation for natural language.
- AI actions are converted to a proposal (`chat/proposal.py`) and require `[a]pply / [e]dit / [r]eject`; they never execute silently.
- `python update.py add/rm/set/...` is the scriptable path and needs no LLM.
- `execute_action()` validates before writing, saves immediately, and creates `config.yaml.bak`.
- `python update.py undo` restores the previous saved version; `diff` shows the last change.
- `preview` runs the prefilter against fetched papers and prints matched keywords. It never sends email or marks papers seen; `--llm` additionally runs full scoring.
- Keyword weights live in `interests.keyword_weights` (1–5) and multiply prefilter contributions.

## Testing

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
pytest tests/ -v -m unit
pytest tests/ --cov=src --cov-fail-under=95
python scripts/check_privacy.py
```

Current: 504 tests, 96% branch + line coverage (95% project target).

```text
tests/
├── conftest.py              # temp_config_dir, mock_env, sample_arxiv_result
├── test_keywords.py         # phrase/token matching
├── test_interests.py        # merge/validation
├── test_cli.py              # subcommands
├── test_preview.py          # preview/format/stats
├── test_config.py           # atomic save, backup, undo
├── test_arxiv_fetcher.py    # fetch/cache/error/canonical IDs
├── test_paper_filter.py     # prefilter, batch parsing, fallbacks
├── test_main.py             # report, seen cache, dry-run, stats
└── ...
```

External I/O (arXiv, LLM, SMTP, HTTP) is always mocked in unit tests. Mock the importing module's `get_fast`/`get_pro`, not `src.llm` directly.

## Configuration and secrets

- `config.yaml` is gitignored and untracked. `config.example.yaml` is the tracked template.
- Secrets come from `.env` locally or from environment variables; do not commit them.
- The public repository does not include GitHub Actions workflows. Run the pipeline locally or from your own scheduler.
- `notification.email.to` is the recipient; `user.email` is the authenticated SMTP sender.
- `paths.seen_papers`, `paths.cache_dir`, `paths.last_run`, `paths.report`, `paths.readline_history` are configurable.
- `seen_papers.json` is local runtime state; do not commit it.
- `config.yaml.bak`, `last_run.json`, `daily_report.html`, `.cache/`, `.env` are gitignored.
- `prompt-toolkit` and `rich` are required for the rich TUI; non-TTY runs fall back to plain input/output.
- `SMTP_PASSWORD` is read when an email is sent, not at import time.

## Publishing a public release

Publish from a fresh snapshot. Do not push a history that contains local configuration or personal data.

```bash
git checkout --orphan public-release
git add -A
git -c user.name="MyArxiv contributors" \
    -c user.email="dailypapers@users.noreply.github.com" \
    commit -m "Initial public release"
git remote add public https://github.com/<owner>/myarxiv.git
git push public public-release:main
```

Before pushing:

```bash
python scripts/check_privacy.py
git ls-files | grep -E '^(config\.yaml|\.env|seen_papers\.json)$' && echo "unexpected tracked file"
```

The check must report no secrets, personal emails, home paths or forbidden tracked files. Also confirm the remote is the intended public repository.

## Code conventions

- Python 3.11+, type hints on public signatures.
- `logger = logging.getLogger(__name__)`; TUI/CLI may print by design.
- Third-party imports first, then stdlib, then local `src.*`.
- No comments in source; self-documenting names.
- Functions over classes except data/config helpers.
- Keep `preview` and `--dry-run` side-effect free.
- Never add a module-level secret snapshot.
