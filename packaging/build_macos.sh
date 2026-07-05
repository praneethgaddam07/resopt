#!/usr/bin/env bash
# Build the macOS desktop app (RESOPT.app) with PyInstaller. Run on a Mac.
#   bash packaging/build_macos.sh   ->   dist/RESOPT.app
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m venv .build-venv
# shellcheck disable=SC1091
source .build-venv/bin/activate
pip install -q --disable-pip-version-check -r requirements-desktop.txt Pillow

python packaging/make_icon.py || true

rm -rf build dist
pyinstaller --noconfirm --windowed --name "RESOPT" \
  --icon packaging/assets/icon.icns \
  --add-data "app/static:app/static" \
  --add-data "app/workflow/master_taxonomy.json:app/workflow" \
  --collect-all uvicorn \
  --collect-all anthropic \
  --collect-all openai \
  --collect-all google.generativeai \
  --collect-all webview \
  --collect-submodules app \
  desktop.py

echo
echo "✅ Built: dist/RESOPT.app"
echo "   Test it:  open 'dist/RESOPT.app'"
