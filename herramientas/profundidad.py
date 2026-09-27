r"""Depth maps of package samples with Depth Anything V2 (the model files ComfyUI already
has on this machine; the architecture from comfyui_controlnet_aux). Run with ComfyUI's
embedded Python (it has torch):

    <ComfyUI>\python_embeded\python.exe herramientas\profundidad.py <package id> [...]

Writes catalogo/paquetes/<id>/<shot>_depth.png: near = white, far = black, at the
sample's size. The user's idea (2026-09-26): a skeleton carries only the pose; a depth
map carries the whole scene -- the body's shape, the furniture, the framing -- so the
client's photo keeps the sample's composition.
"""
import os, sys
import numpy as np
import torch
from PIL import Image
from safetensors.torch import load_file

COMFY = os.environ.get("PHOTOBOOK_COMFY", r"D:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI")
sys.path.insert(0, os.path.join(COMFY, "custom_nodes", "comfyui_controlnet_aux", "src"))
from custom_controlnet_aux.depth_anything_v2.dpt import DepthAnythingV2  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PESOS = os.path.join(COMFY, "models", "depthanything", "depth_anything_v2_vitl_fp16.safetensors")
CFG = {"encoder": "vitl", "features": 256, "out_channels": [256, 512, 1024, 1024]}


def modelo():
    m = DepthAnythingV2(**CFG)
    sd = {k: v.float() for k, v in load_file(PESOS).items()}
    faltan, sobran = m.load_state_dict(sd, strict=False)
    if faltan:
        raise RuntimeError(f"depth weights do not fit: {len(faltan)} missing, e.g. {faltan[:3]}")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    return m.to(dev).eval(), dev


def profundidad(m, ruta):
    import cv2
    bgr = cv2.imread(ruta)
    with torch.no_grad():
        d = m.infer_image(bgr, input_size=518)
    d = (d - d.min()) / max(1e-6, d.max() - d.min()) * 255.0
    return Image.fromarray(d.astype(np.uint8)).convert("RGB")


if __name__ == "__main__":
    m, dev = modelo()
    for pid in sys.argv[1:]:
        D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
        for f in sorted(os.listdir(D)):
            if f[:2].isdigit() and f.endswith((".jpg", ".png")) and "_" not in f:
                dst = os.path.join(D, f.rsplit(".", 1)[0] + "_depth.png")
                if not os.path.exists(dst):
                    profundidad(m, os.path.join(D, f)).save(dst)
                    print("ok", pid, f, flush=True)
    print("PROFUNDIDAD_LISTA", dev, flush=True)
