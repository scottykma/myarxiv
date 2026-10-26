#!/usr/bin/env python3
"""Fail if tracked files look like they contain secrets or personal data."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_TRACKED = {
    ".env",
    "config.yaml",
    "config.yaml.bak",
    "config.yaml.tmp",
    "seen_papers.json",
    "last_run.json",
    "daily_report.html",
    "daily_report.txt",
    ".coverage",
}

ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.net",
    "example.org",
    "users.noreply.github.com",
}

SECRET_PATTERNS = {
    "openai/deepseek key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    "github token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"),
    "aws access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
}

EMAIL_PATTERN = re.compile(r"(?<![\w.+-])([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
HOME_PATH_PATTERN = re.compile(r"(?:/Users/|/home/)[A-Za-z0-9._-]+|C:\\Users\\[^\\\s]+")

TEXT_SUFFIXES = {
    ".md", ".py", ".sh", ".yml", ".yaml", ".toml", ".txt", ".html", ".json", ".cfg", ".ini",
}


def tracked_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(
            path for path in ROOT.rglob("*")
            if path.is_file() and ".git" not in path.parts and ".venv" not in path.parts
        )
    return [ROOT / name for name in result.stdout.split("\0") if name]


def check_tracked_paths(paths: list[Path]) -> list[str]:
    problems = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if relative in FORBIDDEN_TRACKED:
            problems.append(f"{relative}: must not be tracked (local secret or runtime state)")
    return problems


def scan_line(relative: str, number: int, line: str) -> list[str]:
    problems = []

    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(line):
            problems.append(f"{relative}:{number}: possible {label}")

    for match in EMAIL_PATTERN.finditer(line):
        domain = match.group(2).lower()
        if domain not in ALLOWED_EMAIL_DOMAINS:
            problems.append(f"{relative}:{number}: personal email (domain: {domain})")

    if HOME_PATH_PATTERN.search(line):
        problems.append(f"{relative}:{number}: absolute home path")

    return problems


def main() -> int:
    paths = tracked_files()
    if not paths:
        print("No tracked files found; nothing to scan.")
        return 0

    problems = check_tracked_paths(paths)
    scanned = 0

    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        relative = path.relative_to(ROOT).as_posix()
        for number, line in enumerate(text.splitlines(), 1):
            problems.extend(scan_line(relative, number, line))

    print(f"Scanned {scanned} tracked text files.")

    if problems:
        print(f"\nFound {len(problems)} potential privacy or secret issue(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print(
            "\nRemove the data, or add a justified allowlist entry to "
            "scripts/check_privacy.py if it is a placeholder.",
            file=sys.stderr,
        )
        return 1

    print("No secrets, personal emails, home paths, or forbidden tracked files found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
