"""Photobook's installer. It runs INSIDE the environment INSTALL.bat / install.command
created (.venv, Python 3.12 fetched by uv -- nothing on the system is touched).

  1. installs the light dependencies (requirements.txt) -- no torch: Photobook never
     loads a diffusion model, QwenStudio does, over HTTP
  2. installs easy-dwpose without its dependencies (it pins torch and numpy<2, which
     it does not need here; photobook/pose.py runs it on onnxruntime)
  3. downloads the models: ArcFace buffalo_l (likeness score, face landmarks) and the
     two DWPose .onnx files (skeletons of your own scene photos)
  4. finds QwenStudio and writes config.json
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import urllib.request
import zipfile

APP = os.path.dirname(os.path.abspath(__file__))
UV = os.path.join(APP, ".uv", "uv.exe" if os.name == "nt" else "uv")
BUFFALO = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
BUFFALO_ARCHIVOS = ("det_10g.onnx", "w600k_r50.onnx")


def pip(*args: str) -> None:
    if os.path.exists(UV):
        cmd = [UV, "pip", "install", "--python", sys.executable, "--link-mode=copy", *args]
    else:
        cmd = [sys.executable, "-m", "pip", "install", *args]
    print("\n$ pip install " + " ".join(args), flush=True)
    subprocess.run(cmd, check=True)


def buffalo() -> None:
    d = os.path.join(APP, "modelos", "buffalo_l")
    if all(os.path.exists(os.path.join(d, f)) for f in BUFFALO_ARCHIVOS):
        print("  ArcFace models: already here", flush=True)
        return
    os.makedirs(d, exist_ok=True)
    print("  Downloading ArcFace buffalo_l (~280 MB)...", flush=True)
    with urllib.request.urlopen(BUFFALO, timeout=600) as r:
        z = zipfile.ZipFile(io.BytesIO(r.read()))
    for n in z.namelist():
        if os.path.basename(n) in BUFFALO_ARCHIVOS:
            open(os.path.join(d, os.path.basename(n)), "wb").write(z.read(n))
    print("  ArcFace models: ok", flush=True)


def dwpose() -> None:
    print("  Fetching the DWPose models (~350 MB, once)...", flush=True)
    sys.path.insert(0, APP)
    from photobook.pose import detector
    detector()
    print("  DWPose: ok", flush=True)


def buscar_qwenstudio() -> str | None:
    candidatos = [os.path.join(os.path.dirname(APP), "QwenStudio"), os.path.join(APP, "..", "Qwen_studio")]
    if os.name == "nt":
        candidatos += [f"{u}:\\QwenStudio" for u in "CDEFG"]
    else:
        candidatos += [os.path.expanduser("~/QwenStudio"), "/Applications/QwenStudio"]
    for c in candidatos:
        if os.path.isdir(os.path.join(c, "qwenstudio")):
            return os.path.abspath(c)
    return None


def main() -> None:
    print("\n[1/4] Dependencies", flush=True)
    pip("-r", os.path.join(APP, "requirements.txt"))
    print("\n[2/4] DWPose (without torch)", flush=True)
    pip("--no-deps", "easy-dwpose==1.0.2")
    print("\n[3/4] Models", flush=True)
    buffalo()
    dwpose()
    print("\n[4/4] QwenStudio", flush=True)
    f = os.path.join(APP, "config.json")
    cfg = json.load(open(f, encoding="utf-8")) if os.path.exists(f) else {}
    q = cfg.get("qwenstudio") or buscar_qwenstudio()
    if not q:
        try:
            q = input("  Where is QwenStudio installed? (folder path, Enter to skip): ").strip().strip('"') or None
        except EOFError:
            q = None
    if q and not os.path.isdir(os.path.join(q, "qwenstudio")):
        print(f"  {q} does not look like a QwenStudio folder -- skipped.", flush=True)
        q = None
    cfg.update({"qwenstudio": q, "qwen_url": cfg.get("qwen_url", "http://127.0.0.1:7860"),
                "puerto": cfg.get("puerto", 7870)})
    json.dump(cfg, open(f, "w", encoding="utf-8"), indent=1)
    print(f"  QwenStudio: {q or 'not found -- start it yourself before Photobook'}", flush=True)
    print("\n  Photobook is installed. Start it with RUN.bat (Windows) or run.command (Mac).", flush=True)


if __name__ == "__main__":
    main()
