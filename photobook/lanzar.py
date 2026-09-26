"""Start Photobook: make sure QwenStudio is up, then serve the page and open it.

    RUN.bat / run.command  ->  .venv python -m photobook.lanzar

Reads config.json (written by the installer):
  qwenstudio   the QwenStudio folder -- started here when it is not running yet
  qwen_url     where its API answers (default http://127.0.0.1:7860)
  puerto       Photobook's port (default 7870)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config() -> dict:
    f = os.path.join(RAIZ, "config.json")
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def responde(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/api/estado", timeout=3):
            return True
    except Exception:
        return False


def arrancar_qwen(carpeta: str) -> None:
    if os.name == "nt":
        bat = os.path.join(carpeta, "RUN.bat")
        subprocess.Popen(["cmd", "/c", "start", "", bat], cwd=carpeta)
    else:
        subprocess.Popen(["bash", os.path.join(carpeta, "run.command")], cwd=carpeta)


def main() -> None:
    cfg = config()
    # the environment wins over config.json
    url = (os.environ.get("PHOTOBOOK_QWEN_URL") or cfg.get("qwen_url") or "http://127.0.0.1:7860").rstrip("/")
    puerto = int(os.environ.get("PHOTOBOOK_PORT") or cfg.get("puerto") or 7870)
    os.environ["PHOTOBOOK_QWEN_URL"], os.environ["PHOTOBOOK_PORT"] = url, str(puerto)

    if not responde(url):
        carpeta = cfg.get("qwenstudio")
        if carpeta and os.path.isdir(carpeta):
            print(f"  Starting QwenStudio ({carpeta})...", flush=True)
            arrancar_qwen(carpeta)
            t0 = time.time()
            while not responde(url) and time.time() - t0 < 600:
                time.sleep(3)
        if not responde(url):
            print(f"  QwenStudio is not answering on {url}.\n"
                  f"  Start it (QwenStudio\\RUN.bat) -- Photobook opens anyway and waits for it.", flush=True)

    from photobook.servidor import main as servir
    pagina = f"http://127.0.0.1:{puerto}"
    print(f"  Photobook: {pagina}", flush=True)
    if os.environ.get("PHOTOBOOK_SIN_NAVEGADOR") != "1":
        import threading   # once the server below is listening
        threading.Timer(1.5, webbrowser.open, (pagina,)).start()
    servir()


if __name__ == "__main__":
    sys.exit(main())
