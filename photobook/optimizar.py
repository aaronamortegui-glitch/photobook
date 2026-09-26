"""Image weight: what the page loads and what goes into the pipeline.

Measured on 2026-09-25: package photos and client photos are stored as PNG at up to
2048 px, 2-4 MB each -- a 6-photo package was 17 MB, a 20-photo one would be ~60 MB,
and the page was loading those originals into every card and grid tile.

Two rules:
  - WORKING files (what the models read) stay lossless and capped at LADO_MAX on the
    long side. More pixels than that buy nothing: the engine brings references to
    ~1 MP anyway (QwenStudio's REF_MP) and the output sets the size.
  - DISPLAY files are JPEG thumbnails made on demand and cached next to the source
    (`_mini/`), regenerated when the source changes. The lightbox is the only place
    that loads an original.
"""
from __future__ import annotations

import os

from PIL import Image, ImageOps

LADO_MAX = 2048
ANCHOS = (240, 480, 960)          # the only thumbnail widths served: bounded cache


def normalizar(img: Image.Image, lado_max: int = LADO_MAX) -> Image.Image:
    """Upright (EXIF), RGB, long side capped. The single entry point for any input."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > lado_max:
        img = img.copy()
        img.thumbnail((lado_max, lado_max), Image.LANCZOS)
    return img


def mini(ruta: str, ancho: int = 480, calidad: int = 84) -> str:
    """Path of a cached JPEG thumbnail of `ruta`, `ancho` px wide (snapped to ANCHOS)."""
    ancho = min(ANCHOS, key=lambda a: abs(a - ancho))
    d = os.path.join(os.path.dirname(ruta), "_mini")
    base = os.path.splitext(os.path.basename(ruta))[0]
    out = os.path.join(d, f"{base}_{ancho}.jpg")
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(ruta):
        return out
    os.makedirs(d, exist_ok=True)
    im = Image.open(ruta).convert("RGB")
    if im.width > ancho:
        im = im.resize((ancho, max(1, round(im.height * ancho / im.width))), Image.LANCZOS)
    im.save(out, "JPEG", quality=calidad, optimize=True, progressive=True)
    return out


def peso_mb(rutas) -> float:
    return round(sum(os.path.getsize(r) for r in rutas if os.path.exists(r)) / 1e6, 1)
