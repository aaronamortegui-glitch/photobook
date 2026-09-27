"""Thin client for the QwenStudio HTTP engine (http://127.0.0.1:7860).

QwenStudio holds the model; this service never loads it. Every call is a
blocking POST, one at a time, because the engine itself serialises on its GPU
lock and a second request would only wait there.

Images go in as data URLs and come back as file paths: the result is fetched
over HTTP and written where the caller asks, so the photobook session folder
holds everything it produced.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
import urllib.request

URL = os.environ.get("PHOTOBOOK_QWEN_URL", "http://127.0.0.1:7860")


class ErrorMotor(RuntimeError):
    pass


def data_url(ruta_o_img, tope: int | None = None) -> str:
    """A file path or a PIL image as a PNG/JPEG data URL."""
    from PIL import Image
    img = ruta_o_img if not isinstance(ruta_o_img, str) else Image.open(ruta_o_img)
    img = img.convert("RGB")
    if tope and max(img.size) > tope:
        img = img.copy()
        img.thumbnail((tope, tope), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _post(ruta: str, cuerpo: dict, timeout: int = 1800) -> dict:
    req = urllib.request.Request(URL + ruta, data=json.dumps(cuerpo).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    if isinstance(d, dict) and d.get("error"):
        raise ErrorMotor(d["error"])
    return d


def _get(ruta: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(URL + ruta, timeout=timeout) as r:
        return json.loads(r.read().decode())


def estado() -> dict:
    return _get("/api/estado")


def progreso() -> dict:
    try:
        return _get("/api/progreso", timeout=5)
    except Exception:
        return {}


def disponible() -> bool:
    try:
        e = estado()
        return bool(e.get("pesos_listos"))
    except Exception:
        return False


def bajar(archivo: str, destino: str) -> str:
    """Fetch /salidas/<file> from the engine into `destino`."""
    os.makedirs(os.path.dirname(destino) or ".", exist_ok=True)
    with urllib.request.urlopen(URL + archivo, timeout=120) as r, open(destino, "wb") as f:
        f.write(r.read())
    return destino


# Settings passed on every request, so what the service does does not depend
# on whatever the QwenStudio panel was last left at (it was found with the
# turbo adapter on and a leftover negative prompt).
BASE = {"turbo": False, "resumen": False, "muestreo": "base", "vae": "hdr"}


def generar(destino: str, *, prompt: str, personas=(), pose_lib: str | None = None,
            pose: str | None = None, tipo_pose: str = "openpose",
            ratio: str = "3:4", megapixeles: float = 1.0, steps: int = 28,
            seed: int = 0, cfg: float = 1.0, negativo: str = "",
            describir_escena: bool = False, escena=None) -> dict:
    cuerpo = dict(BASE, prompt=prompt, ratio=ratio, megapixeles=megapixeles,
                  steps=steps, seed=seed, cfg=cfg, negativo=negativo,
                  personas=[data_url(p, 1600) for p in personas],
                  describir_escena=describir_escena, caso="photobook")
    if pose:
        cuerpo["pose"] = data_url(pose)
        cuerpo["tipo_pose"] = tipo_pose      # "depth": a depth map instead of a skeleton
    elif pose_lib:
        cuerpo["pose_lib"] = pose_lib
    if escena is not None:
        cuerpo["escena"] = data_url(escena, 1600)
    enfriar()
    t0 = time.time()
    d = _post("/api/generar", cuerpo)
    img = d["imagenes"][0]
    bajar(img["archivo"], destino)
    return {"archivo": destino, "seed": img["seed"], "tam": img["tam"],
            "prompt": d.get("prompt", ""), "segundos": round(time.time() - t0, 1)}


def editar(destino: str, *, imagen, prompt: str, referencias=(), steps: int = 28,
           seed: int = 0, cfg: float = 1.0, negativo: str = "") -> dict:
    """Whole-frame instruction edit. `imagen` is sent uncapped."""
    cuerpo = dict(BASE, imagen=data_url(imagen), prompt=prompt, steps=steps,
                  seed=seed, cfg=cfg, negativo=negativo,
                  referencias=[data_url(r, 1600) for r in referencias])
    enfriar()
    t0 = time.time()
    d = _post("/api/editar", cuerpo)
    img = d["imagenes"][0]
    bajar(img["archivo"], destino)
    return {"archivo": destino, "tam": img["tam"], "prompt": d.get("prompt", ""),
            "segundos": round(time.time() - t0, 1)}


def describir(imagen, pregunta: str, max_tokens: int = 160) -> str:
    """Ask Qwen3-VL a free question about an image."""
    cuerpo = {"imagen": data_url(imagen, 1024), "tarea": "free", "extra": pregunta, "max_tokens": max_tokens}
    try:
        d = _post("/api/describir", cuerpo)
    except ErrorMotor:
        # Qwen3-VL loaded right after the image model sometimes ends split across CPU and
        # GPU ("weight type CPUBFloat16"); with the card released it loads whole. Once.
        _post("/api/desmontar", {}, timeout=120)
        d = _post("/api/describir", cuerpo)
    return (d.get("texto") or "").strip()


def liberar_vision() -> None:
    try:
        _post("/api/liberar_vision", {}, timeout=60)
    except Exception:
        pass


def temperatura() -> int | None:
    """GPU temperature from nvidia-smi, independent of the engine being up."""
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True,
                             text=True, timeout=10).stdout.strip().splitlines()
        return int(out[0]) if out else None
    except Exception:
        return None


def enfriar(limite: int = 75, maximo_s: int = 240) -> int:
    """Wait until the card is under `limite` C, at most `maximo_s`. Returns seconds waited.

    Added after 2026-09-24: six hours of back-to-back generations on the laptop
    ended in two corrected PCIe hardware errors and a driver reset. Letting the
    card breathe between photos costs a little time and keeps a long shoot
    from being the thing that pushes it over.
    """
    t0 = time.time()
    while time.time() - t0 < maximo_s:
        g = temperatura()
        if g is None or g < limite:
            break
        time.sleep(5)
    return int(time.time() - t0)


def reescalar(destino: str, *, imagen, objetivo: int = 1331, seed: int = 0, steps: int = 40) -> dict:
    """QwenStudio's upscale: the image redrawn larger with itself as the reference.

    `objetivo` is the side of the square whose area is the target: 1331 is
    1.77 MP, the size a one-reference shot reaches, so a skeleton shot made at
    1.0 MP ends at the same size as the others.
    """
    cuerpo = dict(BASE, imagen=data_url(imagen), objetivo=objetivo, steps=steps, seed=seed)
    enfriar()
    t0 = time.time()
    d = _post("/api/reescalar", cuerpo)
    img = d["imagenes"][0]
    bajar(img["archivo"], destino)
    return {"archivo": destino, "tam": img["tam"], "segundos": round(time.time() - t0, 1)}


def cancelar() -> None:
    """Abort the generation in progress (QwenStudio checks between steps)."""
    _post("/api/cancelar", {}, timeout=30)
