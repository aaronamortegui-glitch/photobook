"""Bring a package's samples to an aspect ratio QwenStudio can generate.

    python herramientas/recortar_muestras.py <package id> [...]

Seedream returned 3520x4096 and 3312x4096 (0.86, 0.81) where 3:4 and 2:3 were asked;
QwenStudio only makes the model card's seven ratios, and a sample whose proportions
differ from the client's photo would get its skeleton stretched. So each sample is CROPPED
(never resized out of shape) to the nearest supported ratio, the window centred on the
person DWPose finds. The 4K master in catalogo/_masters/ is left as it came.
"""
import json, os, sys
import numpy as np
from PIL import Image
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook.pose import esqueleto

RATIOS = {"1:1": 1.0, "4:3": 4 / 3, "3:4": 3 / 4, "3:2": 3 / 2, "2:3": 2 / 3, "16:9": 16 / 9, "9:16": 9 / 16}


def recortar(im: Image.Image) -> tuple[Image.Image, str]:
    w, h = im.size
    nombre = min(RATIOS, key=lambda k: abs(RATIOS[k] - w / h))
    r = RATIOS[nombre]
    sk = esqueleto(im.resize((w // 4, h // 4)))
    if sk is not None:
        a = np.asarray(sk.convert("L")) > 30
        ys, xs = np.nonzero(a)
        cx, cy = xs.mean() * 4, ys.mean() * 4
    else:
        cx, cy = w / 2, h / 2
    if w / h > r:                       # too wide: crop the sides
        nw = int(round(h * r))
        x0 = int(min(max(0, cx - nw / 2), w - nw))
        return im.crop((x0, 0, x0 + nw, h)), nombre
    nh = int(round(w / r))              # too tall: crop top and bottom
    y0 = int(min(max(0, cy - nh / 2), h - nh))
    return im.crop((0, y0, w, y0 + nh)), nombre


def main(pid):
    D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
    M = os.path.join(RAIZ, "catalogo", "_masters", pid)
    f = os.path.join(D, "paquete.json")
    pk = json.load(open(f, encoding="utf-8"))
    for t in pk["tomas"]:
        master = os.path.join(M, f"{t['id']}.png")
        if not t.get("foto") or not os.path.exists(master):
            continue
        im, nombre = recortar(Image.open(master).convert("RGB"))
        im.thumbnail((2048, 2048), Image.LANCZOS)
        im.save(os.path.join(D, t["foto"]), quality=93)
        t["ratio"] = nombre
        print(pid, t["id"], nombre, im.size, flush=True)
    json.dump(pk, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
