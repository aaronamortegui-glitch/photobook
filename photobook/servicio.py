"""The photoshoot job: sessions on disk and one worker that runs them in order.

A session is a folder under sesiones/ with the client's two photos, their
choices and an estado.json that is the single source of truth -- the page
polls it, and a restarted server picks it up where it stopped.

The shots are produced in blocks. Each block is composed on QwenStudio, then
SAM 3 finds the faces in one subprocess, then each face is rebuilt from the
client's face photo, then ArcFace scores both versions and the better one is
kept. Blocks rather than phases, so the first finished photographs arrive in
minutes instead of after all thirty are composed.

The GPU is shared by QwenStudio and SAM 3, never at the same time: the worker
is a single thread, and SAM 3's process has exited before the next engine
call is made.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid

from PIL import Image

from . import caras as C
from . import detailer as DT
from . import motor_qwen as Q
from . import tomas as T

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESIONES = os.path.join(RAIZ, "sesiones")
BLOQUE = 5

# Measured on the RTX 5090 Laptop (see NOTES.md); used for the estimate only.
SEG_COMPONER = 170
SEG_REFORZAR = 190

# A shot that already scores this high is not sent through the face pass.
# Measured in pruebas/exp1-2: a waist-up shot made from the close-up came out
# at 0.89 and the pass had nothing to add; a full-length one at 0.70 went to
# 0.84. Skipping the strong ones saves ~135 s each.
YA_PARECIDO = 0.78

# The face pass is kept only when ArcFace does not say it made things worse.
# A small tolerance, because two versions of the same face differ by a few
# hundredths from noise alone and the rebuilt one is the sharper picture.
TOLERANCIA = 0.03

# How a shot is made. Measured choices, see README.
CALIDAD = {
    "pasos": 40,              # the model card's editing example; 28 was QwenStudio's face floor
    # pruebas/exp4: with the skeleton gone the sheet is the only reference, the
    # shot goes from 1.0 to 1.77 MP (1.5K), the likeness rose on both framings
    # (0.67->0.73, 0.76->0.82) and the posture still followed the words.
    "pose_en_texto": True,
    "mp_esqueleto": 1.0,      # person sheet + skeleton = two references: ceiling 1.0 MP
    "mp_texto": 1.77,         # person sheet alone: ceiling 2.30 MP, kept under it
    "pasos_cara": 40,
    # Enlarge skeleton shots (1.0 MP) to 1.77 MP at the end. Off until
    # pruebas/exp10 shows the upscale, which runs without guidance, keeps the face.
    "ampliar_esqueleto": False,
    # The face pass. "fal": head and shoulders rebuilt by GPT Image 2.5 Sunburst with a
    # real mask and locked outside it (photobook/fal_inpaint.py) -- the SUNBURST
    # workflow's logic; a masked edit leaves nothing to realign, which is what broke
    # on turned heads with Qwen (pruebas/exp11-12). "qwen": the local pass.
    "cara_motor": "fal",
    # 2026-09-25, the user's call after exp18: Qwen is the base and the face pass
    # is not automatic any more. Photos come out as generated; "Enhance face" is
    # asked for per photo from the page and runs locally -- QwenStudio's upscale on
    # the head-and-shoulders crop with the client's close-up injected
    # (detailer.reforzar_qwen_upscale), which keeps the expression and the angle.
    "cara_auto": False,
    # one line of what the subject is (hair, beard, age, build), appended to each prompt
    "caption_persona": True,
    "cara_sam": "head and neck",
    # Second fal pass on the outline band only (the SUNBURST frame band): the tight
    # head mask keeps the head's size, and this knits the hair and neck edge into
    # the background. pruebas/exp14-16: a loose mask cleaned the edge but grew the
    # head 16-37%; wider blends did not remove the soft edge; the band pass did.
    "pasada_banda": True,
    # Test switch: send every shot through the face pass, not only the weak ones.
    "forzar_cara": False,
}

# A rest between blocks on top of the per-photo cool-down in motor_qwen.enfriar().
DESCANSO_S = 60

MAX_ESCENAS = 30

_lock = threading.RLock()
_cola: "queue.Queue[str]" = queue.Queue()
_cancelar: set[str] = set()
_activo = {"id": None}
# describe-the-client requests: served by the worker between two photos (or at once
# when idle), so the vision model never runs next to a generation on the GPU
_urgentes: "queue.Queue[str]" = queue.Queue()


def _ruta(sid, *p):
    return os.path.join(SESIONES, sid, *p)


def leer(sid: str) -> dict:
    with _lock:
        return json.load(open(_ruta(sid, "estado.json"), encoding="utf-8"))


def escribir(sid: str, est: dict) -> None:
    with _lock:
        tmp = _ruta(sid, "estado.json.tmp")
        json.dump(est, open(tmp, "w", encoding="utf-8"), indent=1)
        os.replace(tmp, _ruta(sid, "estado.json"))


def mutar(sid: str, f) -> dict:
    with _lock:
        est = leer(sid)
        f(est)
        escribir(sid, est)
        return est


def nueva() -> dict:
    sid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    os.makedirs(_ruta(sid, "entrada"))
    os.makedirs(_ruta(sid, "fotos"))
    est = {"id": sid, "creada": time.time(), "fotos": {}, "chequeo": {},
           "eleccion": None, "fase": "nueva", "tomas": [], "error": ""}
    escribir(sid, est)
    return est


def guardar_foto(sid: str, cual: str, img: Image.Image) -> dict:
    """Store the client's face or full-length photo and check it is usable."""
    assert cual in ("cara", "cuerpo")
    from . import optimizar as OP
    img = OP.normalizar(img)
    f = _ruta(sid, "entrada", f"{cual}.png")
    img.save(f)
    avisos = []
    if min(img.size) < 512:
        avisos.append("This photo is small; a sharper one gives a better likeness.")
    try:
        emb = C.identidad([f], [f]).get(os.path.normcase(os.path.abspath(f)))
        cara_ok = emb is not None
    except Exception:
        cara_ok = None
    if cara_ok is False:
        avisos.append("No face was found in this photo.")
    if cual == "cuerpo" and img.height < img.width:
        avisos.append("A full-length photo is usually portrait: head to feet, standing.")

    def f_(est):
        est["fotos"][cual] = f"entrada/{cual}.png"
        est["fotos"].pop("cara_original", None) if cual == "cara" else None
        est["chequeo"][cual] = {"cara": cara_ok, "avisos": avisos,
                                "tam": f"{img.width}x{img.height}"}
    est = mutar(sid, f_)
    # both photos in: are they one person?
    if "cara" in est["fotos"] and "cuerpo" in est["fotos"]:
        try:
            s = C.identidad([_ruta(sid, est["fotos"]["cara"])], [_ruta(sid, est["fotos"]["cuerpo"])])
            v = list(s.values())[0] if s else None
        except Exception:
            v = None
        est = mutar(sid, lambda e: e["chequeo"].update({"misma_persona": v}))
        est = _armar_hoja(sid)
    return est


