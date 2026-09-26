"""Face pass: find the face with SAM 3, rebuild it from the client's photo, stitch it back.

Three pieces, each in the process that owns its model:

  - SAM 3 runs in ComfyUI's embedded Python (sam3/sam3_masks.py), headless, in
    a subprocess that exits when done. It never shares the card with a running
    generation: the photobook worker calls it between engine jobs.
  - ArcFace (herramientas/faceid.py) runs on the CPU in the same Python. It is
    the identity score used to keep the better of before/after.
  - The rebuild itself is a whole-frame edit on QwenStudio, over a crop around
    the face enlarged to the engine's budget -- so a face that is 120 px wide
    in a full-length shot is redrawn at ~1000 px and scaled back down.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageFilter

from . import motor_qwen as Q

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMFY_PY = os.environ.get("PHOTOBOOK_COMFY_PY", r"D:\ComfyUI_windows_portable_nvidia"
                          r"\ComfyUI_windows_portable\python_embeded\python.exe")
# the identity score and face landmarks (ArcFace, onnxruntime) run in Photobook's own
# environment; only the optional SAM 3 masks still need ComfyUI's Python (COMFY_PY)
FACE_PY = sys.executable
SAM3 = os.path.join(RAIZ, "sam3", "sam3_masks.py")
FACEID = os.path.join(RAIZ, "herramientas", "faceid.py")

# The rebuild's instruction. Shape measured in QwenStudio: the verb "put X from
# <image2> on", the attributes named rather than the person, the change first.
# QwenStudio's edit path appends the generic preservation clause itself.
PROMPT_CARA = ("Put the face from <image2> on the person in <image1>: the same facial "
               "structure, eyes, nose, mouth, eyebrows, skin tone and age, with natural "
               "sharp skin detail. The head angle and the expression stay as in <image1>.")
NEGATIVO_CARA = "blurry, smeared, plastic skin, deformed eyes, different person, cartoon"


def _correr(args, timeout=900) -> list[dict]:
    env = dict(os.environ, PYTHONWARNINGS="ignore")
    p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env,
                       encoding="utf-8", errors="replace")
    filas = []
    for linea in p.stdout.splitlines():
        linea = linea.strip()
        if linea.startswith("{"):
            try:
                filas.append(json.loads(linea))
            except ValueError:
                pass
    if p.returncode != 0 and not filas:
        raise RuntimeError((p.stderr or "subprocess failed")[-800:])
    return filas


def mascaras(imagenes: list[str], texto: str = "face", umbral: float = 0.5) -> dict[str, dict]:
    """SAM 3 masks for many images in one process. Returns {image: {mask, coverage}}."""
    if not imagenes:
        return {}
    d = tempfile.mkdtemp(prefix="pb_sam3_")
    items = [{"image": os.path.abspath(f), "mask": os.path.abspath(os.path.splitext(f)[0] + "_mask.png")}
             for f in imagenes]
    trabajo = os.path.join(d, "jobs.json")
    json.dump({"text": texto, "threshold": umbral, "items": items}, open(trabajo, "w"))
    filas = _correr([COMFY_PY, "-W", "ignore", SAM3, trabajo])
    return {os.path.normcase(f["image"]): f for f in filas if "mask" in f}


def identidad(referencias: list[str], imagenes: list[str]) -> dict[str, float | None]:
    """ArcFace cosine between the client's photos and each image."""
    if not imagenes:
        return {}
    filas = _correr([FACE_PY, "-W", "ignore", FACEID, ";".join(referencias)] + list(imagenes))
    return {os.path.normcase(os.path.abspath(f["image"])): f.get("score") for f in filas if "image" in f}


def caja_cara(mascara: Image.Image, umbral: int = 127):
    return mascara.point(lambda v: 255 if v > umbral else 0).getbbox()


def recorte_cara(img: Image.Image, caja, factor: float = 2.3):
    """A square around the face, `factor` times its size, slid inside the frame."""
    x0, y0, x1, y1 = caja
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    lado = int(max(x1 - x0, y1 - y0) * factor)
    lado = min(lado, img.width, img.height)
    lado = max(lado, 64)
    l = int(round(cx - lado / 2))
    t = int(round(cy - lado / 2 - 0.05 * lado))       # a little headroom for the hair
    l = max(0, min(l, img.width - lado))
    t = max(0, min(t, img.height - lado))
    return (l, t, l + lado, t + lado)


