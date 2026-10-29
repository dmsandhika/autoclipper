#!/usr/bin/env bash
# Setup sekali jalan: ffmpeg + uv + virtualenv + dependencies.
# Pakai Python yang dikelola uv karena python@3.12 dari Homebrew bisa rusak (pyexpat vs libexpat macOS).
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || brew install ffmpeg
command -v uv >/dev/null || brew install uv
[ -x .venv/bin/python ] || uv venv --managed-python --python 3.12 .venv
UV_HTTP_TIMEOUT=900 uv pip install --python .venv/bin/python -r requirements.txt
echo "Setup selesai. Jalankan: .venv/bin/python -m autoclipper.web"
