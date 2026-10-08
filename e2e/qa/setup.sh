#!/usr/bin/env bash
# What the QA tools and the e2e tests need on a fresh machine (a cloud session), each step skipped when already done: ComfyUI at the version the
# tests pin (.github/workflows/tests.yml) next to this repository, its Python packages (CPU PyTorch) in ComfyUI/venv, the e2e packages and a
# Chromium. Then start the server: e2e/qa/serve.sh start.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
COMFY="${COMFYUI_PATH:-$REPO/../ComfyUI}"
REF="$(grep -o "'[0-9a-f]\{40\}'" "$REPO/.github/workflows/tests.yml" | head -1 | tr -d "'")"

if [[ ! -f "$COMFY/main.py" ]]; then
  echo "ComfyUI ${REF:0:10} -> $COMFY"
  git init -q "$COMFY"
  git -C "$COMFY" fetch -q --depth 1 https://github.com/comfyanonymous/ComfyUI "$REF"
  git -C "$COMFY" checkout -q FETCH_HEAD
fi
if [[ ! -x "$COMFY/venv/bin/python" ]]; then
  echo "ComfyUI's Python packages (CPU PyTorch) -> $COMFY/venv"
  python3 -m venv "$COMFY/venv"
  "$COMFY/venv/bin/pip" install -q --upgrade pip
  "$COMFY/venv/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  "$COMFY/venv/bin/pip" install -q -r "$COMFY/requirements.txt"
fi
cd "$REPO/e2e"
if [[ ! -d node_modules ]]; then
  echo "e2e packages"
  npm ci --silent
fi
if [[ "$(node -e "console.log(require('./qa/lib').chromiumPath() ?? (require('fs').existsSync(require('@playwright/test').chromium.executablePath()) ? 'own' : ''))")" == "" ]]; then
  echo "Chromium"
  npx playwright install chromium
fi
echo "Ready. Start the server: e2e/qa/serve.sh start"
