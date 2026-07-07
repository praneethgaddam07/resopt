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
  --collect-all sentence_transformers \
  --collect-all transformers \
  --collect-all huggingface_hub \
  --collect-all tokenizers \
  --collect-all tqdm \
  --collect-all safetensors \
  --collect-all regex \
  --collect-all pypdf \
  --collect-all docx \
  --collect-all numpy \
  --collect-all scipy \
  --collect-all sklearn \
  --collect-all torch \
  --copy-metadata packaging \
  --copy-metadata tqdm \
  --copy-metadata regex \
  --copy-metadata requests \
  --copy-metadata packaging \
  --copy-metadata filelock \
  --copy-metadata numpy \
  --copy-metadata tokenizers \
  --copy-metadata huggingface-hub \
  --copy-metadata safetensors \
  --copy-metadata pyyaml \
  --copy-metadata fsspec \
  --copy-metadata scipy \
  --copy-metadata torch \
  --copy-metadata pillow \
  --copy-metadata sentence-transformers \
  --copy-metadata transformers \
  --collect-submodules app \
  desktop.py

echo
echo "✅ Built: dist/RESOPT.app"
echo "   Test it:  open 'dist/RESOPT.app'"
