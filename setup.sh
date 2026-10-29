#!/usr/bin/env bash
# Setup sekali jalan: ffmpeg + Python 3.12 + virtualenv + dependencies
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || brew install ffmpeg
command -v python3.12 >/dev/null || brew install python@3.12
[ -d .venv ] || python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
echo "Setup selesai. Coba: .venv/bin/python -m autoclipper \"https://youtu.be/...\""