def _encuadre_cara(img: Image.Image, ruta: str) -> Image.Image:
    """Head and shoulders, the same way for every client: a 3:4 window 2.6x the face
    box, the face a little above centre. A selfie at arm's length and a portrait from
    across the room come out framed alike. No face found: the photo as it is."""
    try:
        filas = C._correr([C.FACE_PY, "-W", "ignore", C.FACEID, "--puntos", ruta])
        caja = next((f.get("box") for f in filas if f.get("box")), None)
    except Exception:
        caja = None
    if not caja:
        return img
    x0, y0, x1, y1 = caja
    lado = max(x1 - x0, y1 - y0)
    h = lado * 2.6
    w = h * 3 / 4
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # stay inside the photo; if the window is larger than the photo, shrink it
    k = min(1.0, img.width / w, img.height / h)
    w, h = w * k, h * k
    l = min(max(0, cx - w / 2), img.width - w)
    t = min(max(0, cy - 0.45 * h), img.height - h)      # the face just above centre
    return img.crop((int(l), int(t), int(l + w), int(t + h)))


def _encuadre_cuerpo(img: Image.Image) -> Image.Image:
    """The whole person, filling the height: the DWPose skeleton's extent plus a margin
    (more below, for the feet the skeleton stops at the ankles), cropped out of the
    photo -- never stretched. A full-length taken from far away comes out as large as
    one taken close. No person found: the photo as it is."""
    try:
        import numpy as np
        from .pose import esqueleto
        red = img.copy()
        red.thumbnail((768, 768))
        sk = esqueleto(red)
        if sk is None:
            return img
        ys, xs = np.nonzero(np.asarray(sk.convert("L")) > 30)
        f = img.width / red.width
        x0, x1, y0, y1 = xs.min() * f, xs.max() * f, ys.min() * f, ys.max() * f
    except Exception:
        return img
    alto = y1 - y0
    t = max(0, y0 - 0.12 * alto)
    b = min(img.height, y1 + 0.10 * alto)
    h = b - t
    w = max(h * 0.5, (x1 - x0) * 1.25)          # at least 1:2, wider for arms out
    cx = (x0 + x1) / 2
    l = min(max(0, cx - w / 2), max(0, img.width - w))
    return img.crop((int(l), int(t), int(min(img.width, l + w)), int(b)))


def _armar_hoja(sid: str) -> dict:
    """Both photos are in: stitch the character sheet ourselves (the user's idea,
    2026-09-26), the same normalised layout for everyone -- close-up left, full body
    right, both the sheet's full height (caras.hoja_identidad). The close-up crop is
    also what the likeness score and Enhance compare against."""
    est = leer(sid)
    cara_f = _ruta(sid, est["fotos"].get("cara_original") or est["fotos"]["cara"])
    cuerpo_f = _ruta(sid, est["fotos"]["cuerpo"])
    cara = _encuadre_cara(Image.open(cara_f).convert("RGB"), cara_f)
    cuerpo = _encuadre_cuerpo(Image.open(cuerpo_f).convert("RGB"))
    c2, b2 = _ruta(sid, "entrada", "cara_encuadre.png"), _ruta(sid, "entrada", "cuerpo_encuadre.png")
    cara.save(c2)
    cuerpo.save(b2)
    C.hoja_identidad(c2, b2, _ruta(sid, "entrada", "hoja.png"), alto=1080)

    def f(e):
        e["fotos"].update({"hoja": "entrada/hoja.png", "cara_original": e["fotos"]["cara"],
                           "cara": "entrada/cara_encuadre.png"})
        e["chequeo"]["hoja"] = {"cara": bool(e["chequeo"].get("cara", {}).get("cara", True)),
                                "avisos": [], "tam": "1920x1080", "armada": True}
        e.pop("personaje", None)
        e["caption_persona"] = None
    est = mutar(sid, f)
    p = perfil_de(_personaje(sid, est))
    if p["descripcion"]:
        return mutar(sid, lambda e: e.update({"perfil": p, "caption_persona": p["descripcion"],
                                              "perfil_estado": "listo"}))
    mutar(sid, lambda e: e.update({"perfil": p}))
    return pedir_descripcion(sid)


