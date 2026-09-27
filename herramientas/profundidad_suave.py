r"""A LOOSE control image: the head-free depth map, blurred, with the skeleton drawn over it.

    .venv\Scripts\python.exe herramientas\profundidad_suave.py <package id> [...]

The user, after the first real client (2026-09-26): with the full depth + skeleton the
client inherited the sample model's bob and her build. The scene should be followed
roughly -- where the sofa and the window are, where the camera stands -- not the sample
body's exact outline. Blurring the depth keeps the layout and drops the silhouette; the
skeleton still gives the direction of the pose, the hands and the gaze.

Needs <shot>_depthnc.png and <shot>_pose.png. Writes <shot>_depthsoft.png.
"""
import os, sys
import numpy as np
from PIL import Image, ImageFilter
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def suave(depthnc, pose, radio=0.035):
    d = Image.open(depthnc).convert("RGB")
    d = d.filter(ImageFilter.GaussianBlur(max(d.size) * radio))
    p = Image.open(pose).convert("RGB").resize(d.size)
    a = np.asarray(p).astype(np.float32)
    m = (a.max(axis=2) > 40).astype(np.float32)[..., None]
    return Image.fromarray((np.asarray(d).astype(np.float32) * (1 - m) + a * m).astype(np.uint8))


if __name__ == "__main__":
    for pid in sys.argv[1:]:
        D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
        n = 0
        for f in sorted(os.listdir(D)):
            if f.endswith("_depthnc.png"):
                s = f[:-len("_depthnc.png")]
                if os.path.exists(os.path.join(D, s + "_pose.png")):
                    suave(os.path.join(D, f), os.path.join(D, s + "_pose.png")).save(os.path.join(D, s + "_depthsoft.png"))
                    n += 1
        print(pid, n, flush=True)
