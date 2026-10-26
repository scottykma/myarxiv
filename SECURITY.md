# Security Policy

## Supported versions

The `main` branch receives security fixes. Tagged releases are supported on a best-effort basis.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Describe the issue, the affected version or commit, and reproduction steps.

Do not open a public issue for a suspected vulnerability, and do not include real API keys, SMTP passwords or personal email addresses in reports, logs or screenshots.

## Scope

In scope:

- Leakage of secrets or personal data through source, configuration, logs, generated reports or local automation.
- HTML injection in the email report or terminal output.
- Unintended email delivery, or `preview`/`--dry-run` changing state.
- Unsafe handling of untrusted LLM output or external HTTP responses.

Out of scope:

- Vulnerabilities in arXiv, Gmail, the LLM provider or other third-party services.
- Costs incurred by using your own API key.
- Social-engineering attacks that require access to your machine or GitHub account.

## If a secret leaks

1. Revoke and rotate the key or app password immediately.
2. Remove it from the working tree and, if it was committed, from Git history before publishing.
3. Run `python scripts/check_privacy.py` and review `git log -p` for the affected path.

The project deliberately keeps `config.yaml`, `.env` and `seen_papers.json` out of version control; please keep it that way.
