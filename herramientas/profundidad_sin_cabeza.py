r"""Take the sample model's head out of a depth map: the depth keeps the scene, the body,
the arms; the head and hair shape must come from the client (pruebas/exp32: with the
full depth map Ana took the sample's short hair and dropped from 0.57 to 0.37).

    .venv\Scripts\python.exe herramientas\profundidad_sin_cabeza.py <package id> [...]

The face box (SCRFD, as in faceid.py) grown 2.2x (hair included) is filled with the depth
around it, feathered. Writes <shot>_depthnc.png next to <shot>_depth.png.
"""
import os, sys
import cv2
import numpy as np
from PIL import Image, ImageFilter
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from faceid import Caras


def sin_cabeza(det, muestra, prof):
    img = cv2.imread(muestra)
    caras = det.detectar(img, umbral=0.5)
    d = np.asarray(Image.open(prof).convert("L").resize((img.shape[1], img.shape[0]))).astype(np.float32)
    if not caras:
        return Image.fromarray(d.astype(np.uint8)).convert("RGB"), False
    caja = max(caras, key=lambda c: float((c[0][2] - c[0][0]) * (c[0][3] - c[0][1])))[0]
    x0, y0, x1, y1 = (float(v) for v in np.ravel(caja)[:4])
    cx, cy, lado = (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0) * 2.2
    l, t = int(max(0, cx - lado / 2)), int(max(0, cy - lado * 0.55))
    r, b = int(min(d.shape[1], cx + lado / 2)), int(min(d.shape[0], cy + lado * 0.5))
    # the value to fill with: the depth just around the box (the body and the set there)
    marco = np.concatenate([d[max(0, t - 8):t, l:r].ravel(), d[b:b + 8, l:r].ravel(),
                            d[t:b, max(0, l - 8):l].ravel(), d[t:b, r:r + 8].ravel()])
    relleno = np.median(marco) if marco.size else d.mean()
    m = Image.new("L", (d.shape[1], d.shape[0]), 0)
    from PIL import ImageDraw
    ImageDraw.Draw(m).ellipse((l, t, r, b), fill=255)
    m = np.asarray(m.filter(ImageFilter.GaussianBlur(float(lado) * 0.08))).astype(np.float32) / 255
    out = d * (1 - m) + relleno * m
    return Image.fromarray(out.astype(np.uint8)).convert("RGB"), True


if __name__ == "__main__":
    det = Caras()
    for pid in sys.argv[1:]:
        D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
        for f in sorted(os.listdir(D)):
            if f.endswith("_depth.png"):
                n = f[:-len("_depth.png")]
                muestra = next((os.path.join(D, n + e) for e in (".jpg", ".png") if os.path.exists(os.path.join(D, n + e))), None)
                if muestra:
                    im, ok = sin_cabeza(det, muestra, os.path.join(D, f))
                    im.save(os.path.join(D, n + "_depthnc.png"))
                    print(pid, n, "head removed" if ok else "no face found", flush=True)
