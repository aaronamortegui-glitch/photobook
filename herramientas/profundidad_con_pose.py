r"""One control image with both: the full depth map, and the sample's OpenPose skeleton
drawn over it (the user's idea, 2026-09-26). The depth carries the scene, the framing and
the body's volume; the coloured skeleton pins the limbs, the hands and where the head
turns -- where depth alone is ambiguous.

    .venv\Scripts\python.exe herramientas\profundidad_con_pose.py <package id> [...]

Needs <shot>_depth.png (profundidad.py) and <shot>_pose.png (esqueletos_paquete.py).
Writes <shot>_depthpose.png.
"""
import os, sys
import numpy as np
from PIL import Image
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def combinar(prof, pose):
    d = Image.open(prof).convert("RGB")
    p = Image.open(pose).convert("RGB").resize(d.size)
    a = np.asarray(p).astype(np.float32)
    # the skeleton's lines are coloured on black: where it is drawn, it wins
    m = (a.max(axis=2) > 40).astype(np.float32)[..., None]
    out = np.asarray(d).astype(np.float32) * (1 - m) + a * m
    return Image.fromarray(out.astype(np.uint8))


if __name__ == "__main__":
    for pid in sys.argv[1:]:
        D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
        n = 0
        for f in sorted(os.listdir(D)):
            if f.endswith("_depth.png"):
                s = f[:-len("_depth.png")]
                pose = os.path.join(D, s + "_pose.png")
                if os.path.exists(pose):
                    combinar(os.path.join(D, f), pose).save(os.path.join(D, s + "_depthpose.png"))
                    n += 1
        print(pid, n, "combined", flush=True)
