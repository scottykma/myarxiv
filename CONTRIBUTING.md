# Contributing to MyArxiv

Thanks for taking the time to contribute. Bug reports, feature ideas, documentation fixes and pull requests are all welcome.

## Setup

```bash
git clone https://github.com/<your-username>/myarxiv.git
cd myarxiv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp config.example.yaml config.yaml
cp .env.example .env
```

`config.yaml` and `.env` are gitignored. Use placeholder values; never commit real keys, passwords or personal addresses.

## Before you open a pull request

```bash
pytest tests/ -v
pytest tests/ -q --cov=src --cov-report=term-missing --cov-fail-under=95
python scripts/check_privacy.py
```

All three must pass. 95% is the coverage target.

## Guidelines

- **Tests first.** New module → `tests/test_<module>.py`; new public function → at least one test. Mark tests `@pytest.mark.unit` or `@pytest.mark.integration`.
- **Mock external I/O.** arXiv, LLM, SMTP and HTTP calls must be mocked in unit tests. Patch the importing module's `get_fast`/`get_pro`, not `src.llm` directly.
- **Keep secrets out.** No API keys, SMTP passwords, personal email addresses or absolute home paths in source, tests, docs, examples or commit messages.
- **Preserve safe previews.** `preview` and `--dry-run` must never send email or mark papers as seen.
- **Review AI actions.** Config changes proposed by the LLM go through `chat/proposal.py` and require explicit user confirmation.
- **Match the style.** Python 3.11+, type hints on public signatures, `logging` rather than `print` outside the TUI, third-party/stdlib/local imports in that order.
- **Keep it configurable.** Tunables belong in `config.yaml`; do not hardcode machine-specific paths.

## Good first contributions

- Add an arXiv category or an LLM provider example.
- Improve the prefilter or scoring prompt with a test that demonstrates the change.
- Fix a documentation gap or a confusing error message.
- Add a test for an untested edge case.

## Reporting bugs

Open a GitHub issue with:

- what you expected and what happened;
- the command you ran;
- the relevant part of `last_run.json` (remove personal data first);
- your Python version and OS.

For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## License

By contributing, you agree that your contributions are licensed under the MIT License in [LICENSE](LICENSE).
