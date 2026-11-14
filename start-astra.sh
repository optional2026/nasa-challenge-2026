#!/usr/bin/env sh
# ASTRA start script for macOS/Linux.
cd "$(dirname "$0")/backend"
[ -d .venv ] || { python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt; }
. .venv/bin/activate
python run.py "$@"