def guardar_hoja(sid: str, img: Image.Image) -> dict:
    """The client's CHARACTER SHEET: one 16:9 image, close-up and full-length side by side.

    Used as-is as the person reference (the shape measured in pruebas/exp3). The
    close-up the likeness score and Enhance need is cut from it: the largest face the
    detector finds, a square 2.4x its size. A sheet with no detectable face (a 3D
    mannequin, a masked character) still works -- its left half stands in for it.
    """
    from . import optimizar as OP
    img = OP.normalizar(img)
    hoja = _ruta(sid, "entrada", "hoja.png")
    img.save(hoja)
    avisos = []
    if not 1.5 <= img.width / img.height <= 2.1:
        avisos.append("A character sheet is a wide 16:9 image: face on the left, full body on the right.")
    try:
        filas = C._correr([C.FACE_PY, "-W", "ignore", C.FACEID, "--puntos", hoja])
        caja = next((f.get("box") for f in filas if f.get("box")), None)
    except Exception:
        caja = None
    if caja:
        x0, y0, x1, y1 = caja
        lado = max(x1 - x0, y1 - y0) * 2.4
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.1 * lado
        l, t = max(0, int(cx - lado / 2)), max(0, int(cy - lado / 2))
        cara = img.crop((l, t, min(img.width, int(l + lado)), min(img.height, int(t + lado))))
    else:
        cara = img.crop((0, 0, img.width // 2, img.height))
        avisos.append("No face was found on the sheet: the likeness check will be skipped.")
    cara.save(_ruta(sid, "entrada", "cara.png"))

    def f(est):
        est["fotos"].update({"cara": "entrada/cara.png", "cuerpo": "entrada/hoja.png",
                             "hoja": "entrada/hoja.png"})
        est["chequeo"] = {"hoja": {"cara": bool(caja), "avisos": avisos,
                                   "tam": f"{img.width}x{img.height}"}}
        est.pop("personaje", None)
        est["caption_persona"] = None
    est = mutar(sid, f)
    p = perfil_de(_personaje(sid, est))
    if p["descripcion"]:
        return mutar(sid, lambda e: e.update({"perfil": p, "caption_persona": p["descripcion"],
                                              "perfil_estado": "listo"}))
    mutar(sid, lambda e: e.update({"perfil": p}))
    return pedir_descripcion(sid)


def guardar_escena(sid: str, img: Image.Image, nombre: str = "") -> dict:
    """One of the client's own scene photos (the "Upload my images" path)."""
    from . import optimizar as OP
    d = _ruta(sid, "escenas")
    os.makedirs(d, exist_ok=True)
    n = len([x for x in os.listdir(d) if x.endswith(".png")]) + 1
    if n > MAX_ESCENAS:
        raise ValueError(f"up to {MAX_ESCENAS} scene photos per shoot")
    OP.normalizar(img).save(os.path.join(d, f"{n:02d}.png"))

    def f(est):
        est.setdefault("escenas", []).append({"n": n, "nombre": nombre, "archivo": f"escenas/{n:02d}.png"})
    return mutar(sid, f)


def borrar_escenas(sid: str) -> dict:
    import shutil
    shutil.rmtree(_ruta(sid, "escenas"), ignore_errors=True)
    return mutar(sid, lambda e: e.update({"escenas": []}))


def _importar_escenas(sid: str) -> str:
    """The client's own photos become a private package, exactly like a library one:
    DWPose skeleton + Qwen3-VL recipe per photo. Hidden from the library (id u_...)."""
    import shutil, subprocess, sys as _sys
    pid = "u_" + sid.replace("-", "_")
    D = os.path.join(T.CATALOGO, "paquetes", pid)
    os.makedirs(D, exist_ok=True)
    tomas = []
    for e in leer(sid).get("escenas", []):
        tid = f"{e['n']:02d}"
        shutil.copy(_ruta(sid, e["archivo"]), os.path.join(D, tid + ".png"))
        tomas.append({"id": tid, "origen": e.get("nombre", "")})
    json.dump({"id": pid, "label": "My scenes", "privado": True, "tomas": tomas},
              open(os.path.join(D, "paquete.json"), "w", encoding="utf-8"), indent=1)
    her = os.path.join(RAIZ, "herramientas")
    subprocess.run([_sys.executable,os.path.join(her, "esqueletos_paquete.py"), pid], capture_output=True, timeout=1800)
    subprocess.run([_sys.executable, os.path.join(her, "preparar_paquete.py"), pid], capture_output=True,
                   timeout=3600, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return pid


def borrar_foto(sid: str, n: int) -> dict:
    """Delete a photo -- into sesiones/<id>/_papelera/, never gone: restaurar_foto brings it back.
    Every file of that shot moves (raw, identity pass, enhanced, masks)."""
    import glob, shutil
    pap = _ruta(sid, "_papelera")
    os.makedirs(pap, exist_ok=True)
    for f in glob.glob(_ruta(sid, "fotos", f"{n:02d}_*")):
        shutil.move(f, os.path.join(pap, os.path.basename(f)))
    return mutar(sid, lambda e: _toma(e, n).update({"estado": "borrada", "borrada_en": time.time()}))


def restaurar_foto(sid: str, n: int) -> dict:
    import glob, shutil
    for f in glob.glob(_ruta(sid, "_papelera", f"{n:02d}_*")):
        shutil.move(f, _ruta(sid, "fotos", os.path.basename(f)))
    return mutar(sid, lambda e: _toma(e, n).update({"estado": "lista", "borrada_en": None}))


def _personaje(sid: str, e: dict) -> str:
    """Which character a session belongs to: the hash of its close-up (or sheet). Every
    session made from the same photos lands in the same group; cached in estado.json."""
    if e.get("personaje"):
        return e["personaje"]
    import hashlib
    f = e.get("fotos", {}).get("cara") or e.get("fotos", {}).get("hoja")
    if not f or not os.path.exists(_ruta(sid, f)):
        return "sin-" + sid
    h = hashlib.md5(open(_ruta(sid, f), "rb").read()).hexdigest()[:12]
    mutar(sid, lambda x: x.update({"personaje": h}))
    return h


def galeria(limite: int = 400) -> list[dict]:
    """Finished photos from every session, newest first -- read from sesiones/, which is
    where the installed app writes everything it makes. The final (enhanced when there
    is one) and the session it came from."""
    out = []
    if not os.path.isdir(SESIONES):
        return out
    paquetes = {p["id"]: p["label"] for p in T.paquetes()}
    for sid in sorted(os.listdir(SESIONES), reverse=True):
        if sid.startswith("_"):
            continue
        try:
            e = leer(sid)
        except Exception:
            continue
        el = e.get("eleccion") or {}
        origen = (paquetes.get(el.get("paquete"), el.get("paquete")) if el.get("paquete")
                  else "Own scenes" if el.get("escenas_propias") else "Custom shoot")
        for t in e.get("tomas", []):
            if t.get("estado") != "lista" or not t.get("final"):
                continue
            if not os.path.exists(_ruta(sid, t["final"])):
                continue
            out.append({"sesion": sid, "n": t["n"], "archivo": f"/sesiones/{sid}/{t['final']}",
                         "personaje": _personaje(sid, e), "descripcion": e.get("caption_persona") or "",
                         "mejorada": bool(t.get("mejorada")), "favorita": bool(t.get("favorita")),
                         "origen": origen, "fecha": e.get("fin") or e.get("creada"),
                         "cliente": f"/sesiones/{sid}/{e['fotos'].get('cara')}" if e.get("fotos", {}).get("cara") else None})
            if len(out) >= limite:
                return out
    return out


def _nombres() -> dict:
    f = os.path.join(SESIONES, "_personajes.json")
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def perfil_de(pid: str) -> dict:
    v = _nombres().get(pid) or {}
    return {"nombre": v, "descripcion": ""} if isinstance(v, str) else {"nombre": "", "descripcion": ""} | v


def guardar_perfil(pid: str, **campos) -> dict:
    with _lock:
        d = _nombres()
        p = perfil_de(pid)
        for k, v in campos.items():
            if v is not None:
                p[k] = v.strip()[:60 if k == "nombre" else 400]
        d[pid] = p
        json.dump(d, open(os.path.join(SESIONES, "_personajes.json"), "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
    return p


def nombrar_personaje(pid: str, nombre: str) -> dict:
    guardar_perfil(pid, nombre=nombre)
    return {"ok": True}


def perfil(sid: str, nombre: str | None = None, descripcion: str | None = None) -> dict:
    """The client's profile for this session: a name and the one-line description that
    goes after every prompt. Kept per character, so the same sheet comes back filled in.
    An edited description replaces the LLM's for this session."""
    pid = _personaje(sid, leer(sid))
    p = guardar_perfil(pid, nombre=nombre, descripcion=descripcion)
    if descripcion is not None:
        mutar(sid, lambda e: e.update({"caption_persona": _pulir(descripcion), "perfil_estado": "listo"}))
    return mutar(sid, lambda e: e.update({"perfil": p}))


def pedir_descripcion(sid: str) -> dict:
    """Ask the LLM to describe the client (async; the session's perfil_estado says when)."""
    est = mutar(sid, lambda e: e.update({"perfil_estado": "describiendo", "caption_persona": None}))
    _urgentes.put(sid)
    _cola.put(("despertar",))
    return est


def _atender_urgentes() -> None:
    while True:
        try:
            sid = _urgentes.get_nowait()
        except queue.Empty:
            return
        try:
            txt = _caption_persona(sid)
            guardar_perfil(_personaje(sid, leer(sid)), descripcion=txt)
            mutar(sid, lambda e: e.update({"perfil_estado": "listo" if txt else "fallo",
                                           "perfil": perfil_de(_personaje(sid, e))}))
        except Exception as ex:
            print("[photobook] describe failed:", ex, flush=True)
            try:        # the session may be gone (deleted meanwhile): never kill the worker
                mutar(sid, lambda e: e.update({"perfil_estado": "fallo"}))
            except Exception:
                pass


ACTIVAS = ("en_cola", "preparando", "leyendo_escenas", "trabajando")


def sesiones_de(pid: str) -> list[str]:
    out = []
    for sid in sorted(os.listdir(SESIONES)):
        if sid.startswith("_") or not os.path.isdir(os.path.join(SESIONES, sid)):
            continue
        try:
            if _personaje(sid, leer(sid)) == pid:
                out.append(sid)
        except Exception:
            pass
    return out


def borrar_personaje(pid: str) -> dict:
    """Delete a character: every shoot made with it moves to sesiones/_papelera/, whole
    (sheet, photos, enhanced versions). Nothing is erased -- Undo moves them back.
    Refused while one of its shoots is still running."""
    sids = sesiones_de(pid)
    ocupadas = [s for s in sids if s == _activo["id"] or leer(s).get("fase") in ACTIVAS]
    if ocupadas:
        raise ValueError("this character has a shoot in progress -- stop it first")
    dest = os.path.join(SESIONES, "_papelera")
    os.makedirs(dest, exist_ok=True)
    with _lock:
        for sid in sids:
            shutil.move(os.path.join(SESIONES, sid), os.path.join(dest, sid))
    return {"ok": True, "sesiones": sids}


def restaurar_personaje(sids: list[str]) -> dict:
    with _lock:
        for sid in sids:
            src = os.path.join(SESIONES, "_papelera", os.path.basename(sid))
            if os.path.isdir(src) and not os.path.exists(os.path.join(SESIONES, os.path.basename(sid))):
                shutil.move(src, os.path.join(SESIONES, os.path.basename(sid)))
    return {"ok": True}


def personajes() -> list[dict]:
    '''The gallery's first level: one card per character, newest activity first.'''
    grupos = {}
    for g in galeria(limite=100000):
        c = grupos.setdefault(g["personaje"], {"id": g["personaje"], "cara": g["cliente"], "fotos": 0,
                                               "sesiones": set(), "portadas": [], "fecha": 0,
                                               "descripcion": "", "mejoradas": 0})
        c["fotos"] += 1
        c["mejoradas"] += g["mejorada"]
        c["sesiones"].add(g["sesion"])
        c["fecha"] = max(c["fecha"], g["fecha"] or 0)
        c["descripcion"] = c["descripcion"] or g["descripcion"]
        if len(c["portadas"]) < 4:
            c["portadas"].append(g["archivo"])
    out = []
    nombres = _nombres()
    for c in grupos.values():
        c["sesiones"] = len(c["sesiones"])
        c["nombre"] = perfil_de(c["id"])["nombre"]
        c["descripcion"] = perfil_de(c["id"])["descripcion"] or c["descripcion"]
        out.append(c)
    return sorted(out, key=lambda c: -c["fecha"])


def estimar(n: int) -> int:
    return int(n * (SEG_COMPONER + SEG_REFORZAR))


def encolar(sid: str, eleccion: dict, total: int = 30) -> dict:
    cat = T.catalogo()
    if eleccion.get("escenas_propias"):
        tomas = []                    # planned by the worker once the photos are read
        if not leer(sid).get("escenas"):
            raise ValueError("add your scene photos first")
    elif eleccion.get("paquete"):
        tomas = T.planificar_paquete(eleccion["paquete"])
        if eleccion.get("tomas"):
            # the client left some photos out in the preview
            quiero = set(eleccion["tomas"])
            tomas = [t for t in tomas if t["id_muestra"] in quiero]
            for k, t in enumerate(tomas, 1):
                t["n"] = k
            if not tomas:
                raise ValueError("pick at least one photo")
    else:
        tomas = T.planificar(cat, eleccion, total=total,
                             semilla=int(eleccion.get("semilla") or (int(time.time()) % 90000)),
                             pose_en_texto=CALIDAD["pose_en_texto"])
    for t in tomas:
        t.update({"estado": "pendiente", "bruto": None, "final": None,
                  "id_bruto": None, "id_final": None, "reforzada": False})

    def f(est):
        if not est["fotos"].get("cara") or not est["fotos"].get("cuerpo"):
            raise ValueError("both photos are needed first")
        est.update({"eleccion": eleccion, "tomas": tomas, "fase": "en_cola", "error": "",
                    "encolada": time.time(),
                    "estimado_s": estimar(len(tomas) or len(est.get("escenas", [])))})
    est = mutar(sid, f)
    _cola.put(sid)
    return est


def cancelar(sid: str) -> None:
    _cancelar.add(sid)


def reanudar_pendientes() -> None:
    """Sessions that were running when the server stopped go back in the queue."""
    if not os.path.isdir(SESIONES):
        return
    for sid in sorted(os.listdir(SESIONES)):
        try:
            est = leer(sid)
        except Exception:
            continue
        if est.get("fase") in ("en_cola", "preparando", "trabajando"):
            _cola.put(sid)


# ------------------------------------------------------------------ worker

def _vestuario_propio(sid: str, est: dict) -> str:
    """What the client wears in the full-length photo, in a dozen words."""
    txt = Q.describir(_ruta(sid, est["fotos"]["cuerpo"]),
                      "Describe only the clothing and shoes this person wears, as a short "
                      "comma-separated list of garments with their colours, max 20 words. "
                      "No people, no background.", max_tokens=60)
    Q.liberar_vision()
    return txt.strip().rstrip(".")


import re as _re
_PELO = _re.compile(r"\b(hair|hairstyle|curls?|braids?|ponytail|bangs|fringe|locks)\b", _re.I)


def _sin_pelo(prompt: str) -> str:
    """Drop the recipe clauses that describe hair. The client's hair is theirs -- it comes
    from the sheet and the caption -- but a recipe read from the sample says "hair spread
    out" or "hair blown back", and the model obeys it: a bald client and a mannequin grew
    hair on exactly those shots (pruebas/exp24, exp26)."""
    partes = [x for x in _re.split(r"(?<=[,.;])\s+", prompt) if not _PELO.search(x)]
    return " ".join(partes)


PREGUNTA_PERSONA = (
    "This character sheet shows one subject twice: a close-up and a full-length view. Describe the "
    "subject in ONE sentence of at most 30 words, for an image generator: what it is (a person, or "
    "e.g. a 3D mannequin), apparent age and gender if a person, hair (colour, length, style, or bald), "
    "facial hair, skin tone, and body build. Never mention clothing, pose, background or light. "
    "Start with 'The subject is'.")


def _caption_persona(sid: str) -> str:
    """One line describing the client -- hair, beard, age, build, never clothes.

    The user's idea (2026-09-26). The sheet is the identity reference, but two things
    escaped it: a package recipe that mentions hair gave a bald client hair ("hair
    spread out", "hair blown back"), and a 3D mannequin came back as a bald person.
    Saying in words what the subject is, next to every prompt, answers both.
    """
    est = leer(sid)
    if est.get("caption_persona") is not None:
        return est["caption_persona"]
    try:
        txt = Q.describir(_ruta(sid, est["fotos"].get("hoja") or est["fotos"]["cara"]),
                          PREGUNTA_PERSONA, max_tokens=80).strip().replace("\n", " ")
        Q.liberar_vision()
    except Exception as ex:
        print("[photobook] caption failed:", ex, flush=True)
        txt = ""
    txt = _pulir(txt)
    mutar(sid, lambda e: e.update({"caption_persona": txt}))
    return txt


def _pulir(txt: str) -> str:
    txt = " ".join((txt or "").split())
    if txt and not txt.lower().startswith("the subject"):
        txt = "The subject is " + txt[0].lower() + txt[1:]
    return txt.rstrip(".") + "." if txt else ""


def _procesar(sid: str) -> None:
    est = leer(sid)
    el = est["eleccion"]
    cara = _ruta(sid, est["fotos"]["cara"])
    cuerpo = _ruta(sid, est["fotos"]["cuerpo"])
    cat = T.catalogo()
    # One reference for the person: close-up and full-length side by side on a
    # 16:9 sheet. Measured in pruebas/exp3 against choosing one photo per
    # framing: 0.74 against 0.70 full-length, 0.88 against 0.89 waist-up, and
    # the person is not duplicated.
    hoja = _ruta(sid, "entrada", "hoja.png")
    if not os.path.exists(hoja):
        C.hoja_identidad(cara, cuerpo, hoja)

    mutar(sid, lambda e: e.update({"fase": "preparando", "inicio": e.get("inicio") or time.time()}))
    if el.get("escenas_propias") and not leer(sid)["tomas"]:
        mutar(sid, lambda e: e.update({"fase": "leyendo_escenas"}))
        pid = _importar_escenas(sid)
        nuevas = T.planificar_paquete(pid)
        for t in nuevas:
            t.update({"estado": "pendiente", "bruto": None, "final": None,
                      "id_bruto": None, "id_final": None, "reforzada": False})
        mutar(sid, lambda e: e.update({"tomas": nuevas, "paquete_privado": pid, "fase": "preparando",
                                        "estimado_s": estimar(len(nuevas))}))
    # the client's identity as a written checklist, once per session, for the fal
    # face pass -- the face's equivalent of the SUNBURST prompt's SKU inventory
    ficha = leer(sid).get("ficha_identidad")
    if CALIDAD["cara_motor"] == "fal" and CALIDAD["cara_auto"] and not ficha:
        try:
            from . import lectura as L
            ficha = {k: v for k, v in L.leer_identidad(cara).items() if not k.startswith("_")}
            Q.liberar_vision()
        except Exception as ex:
            print("[photobook] identity checklist failed:", ex, flush=True)
            ficha = {}
        mutar(sid, lambda e: e.update({"ficha_identidad": ficha}))
    if el.get("vestuario") == "own" and not el.get("vestuario_texto"):
        propio = _vestuario_propio(sid, est)
        el["vestuario_texto"] = propio or "the same outfit as in the full-length photo"

        def f(e):
            e["eleccion"]["vestuario_texto"] = el["vestuario_texto"]
            for t in e["tomas"]:
                if not t.get("pose"):
                    continue
                pose = next(p for p in cat["poses"] if p["id"] == t["pose"])
                t["prompt"], t["ratio"] = T.prompt_toma(cat, e["eleccion"], pose, CALIDAD["pose_en_texto"])
        mutar(sid, f)

    caption = _caption_persona(sid) if CALIDAD["caption_persona"] else ""
    mutar(sid, lambda e: e.update({"fase": "trabajando"}))
    ns = [t["n"] for t in leer(sid)["tomas"] if t["estado"] not in ("lista", "borrada")]
    # the first block is short so the client sees finished photos in minutes
    bloques = [ns[:2]] + [ns[i:i + BLOQUE] for i in range(2, len(ns), BLOQUE)] if ns else []
    for i_b, bloque in enumerate(bloques):
        if i_b:
            time.sleep(DESCANSO_S)

        # 1. compose
        for n in bloque:
            if sid in _cancelar:
                raise InterruptedError
            _atender_urgentes()
            t = next(x for x in leer(sid)["tomas"] if x["n"] == n)
            if t.get("bruto") and os.path.exists(_ruta(sid, t["bruto"])):
                # resumed after a restart: composed already, redo what follows
                mutar(sid, lambda e: _toma(e, n).update({"estado": "compuesta"}))
                continue
            mutar(sid, lambda e: _toma(e, n).update({"estado": "componiendo", "t0": time.time()}))
            dest = _ruta(sid, "fotos", f"{n:02d}_raw.png")
            try:
                if t.get("esqueleto"):
                    # a package shot: the sample's skeleton + its recipe (R3)
                    esq = t["esqueleto"]
                elif t.get("pose") and not CALIDAD["pose_en_texto"]:
                    esq = os.path.join(T.CATALOGO, "poses", t["pose"] + ".png")
                else:
                    esq = None
                prompt = (_sin_pelo(t["prompt"]).rstrip() + " " + caption).strip()
                if t.get("esqueleto"):
                    # the sheet shows the client twice (close-up + full body); a package shot
                    # once came back with both (manga, pruebas/exp29)
                    prompt += " The subject appears once."
                r = Q.generar(dest, prompt=prompt, personas=[hoja], pose=esq,
                              ratio=t["ratio"], steps=CALIDAD["pasos"], seed=t["seed"],
                              megapixeles=CALIDAD["mp_esqueleto"] if esq else CALIDAD["mp_texto"])
                mutar(sid, lambda e: _toma(e, n).update({
                    "estado": "compuesta", "bruto": f"fotos/{n:02d}_raw.png",
                    "final": f"fotos/{n:02d}_raw.png", "s_componer": r["segundos"],
                    "tam": r["tam"]}))
            except Exception as ex:
                mutar(sid, lambda e: _toma(e, n).update({"estado": "fallida", "error": str(ex)[:300]}))

        # 2. score what was composed; the strong ones are finished already
        hechas = [x for x in leer(sid)["tomas"] if x["n"] in bloque and x["estado"] == "compuesta"]
        if not hechas:
            continue
        try:
            sc0 = C.identidad([cara], [_ruta(sid, x["bruto"]) for x in hechas])
        except Exception:
            sc0 = {}

        def primera(e):
            for x in hechas:
                t = _toma(e, x["n"])
                t["id_bruto"] = sc0.get(os.path.normcase(os.path.abspath(_ruta(sid, x["bruto"]))))
                if not CALIDAD["cara_auto"] and not CALIDAD["forzar_cara"]:
                    t.update({"estado": "lista", "id_final": t["id_bruto"], "t1": time.time()})
                elif (not CALIDAD["forzar_cara"] and t["id_bruto"] is not None
                        and t["id_bruto"] >= YA_PARECIDO):
                    t.update({"estado": "lista", "id_final": t["id_bruto"],
                              "nota": "Already a strong likeness", "t1": time.time()})
        mutar(sid, primera)
        hechas = [x for x in leer(sid)["tomas"] if x["n"] in bloque and x["estado"] == "compuesta"]
        if not hechas:
            continue

        # 3. faces, all of the block in one SAM 3 process
        mutar(sid, lambda e: [_toma(e, x["n"]).update({"estado": "buscando_cara"}) for x in hechas])
        brutos = [_ruta(sid, x["bruto"]) for x in hechas]
        try:
            mas = C.mascaras(brutos, texto=CALIDAD["cara_sam"] if CALIDAD["cara_motor"] == "fal" else "face")
        except Exception as ex:
            mas = {}
            print("[photobook] SAM 3 failed:", ex, flush=True)
        mutar(sid, lambda e: [_toma(e, x["n"]).update({"estado": "cola_cara"}) for x in hechas])

        # 4. rebuild each face
        for x in hechas:
            if sid in _cancelar:
                raise InterruptedError
            n = x["n"]
            src = _ruta(sid, x["bruto"])
            m = mas.get(os.path.normcase(os.path.abspath(src)))
            if not m or m.get("coverage", 0) <= 0.0005:
                mutar(sid, lambda e: _toma(e, n).update({"estado": "lista", "nota": "no face found"}))
                continue
            mutar(sid, lambda e: _toma(e, n).update({"estado": "reforzando"}))
            dest = _ruta(sid, "fotos", f"{n:02d}_face.png")
            try:
                if CALIDAD["cara_motor"] == "fal":
                    r = DT.reforzar_fal(src, m["mask"], [cara], dest, ficha=ficha,
                                        expresion=x.get("expresion", ""), luz=x.get("luz", ""))
                    if CALIDAD["pasada_banda"]:
                        rb = DT.pasada_banda(dest, m["mask"], dest)
                        r["segundos"] = round((r.get("segundos") or 0) + (rb.get("segundos") or 0), 1)
                else:
                    r = C.reforzar(src, m["mask"], cara, dest, seed=x["seed"] + 1,
                                   steps=CALIDAD["pasos_cara"],
                                   **({"prompt": x["cara_prompt"]} if x.get("cara_prompt") else {}))
                if r.get("error"):
                    raise RuntimeError(r["error"])
                mutar(sid, lambda e: _toma(e, n).update({
                    "estado": "puntuando",
                    "reforzada_archivo": f"fotos/{n:02d}_face.png", "s_reforzar": r["segundos"]}))
            except Exception as ex:
                mutar(sid, lambda e: _toma(e, n).update({"estado": "lista", "nota": f"face pass failed: {str(ex)[:200]}"}))

        # 5. score the rebuilt ones and keep the better version
        numeros = {x["n"] for x in hechas}
        tomas_b = [t for t in leer(sid)["tomas"] if t["n"] in numeros and t.get("reforzada_archivo")]
        archivos = [_ruta(sid, t["reforzada_archivo"]) for t in tomas_b]
        try:
            sc = C.identidad([cara], archivos)
        except Exception:
            sc = {}

        def puntuar(e):
            for t in e["tomas"]:
                if t["n"] not in numeros or not t.get("bruto"):
                    continue
                k = lambda p: os.path.normcase(os.path.abspath(_ruta(sid, p)))
                if t.get("reforzada_archivo"):
                    t["id_reforzada"] = sc.get(k(t["reforzada_archivo"]))
                    a, b_ = t["id_bruto"], t["id_reforzada"]
                    usar = b_ is not None and (a is None or b_ >= a - TOLERANCIA)
                    t["reforzada"] = bool(usar)
                    t["final"] = t["reforzada_archivo"] if usar else t["bruto"]
                    t["id_final"] = b_ if usar else a
                else:
                    t["id_final"] = t["id_bruto"]
                t["estado"] = "lista"
                t["t1"] = time.time()
        mutar(sid, puntuar)

    mutar(sid, lambda e: e.update({"fase": "lista", "fin": time.time()}))


def _toma(est, n):
    return next(t for t in est["tomas"] if t["n"] == n)


def pedir_mejora(sid: str, n: int) -> dict:
    """Queue "Enhance face" for one finished photo."""
    def f(e):
        t = _toma(e, n)
        if t["estado"] != "lista":
            raise ValueError("that photo is not finished yet")
        t.update({"estado": "en_cola_mejora", "nota_mejora": ""})
    est = mutar(sid, f)
    _cola.put(("mejorar", sid, n))
    return est


def _mejorar(sid: str, n: int) -> None:
    """Enhance = W2 (pruebas/exp20, the user's pick): the whole photo, no mask.
    1. identity pass at 1 MP -- the photo + the client's close-up, the expression kept
    2. 2K upscale of that result -- QwenStudio's upscale, like qwen212KUpscale_v10
    No crop and no stitch, so no seam, feather or ghost is possible."""
    est = leer(sid)
    t = _toma(est, n)
    cara = _ruta(sid, est["fotos"]["cara"])
    src = _ruta(sid, t["bruto"])
    mutar(sid, lambda e: _toma(e, n).update({"estado": "mejorando"}))
    t0 = time.time()
    paso1 = _ruta(sid, "fotos", f"{n:02d}_id.png")
    dest = _ruta(sid, "fotos", f"{n:02d}_enh.png")
    semilla = int(t["seed"]) + 3
    DT.entero(src, paso1, referencia=cara, expresion=t.get("expresion", ""), seed=semilla)
    r = DT.entero(paso1, dest, seed=semilla)
    sc = C.identidad([cara], [paso1, dest])
    k = lambda f: sc.get(os.path.normcase(os.path.abspath(f)))
    mutar(sid, lambda e: _toma(e, n).update({
        "estado": "lista", "final": f"fotos/{n:02d}_enh.png", "reforzada": True, "mejorada": True,
        "id_paso1": k(paso1), "id_reforzada": k(dest), "id_final": k(dest), "tam": r.get("tam"),
        "s_reforzar": round(time.time() - t0, 1), "metodo_mejora": "W2"}))


def _bucle():
    while True:
        item = _cola.get()
        _atender_urgentes()
        if isinstance(item, tuple) and item[0] == "despertar":
            continue
        if isinstance(item, tuple) and item[0] == "mejorar":
            _, sid, n = item
            _activo["id"] = sid
            try:
                _mejorar(sid, n)
            except Exception as ex:
                traceback.print_exc()
                mutar(sid, lambda e: _toma(e, n).update({"estado": "lista",
                                                         "nota_mejora": f"enhance failed: {str(ex)[:200]}"}))
            finally:
                _activo["id"] = None
            continue
        sid = item
        _activo["id"] = sid
        try:
            _procesar(sid)
        except InterruptedError:
            mutar(sid, lambda e: e.update({"fase": "cancelada"}))
        except Exception as ex:
            traceback.print_exc()
            mutar(sid, lambda e: e.update({"fase": "error", "error": str(ex)[:500]}))
        finally:
            _cancelar.discard(sid)
            _activo["id"] = None


def arrancar() -> None:
    os.makedirs(SESIONES, exist_ok=True)
    threading.Thread(target=_bucle, daemon=True, name="photobook-worker").start()
    reanudar_pendientes()


def cola_info() -> dict:
    return {"activo": _activo["id"], "en_espera": _cola.qsize()}
