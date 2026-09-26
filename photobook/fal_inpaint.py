"""Mask-aware inpainting on fal: GPT Image 2.5 Sunburst edit, the model an eyewear
SUNBURST workflow uses (openai/gpt-image-2.5/sunburst/edit).

Called over fal's queue with plain HTTP -- submit, poll, fetch -- so nothing has to
be installed. The key comes from the app folder's .env (FAL_KEY=...) or the
environment, never from code.

What is sent mirrors a GPT Image 2 edit node for ComfyUI:
  image_urls  [the image to edit, then the references]  (data URIs)
  mask_url    grayscale, WHITE = edit, BLACK = keep
  image_size  {width, height}, multiples of 16
  quality, output_format, num_images
The "lock outside mask (hard)" half -- pasting back only inside the mask -- is done
by the caller (detailer.pegar), exactly as that node does it after the call.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENDPOINT = "openai/gpt-image-2.5/sunburst/edit"
COLA = "https://queue.fal.run/"


def clave() -> str:
    k = os.environ.get("FAL_KEY", "").strip()
    if k:
        return k
    f = os.path.join(RAIZ, ".env")
    if os.path.exists(f):
        for linea in open(f, encoding="utf-8"):
            if linea.strip().startswith("FAL_KEY="):
                return linea.split("=", 1)[1].strip()
    raise RuntimeError("FAL_KEY is not set: add FAL_KEY=... to the .env file in the app folder")


def _uri(img, formato="PNG") -> str:
    from PIL import Image
    im = Image.open(img) if isinstance(img, str) else img
    if formato == "JPEG" and im.mode != "RGB":
        im = im.convert("RGB")
    buf = io.BytesIO()
    im.save(buf, formato)
    tipo = "png" if formato == "PNG" else "jpeg"
    return f"data:image/{tipo};base64," + base64.b64encode(buf.getvalue()).decode()


def _pedir(url: str, datos: dict | None = None, timeout: int = 120) -> dict:
    cab = {"Authorization": "Key " + clave(), "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(datos).encode() if datos is not None else None,
                                 headers=cab, method="POST" if datos is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def editar(imagen, referencias, mascara, prompt: str, *, ancho: int, alto: int,
           calidad: str = "high", espera_max: int = 600, endpoint: str = ENDPOINT) -> tuple:
    """Run one masked edit. Returns (PIL image, info)."""
    from PIL import Image
    args = {"prompt": prompt,
            "image_urls": [_uri(imagen)] + [_uri(r, "JPEG") for r in referencias],
            "mask_url": _uri(mascara),
            "image_size": {"width": int(ancho) // 16 * 16, "height": int(alto) // 16 * 16},
            "quality": calidad, "output_format": "png", "num_images": 1}
    t0 = time.time()
    sub = _pedir(COLA + endpoint, args)
    estado_url, resp_url = sub["status_url"], sub["response_url"]
    while True:
        st = _pedir(estado_url)
        if st.get("status") == "COMPLETED":
            break
        if st.get("status") in ("FAILED", "ERROR") or time.time() - t0 > espera_max:
            raise RuntimeError(f"fal {st.get('status')}: {json.dumps(st)[:400]}")
        time.sleep(2)
    res = _pedir(resp_url)
    url = res["images"][0]["url"]
    with urllib.request.urlopen(url, timeout=120) as r:
        out = Image.open(io.BytesIO(r.read())).convert("RGB")
    return out, {"segundos": round(time.time() - t0, 1), "request_id": sub.get("request_id"),
                 "tam": f"{out.width}x{out.height}", "pedido": f"{args['image_size']['width']}x{args['image_size']['height']}"}
