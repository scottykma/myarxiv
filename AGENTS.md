# AGENTS.md

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime + test dependencies
cp config.example.yaml config.yaml
cp .env.example .env                  # fill in local secrets
```

All commands below assume the venv is active.

## Run Tests

```bash
pytest tests/ -v                          # all tests
pytest tests/ -v -m unit                  # skip integration
pytest tests/ --cov=src --cov-fail-under=95
python scripts/check_privacy.py           # secrets / personal data scan
```

### Coverage

- **95%+ line coverage** mandatory across all of `src/`.
- New module → new `tests/test_<module>.py`.
- New public function → at least one test.
- All tests must pass before push.

### Test Structure

- One test class per feature: `Test<Feature>` with `@pytest.mark.unit` or `@pytest.mark.integration`.
- Shared fixtures in `tests/conftest.py` (`temp_config_dir`, `mock_env`, `sample_arxiv_result`).
- External I/O (arXiv, LLM, SMTP, HTTP) always mocked in unit tests.
- Integration tests mock sub-module boundaries, verify pipeline orchestration.

## Common Commands

```bash
python setup_wizard.py        # setup wizard (reads profile.scholar_url from config.yaml)
python update.py              # conversational interest management (TUI)
python update.py list         # scriptable interest management (also add/rm/set/preview/stats/diff/undo)
python update.py set weight "video generation" 3
python -m src.main            # manual daily run (needs OPENAI_API_KEY + SMTP_PASSWORD)
python -m src.main --dry-run  # build daily_report.html without email or seen updates
```

## Architecture

```
setup_wizard.py              Google Scholar → profile fetcher → interest generator → config.yaml
update.py                    CLI / TUI → config.yaml (atomic save + backup)
src/
├── config.py              # YAML read/write (atomic save, backup, undo), env var helpers
├── interests.py           # keyword/category validation and merge helpers
├── keywords.py            # phrase/token matching (stopwords, plurals, boundaries)
├── cli.py                 # update.py subcommands
├── llm.py                 # LLMClient (OpenAI-compatible), get_fast/get_pro singletons
├── main.py                # daily pipeline entrypoint (+ --dry-run)
├── report.py              # HTML + plain-text digest rendering
├── chat/
│   ├── engine.py          # conversation agent (system prompt + streaming + actions)
│   ├── proposal.py        # reviewable config diff/apply
│   ├── screen.py          # ANSI fallback renderer
│   ├── ui.py              # rich tables, markdown, diff rendering
│   └── terminal.py        # prompt-toolkit/rich TUI + plain fallback
├── pipeline/
│   ├── fetcher.py         # arXiv API + ArxivPaper + file cache (.cache/)
│   ├── filter.py          # phrase-aware keyword_prefilter + chat_final_score (LLM)
│   ├── preview.py         # preview/stats without email or seen changes
│   ├── summarizer.py      # LLM paper summarizer (standby, not used in daily run)
│   └── notifier.py        # Gmail SMTP email push
└── profile/
    ├── fetcher.py          # Semantic Scholar + Google Scholar profile fetching
    └── generator.py        # LLM interest keyword generation
```

### Pipeline Flow

```
fetch_daily_papers()         arXiv + .cache/ file cache (same-day reuse)
    ↓ 去重 seen_papers.json (canonical IDs, version suffix stripped)
keyword_prefilter()          phrase/coverage scoring; strict exclude → top 60
    ↓
chat_final_score()           LLM, batch=30, temp=0.0, 5-level calibration anchors
    ↓                          score ≥ min_relevance_score, top max_papers
build_report()               Python → responsive HTML + plain-text alternative
    ↓
send_email()                 Gmail SMTP / SMTP_SSL
    ↓ only on success
save_seen_ids()              mark delivered papers seen
    ↓
