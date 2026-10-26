#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
else
    echo "Virtual environment not found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

if [ -z "${OPENAI_API_KEY:-}" ] && [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    export OPENAI_API_KEY="$DEEPSEEK_API_KEY"
fi

python -m src.main "$@"
