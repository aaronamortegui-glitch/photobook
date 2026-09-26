#!/bin/bash
# Starts QwenStudio if it is not running (config.json), then Photobook, and opens it.
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then echo "  Run install.command first."; read; exit 1; fi
PYTHONUTF8=1 ".venv/bin/python" -m photobook.lanzar