last_run.json                fetch/filter/select stats + per-keyword hits
```

### TUI and CLI

- `python update.py` (no args) opens the TUI; `src/cli.py` handles `list/add/rm/set/preview/stats/diff/undo`.
- `src/interests.py` owns keyword/category/score/weight validation; `src/keywords.py` owns phrase matching.
- `preview` and `--dry-run` must never send email or mark papers seen. `preview --llm` may call the LLM but still must not send/mark.
- AI-generated actions are shown as a proposal diff in `chat/proposal.py` and require apply/edit/reject confirmation.
- Rich mode uses `prompt-toolkit` + `rich` (`chat/ui.py`); non-TTY mode falls back to `Screen` and plain input.
- `Screen` class (`chat/screen.py`) manages incremental ANSI rendering — no `_clear_screen()`.
  - `render_header()` prints config once (no-op on subsequent calls).
  - `show_thinking()` / `hide_thinking()` display/dismiss "Thinking..." indicator.
  - `write()` / `writeln()` stream tokens incrementally.
  - `show_actions()` prints action results with icons.
  - `show_config_status()` prints compact status bar after config changes.
- `_stream_ai_response()` supports rich console/session or plain screen; reasoning content is suppressed.
- `httpx` logger set to `WARNING` in all entry points (`main.py`, `setup_wizard.py`, `update.py`).

### Config

- `config.yaml` is **gitignored and untracked**; `config.example.yaml` is the tracked template. `.env` is also gitignored.
- Read: `config.get("path.to.key", default)`, write: `config.set(...)` then `config.save()`.
- `config.py` caches YAML. Call `reload()` before fresh pipeline runs (`main.py` does this).
- All tunables (LLM models, temperatures, batch sizes, keyword weights, paths, SMTP) are in `config.yaml`.
- The public repository does not include GitHub Actions workflows; run the pipeline locally or from your own scheduler.
- `seen_papers.json` is local runtime state, not source; do not commit it.

## Environment Variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | `src/llm.py` (all LLM calls; name is configurable via `llm.api_key_env`) |
| `SMTP_PASSWORD` | `src/pipeline/notifier.py` (read at send time via `config.get_env`) |

Entry points (`main.py`, `update.py`, `setup_wizard.py`) call `load_dotenv()`. No module-level API key constants.

## Testing Gotchas

- `LLMClient` reads the key named by `llm.api_key_env` at init. `mock_env` fixture sets `OPENAI_API_KEY`.
- `get_fast()` / `get_pro()` return **cached singletons**. Reset `src.llm._fast_instance = None` before tests that mock them.
- Mock LLM clients by patching the **importing module's** `get_fast`/`get_pro` (e.g. `monkeypatch.setattr("src.pipeline.filter.get_fast", lambda: mock)`), not `src.llm.get_fast` directly.
- The `parse_response_stream` and `_parse_stream` functions in `chat/engine.py` are often mocked directly in tui tests rather than mocking the LLM client.
- `sample_arxiv_result` creates author mocks with explicit `.name = "..."` (not `MagicMock(name=...)`), since `MagicMock.name` returns a MagicMock.
- Profile fetcher tests must mock `requests.get` (Semantic Scholar) and `_fetch_from_google_scholar`.

## Development Workflow

### Branches and releases

- `main` is the public release branch for `scottykma/myarxiv`; keep it releasable.
- Create short-lived branches (`feat/...`, `fix/...`, `docs/...`) from `main`; open a PR back to `main`.
- `public-release` is the local publishing branch; before release it must match `public/main`.
- The private deployment repository is separate. Never push its branches or history to `public`.
- Do not add `.github/workflows` to the public repository; it intentionally has no GitHub Actions. Run checks locally. If private automation is needed, keep it in the private repository.

### Commits

- Use Conventional Commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- One logical change per commit.
- Never commit secrets, `config.yaml`, `.env`, `seen_papers.json`, caches, generated reports or personal data.
- Update tests, README and `demo/` together with user-facing changes.

### Definition of done

Run before every push or pull request:

```bash
pytest tests/ -v
pytest tests/ -q --cov=src --cov-fail-under=95
python scripts/check_privacy.py
git diff --check
```

- 95%+ branch + line coverage; new module → new test file; new public function → test.
- Mock external I/O (arXiv, LLM, SMTP, HTTP); no network in unit tests.
- Keep `preview` and `--dry-run` free of email/seen side effects.
- Add a regression test for every bug fix.
- If report rendering changes, regenerate/check `demo/report.html`, `demo/report.txt` and `demo/report.png`.

### Config, dependencies and compatibility

- All tunables belong in `config.yaml` and must be reflected in `config.example.yaml`; read with `config.get`.
- Secrets come from `.env` or the environment only; read them at call time, never at import time.
- Runtime dependencies go in `requirements.txt`; test/dev dependencies in `requirements-dev.txt`.
- Preserve CLI flags, config keys and JSON output fields unless a deprecation is documented.

### Public/private boundary

- Public: `main` in `scottykma/myarxiv`, placeholders only, no `.github/`, no secrets.
- Private: local `config.yaml`/`.env` and any deployment automation; never force-push private branches to `public`.
- Before releasing, run `git remote -v` and `python scripts/check_privacy.py`; publish from a clean root commit.

## Development Style

- Python 3.11+, type hints on public function signatures.
- `logger = logging.getLogger(__name__)`, never `print` (except TUI which uses `print`/`input` by design).
- Third-party imports first, then stdlib, then local `src.*` imports (blank line between groups).
- No comments in source code. Self-documenting names.
- Functions over classes (exceptions: `ArxivPaper`, `ScholarProfile`, `LLMClient`).

## Security

- `config.yaml`, `.env`, `seen_papers.json` and generated reports must stay untracked.
- API keys via environment variables only, never in source or config.
- No hardcoded local paths; all paths configurable in `config.yaml` under `paths.*`.
- `scripts/check_privacy.py` must stay green before publishing.
- Publish from a **fresh history**; never push a history that contains local configuration or personal data to a public remote.
