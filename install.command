#!/bin/bash
# Photobook - macOS installer. Nothing on your system is touched: uv downloads its
# own Python and the environment lives inside this folder. QwenStudio is separate.
set -e
cd "$(dirname "$0")"
echo "=================================================================="
echo "  Photobook - installer"
echo "=================================================================="
UVDIR="$PWD/.uv"; UV="$UVDIR/uv"
if [ ! -x "$UV" ]; then
  echo "  Downloading uv..."
  mkdir -p "$UVDIR"
  case "$(uname -m)" in
    arm64)  ARCH="aarch64-apple-darwin" ;;
    x86_64) ARCH="x86_64-apple-darwin" ;;
    *) echo "  Unsupported architecture: $(uname -m)"; exit 1 ;;
  esac
  curl -fsSL "https://github.com/astral-sh/uv/releases/latest/download/uv-${ARCH}.tar.gz" -o /tmp/uv.tar.gz
  tar -xzf /tmp/uv.tar.gz -C "$UVDIR" --strip-components=1
  rm -f /tmp/uv.tar.gz; chmod +x "$UV"
fi
if [ ! -x "$PWD/.venv/bin/python" ]; then
  echo "  Creating an isolated environment with Python 3.12..."
  "$UV" venv "$PWD/.venv" --python 3.12
fi
"$PWD/.venv/bin/python" "$PWD/instalar.py"
echo; echo "  Press Enter to close."; read
