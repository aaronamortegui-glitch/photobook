r"""OpenPose skeletons of a package's photos, so a client can be regenerated in
exactly the model's pose (R3). Runs in Photobook's own environment (photobook/pose.py,
onnxruntime, no torch):
    .venv\Scripts\python.exe herramientas\esqueletos_paquete.py paris_f
Writes catalogo/paquetes/<id>/<shot>_pose.png. A photo where no person is found (a
tiny pixel-art hero, a body seen from straight above) gets none, and its shot is
regenerated from the words alone."""
import os, sys
from PIL import Image
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook.pose import esqueleto

D = os.path.join(RAIZ, "catalogo", "paquetes", sys.argv[1])
for f in sorted(os.listdir(D)):
    if not (f[:2].isdigit() and f.endswith((".png", ".jpg")) and "_" not in f):
        continue
    dst = os.path.join(D, f.rsplit(".", 1)[0] + "_pose.png")
    if os.path.exists(dst):
        continue
    sk = esqueleto(Image.open(os.path.join(D, f)))
    if sk is None:
        print("empty", f, flush=True)
        continue
    sk.save(dst)
    print("ok", f, flush=True)
print("ESQUELETOS_LISTOS")
