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

if [ -z "${OPENAI_API_KEY:-}" ] && [ ! -f "$SCRIPT_DIR/.env" ]; then
    echo "OPENAI_API_KEY is not set"
    echo "Copy .env.example to .env and fill in your API key, or export OPENAI_API_KEY."
    exit 1
fi

python "$SCRIPT_DIR/setup_wizard.py" "$@"