def igualar_color(nuevo: Image.Image, viejo: Image.Image, mascara: Image.Image) -> Image.Image:
    """Match the rebuilt face's colour to the original's, inside the mask.

    Measured in pruebas/exp2: the rebuild takes the reference photo's skin
    tone and white balance with it -- a waist-up face under golden light came
    back orange. Mean and spread per channel, measured over the face only,
    moved back onto the original's: the shape comes from the rebuild, the
    light stays the scene's.
    """
    import numpy as np
    a = np.asarray(nuevo, dtype=np.float32)
    b = np.asarray(viejo, dtype=np.float32)
    m = np.asarray(mascara, dtype=np.float32) > 127
    if m.sum() < 50:
        return nuevo
    out = a.copy()
    for c in range(3):
        ma, sa = a[..., c][m].mean(), a[..., c][m].std() + 1e-3
        mb, sb = b[..., c][m].mean(), b[..., c][m].std() + 1e-3
        out[..., c] = (a[..., c] - ma) * (sb / sa) + mb
    return Image.fromarray(np.clip(out, 0, 255).astype("uint8"))


def reforzar(imagen: str, mascara: str, cara_cliente: str, destino: str, *,
             seed: int = 0, cfg: float = 3.0, steps: int = 28, lado: int = 1024,
             prompt: str = PROMPT_CARA, negativo: str = NEGATIVO_CARA,
             crecer: float = 0.10, difuminar: float = 0.06) -> dict:
    """Rebuild the face of `imagen` from `cara_cliente`, only inside the face mask."""
    img = Image.open(imagen).convert("RGB")
    m = Image.open(mascara).convert("L")
    if m.size != img.size:
        m = m.resize(img.size, Image.BILINEAR)
    caja = caja_cara(m)
    if not caja:
        return {"error": "no face found"}
    rc = recorte_cara(img, caja)
    crop = img.crop(rc)
    n = crop.width
    grande = crop.resize((lado, lado), Image.LANCZOS)
    tmp = destino + ".crop.png"
    r = Q.editar(tmp, imagen=grande, prompt=prompt, referencias=[cara_cliente],
                 steps=steps, seed=seed, cfg=cfg, negativo=negativo)
    nuevo = Image.open(tmp).convert("RGB").resize((n, n), Image.LANCZOS)
    nuevo = igualar_color(nuevo, crop, m.crop(rc))

    # the mask, grown a little past the jaw and hairline and feathered, so the
    # seam falls on skin the model also redrew
    tam = max(caja[2] - caja[0], caja[3] - caja[1])
    mc = m.crop(rc)
    g = max(1, int(tam * crecer)) | 1
    mc = mc.filter(ImageFilter.MaxFilter(min(g, 51)))
    mc = mc.filter(ImageFilter.GaussianBlur(max(1, tam * difuminar)))
    final = img.copy()
    final.paste(Image.composite(nuevo, crop, mc), rc[:2])
    final.save(destino, quality=95) if destino.lower().endswith(".jpg") else final.save(destino)
    os.remove(tmp)
    return {"archivo": destino, "segundos": r["segundos"], "recorte": list(rc),
            "cara_px": tam, "prompt": r.get("prompt", "")}


def hoja_identidad(cara: str, cuerpo: str, destino: str, alto: int = 1080) -> str:
    """The client's two photos side by side on one 16:9 sheet: close-up left,
    full-length right, on a neutral grey. One reference with both the face
    at size and the build, instead of choosing one per shot."""
    a = Image.open(cara).convert("RGB")
    b = Image.open(cuerpo).convert("RGB")
    ancho = alto * 16 // 9
    hueco = alto // 30
    a = a.resize((int(a.width * alto / a.height), alto), Image.LANCZOS)
    b = b.resize((int(b.width * alto / b.height), alto), Image.LANCZOS)
    if a.width + b.width + hueco > ancho:           # a wide close-up: shrink both to fit
        f = (ancho - hueco) / (a.width + b.width)
        a = a.resize((int(a.width * f), int(a.height * f)), Image.LANCZOS)
        b = b.resize((int(b.width * f), int(b.height * f)), Image.LANCZOS)
    hoja = Image.new("RGB", (ancho, alto), (200, 200, 198))
    x = (ancho - a.width - b.width - hueco) // 2
    hoja.paste(a, (x, (alto - a.height) // 2))
    hoja.paste(b, (x + a.width + hueco, (alto - b.height) // 2))
    hoja.save(destino)
    return destino
