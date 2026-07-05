#!/usr/bin/env bash
# Run locally. Stateless + bring-your-own-key: enter your AI key in the browser.
# For a no-key dry run (placeholder content), prefix with FORCE_MOCK=1.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtualenv (.venv)…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q --disable-pip-version-check -r requirements.txt

echo "→ Open http://localhost:${PORT:-8000}  (enter your Anthropic / OpenAI / Gemini key in the page)"
exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
