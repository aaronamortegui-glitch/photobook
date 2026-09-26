"""Skeletons for the new poses: DWPose over the Qwen-made source photos.

Run with a Python that has easy-dwpose (the AI-Toolkit venv on this machine):
    D:\AIToolkit\AI-Toolkit\venv\Scripts\python.exe herramientas\build_poses.py
Writes catalogo/poses/<id>.png (skeleton), thumbs/<id>.jpg, and adds the entry
to index.json. A pose whose skeleton comes back empty is skipped.
"""
import json, os
import numpy as np
from PIL import Image

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(RAIZ, "catalogo", "poses")
nuevas = json.load(open(os.path.join(P, "nuevas.json"), encoding="utf-8"))
idx = json.load(open(os.path.join(P, "index.json"), encoding="utf-8"))
ya = {e["id"] for e in idx}

import torch
from easy_dwpose import DWposeDetector
det = DWposeDetector(device="cuda" if torch.cuda.is_available() else "cpu")

for pid, meta in nuevas.items():
    src = os.path.join(P, "fuentes", f"{pid}.png")
    if not os.path.exists(src):
        print("missing source", pid); continue
    im = Image.open(src).convert("RGB")
    sk = det(im, output_type="pil", include_hands=True, include_face=True)
    sk = sk.resize(im.size)
    if np.asarray(sk).max() < 30:
        print("empty skeleton", pid); continue
    sk.save(os.path.join(P, f"{pid}.png"))
    t = im.copy(); t.thumbnail((640, 640)); t.save(os.path.join(P, "thumbs", f"{pid}.jpg"), quality=88)
    if pid not in ya:
        idx.append({"id": pid, "label": meta["label"], "framing": meta["encuadre"],
                    "desc": meta["desc"].replace("her ", "the ").replace("his ", "the "), "origen": "photobook"})
    print("ok", pid, flush=True)
del det; torch.cuda.empty_cache()
json.dump(idx, open(os.path.join(P, "index.json"), "w"), indent=1)
print("POSES_LISTAS")
