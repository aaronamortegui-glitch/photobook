"""Review sheets for any session: full frames (sample / raw / final) and face detail.

    python herramientas/hoja_sesion.py <session id> [label]
Faces are cropped from the face detector's box (W2 leaves no mask). Writes
pruebas/rev_<label>_completas.jpg and pruebas/rev_<label>_caras.jpg.
"""
import json, os, sys
from PIL import Image
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ); sys.path.insert(0, os.path.join(RAIZ, "herramientas"))
from photobook import caras as C
from hoja import hoja

sid = sys.argv[1]
lbl = sys.argv[2] if len(sys.argv) > 2 else sid[-6:]
S = os.path.join(RAIZ, "sesiones", sid)
e = json.load(open(os.path.join(S, "estado.json"), encoding="utf-8"))
comp, fins = [], []
for t in e["tomas"]:
    n = f"{t['n']:02d}"
    raw = os.path.join(S, t["bruto"]) if t.get("bruto") else None
    fin = os.path.join(S, t["final"]) if t.get("final") else raw
    if not raw or not os.path.exists(raw):
        continue
    muestra = os.path.join(RAIZ, t["muestra"].lstrip("/")) if t.get("muestra") else None
    ib, ifn = t.get("id_bruto"), t.get("id_final")
    if muestra:
        comp.append((f"{n} sample", muestra))
    comp.append((f"{n} raw" + (f" {ib:.2f}" if ib is not None else ""), raw))
    comp.append((f"{n} {'ENHANCED' if t.get('mejorada') else 'final'}" + (f" {ifn:.2f}" if ifn is not None else ""), fin))
    fins.append((n, fin))
filas = C._correr([C.FACE_PY, "-W", "ignore", C.FACEID, "--puntos"] + [os.path.abspath(f) for _, f in fins])
bx = {os.path.normcase(f["image"]): f.get("box") for f in filas}
caras = [("client", os.path.join(S, e["fotos"]["cara"]))]
for n, f in fins:
    b = bx.get(os.path.normcase(os.path.abspath(f)))
    if not b:
        caras.append((f"{n} no face", f)); continue
    im = Image.open(f).convert("RGB")
    x0, y0, x1, y1 = b; s = max(x1 - x0, y1 - y0) * 2.0; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    c = os.path.join(S, "fotos", f"_rev_{n}.png")
    im.crop((int(max(0, cx - s / 2)), int(max(0, cy - s / 2)), int(min(im.width, cx + s / 2)),
             int(min(im.height, cy + s / 2)))).resize((260, 260), Image.LANCZOS).save(c)
    caras.append((n, c))
cols = 9 if any(t.get("muestra") for t in e["tomas"]) else 8
hoja(os.path.join(RAIZ, "pruebas", f"rev_{lbl}_completas.jpg"), comp, cols=cols, alto=420)
hoja(os.path.join(RAIZ, "pruebas", f"rev_{lbl}_caras.jpg"), caras, cols=11, alto=260)
print("ok", lbl)
