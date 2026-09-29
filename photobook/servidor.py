"""Photobook HTTP server: the page, the catalogue, sessions, and their files.

    .venv of QwenStudio:  python -m photobook.servidor      -> http://127.0.0.1:7870

QwenStudio must be running on 7860; this server never loads a model itself.
"""
from __future__ import annotations

import base64
import io
import json
import mimetypes
import os
import sys
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from PIL import Image

from . import motor_qwen as Q
from . import servicio as S
from . import tomas as T

RAIZ = S.RAIZ
WEB = os.path.join(RAIZ, "photobook", "web")
PUERTO = int(os.environ.get("PHOTOBOOK_PORT", "7870"))


def _img(data_url: str) -> Image.Image:
    b = base64.b64decode(data_url.split(",", 1)[1])
    from . import optimizar as OP
    return OP.normalizar(Image.open(io.BytesIO(b)))


def _publico(est: dict) -> dict:
    """What the page needs, with paths turned into URLs."""
    sid = est["id"]
    u = lambda p: f"/sesiones/{sid}/{p}" if p else None
    out = dict(est)
    out["fotos"] = {k: u(v) for k, v in est.get("fotos", {}).items()}
    tomas = []
    for t in est.get("tomas", []):
        t = dict(t)
        for k in ("bruto", "final", "reforzada_archivo"):
            t[k] = u(t.get(k))
        tomas.append(t)
    out["tomas"] = tomas
    out["escenas"] = [dict(e, archivo=u(e["archivo"])) for e in est.get("escenas", [])]
    out["cola"] = S.cola_info()
    return out


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _archivo(self, ruta):
        ruta = os.path.abspath(ruta)
        if not (ruta.startswith(os.path.abspath(RAIZ)) and os.path.isfile(ruta)):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        with open(ruta, "rb") as f:
            self._send(200, f.read(), ctype)

    def do_GET(self):
        p = unquote(urlparse(self.path).path)
        if p in ("/", "/index.html"):
            return self._archivo(os.path.join(WEB, "index.html"))
        if p.startswith("/web/"):
            return self._archivo(os.path.join(WEB, p[5:]))
        if p.startswith("/mini/"):
            # /mini/<catalogo|sesiones path>?w=480 -> cached JPEG thumbnail (optimizar.mini)
            from urllib.parse import parse_qs
            from . import optimizar as OP
            rel = p[len("/mini/"):]
            ruta = os.path.abspath(os.path.join(RAIZ, rel))
            if not (rel.startswith(("catalogo/", "sesiones/")) and ruta.startswith(os.path.abspath(RAIZ))
                    and os.path.isfile(ruta)):
                return self._send(404, {"error": "not found"})
            w = int((parse_qs(urlparse(self.path).query).get("w") or ["480"])[0])
            return self._archivo(OP.mini(ruta, w))
        if p.startswith("/catalogo/"):
            return self._archivo(os.path.join(RAIZ, p.lstrip("/")))
        if p.startswith("/sesiones/"):
            return self._archivo(os.path.join(RAIZ, p.lstrip("/")))
        if p == "/api/catalogo":
            return self._send(200, T.catalogo())
        if p == "/api/motor":
            try:
                e = Q.estado()
                return self._send(200, {"ok": bool(e.get("pesos_listos")), "perfil": e.get("perfil"),
                                        "cola": S.cola_info()})
            except Exception as ex:
                return self._send(200, {"ok": False, "error": f"QwenStudio is not answering on {Q.URL}: {ex}"})
        if p.startswith("/api/sesion/"):
            partes = p.split("/")
            sid = partes[3]
            if len(partes) == 5 and partes[4] == "zip":
                return self._zip(sid)
            try:
                return self._send(200, _publico(S.leer(sid)))
            except FileNotFoundError:
                return self._send(404, {"error": "no such session"})
        if p == "/api/personajes":
            return self._send(200, S.personajes())
        if p == "/api/galeria":
            return self._send(200, S.galeria())
        if p == "/api/sesiones":
            filas = []
            if os.path.isdir(S.SESIONES):
                for sid in [x for x in sorted(os.listdir(S.SESIONES), reverse=True) if not x.startswith("_")][:30]:
                    try:
                        e = S.leer(sid)
                        filas.append({"id": sid, "fase": e["fase"], "creada": e["creada"],
                                      "n": len(e["tomas"]),
                                      "listas": sum(t["estado"] == "lista" for t in e["tomas"])})
                    except Exception:
                        pass
            return self._send(200, filas)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        b = json.loads(self.rfile.read(n).decode() or "{}") if n else {}
        try:
            if p == "/api/sesion":
                return self._send(200, _publico(S.nueva(desde=b.get("desde"))))
            if p == "/api/personaje/restaurar":
                return self._send(200, S.restaurar_personaje(b.get("sesiones", [])))
            if p.startswith("/api/personaje/") and p.endswith("/borrar"):
                return self._send(200, S.borrar_personaje(p.split("/")[3]))
            if p.startswith("/api/personaje/") and p.endswith("/nombre"):
                return self._send(200, S.nombrar_personaje(p.split("/")[3], b.get("nombre", "")))
            partes = p.split("/")
            if p.startswith("/api/sesion/") and len(partes) == 5:
                sid, accion = partes[3], partes[4]
                if accion == "hoja":
                    return self._send(200, _publico(S.guardar_hoja(sid, _img(b["imagen"]))))
                if accion == "perfil":
                    return self._send(200, _publico(S.perfil(sid, b.get("nombre"), b.get("descripcion"),
                                                                    lora=b.get("lora"), trigger=b.get("trigger"))))
                if accion == "describir":
                    return self._send(200, _publico(S.pedir_descripcion(sid)))
                if accion == "escena":
                    return self._send(200, _publico(S.guardar_escena(sid, _img(b["imagen"]), b.get("nombre", ""))))
                if accion == "escenas_borrar":
                    return self._send(200, _publico(S.borrar_escenas(sid)))
                if accion == "foto":
                    est = S.guardar_foto(sid, b["cual"], _img(b["imagen"]))
                    return self._send(200, _publico(est))
                if accion == "generar":
                    est = S.encolar(sid, b["eleccion"], total=int(b.get("total", 30)))
                    return self._send(200, _publico(est))
                if accion == "mejorar":
                    est = S.pedir_mejora(sid, int(b["n"]))
                    return self._send(200, _publico(est))
                if accion == "cancelar":
                    S.cancelar(sid)
                    return self._send(200, {"ok": True})
                if accion == "borrar":
                    return self._send(200, _publico(S.borrar_foto(sid, int(b["n"]))))
                if accion == "restaurar":
                    return self._send(200, _publico(S.restaurar_foto(sid, int(b["n"]))))
                if accion == "favorita":
                    num, val = int(b["n"]), bool(b.get("valor", True))
                    est = S.mutar(sid, lambda e: next(t for t in e["tomas"] if t["n"] == num)
                                  .update({"favorita": val}))
                    return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as ex:
            return self._send(200, {"error": str(ex)})

    def _zip(self, sid):
        est = S.leer(sid)
        buf = io.BytesIO()
        solo_fav = any(t.get("favorita") for t in est["tomas"])
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
            for t in est["tomas"]:
                if t.get("estado") == "lista" and t.get("final") and (not solo_fav or t.get("favorita")):
                    f = os.path.join(S.SESIONES, sid, t["final"])
                    im = Image.open(f).convert("RGB")
                    jb = io.BytesIO()
                    im.save(jb, "JPEG", quality=94)
                    z.writestr(f"photobook_{t['n']:02d}.jpg", jb.getvalue())
        self._send(200, buf.getvalue(), "application/zip",
                   {"Content-Disposition": f'attachment; filename="photobook_{sid}.zip"'})


def main():
    # PHOTOBOOK_SOLO_WEB=1: the page and the API without the worker -- to try the
    # interface while another instance is generating (nothing it queues will run)
    if os.environ.get("PHOTOBOOK_SOLO_WEB") != "1":
        S.arrancar()
    srv = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    print(f"Photobook on http://127.0.0.1:{PUERTO}  (engine: {Q.URL})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
