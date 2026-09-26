"""Generate the catalogue with the same model the photoshoot uses.

Thumbnails for concepts, places, light and wardrobe, and source photographs for
the new poses (their skeletons are extracted afterwards by build_poses.py).
Skips anything already on disk, so it can be rerun after adding an entry.
16 steps: nothing here has to hold a face, and 16 is where texture resolves.
"""
import json, os, sys, time
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook import motor_qwen as Q

CAT = os.path.join(RAIZ, "catalogo")
cat = json.load(open(os.path.join(CAT, "catalogo.json"), encoding="utf-8"))

POSES_NUEVAS = json.load(open(os.path.join(CAT, "poses", "nuevas.json"), encoding="utf-8"))

trabajos = []
for grupo in ("conceptos", "ambientes", "luces", "vestuarios"):
    for e in cat[grupo]:
        if e.get("thumb"):
            trabajos.append((os.path.join(CAT, "thumbs", f"{grupo}_{e['id']}.jpg"), e["thumb"], "3:4", 0.6))
for pid, p in POSES_NUEVAS.items():
    ratio = "2:3" if p["encuadre"] == "full" else "7:9"
    txt = (f"A studio photograph of {p['quien']}, {p['desc']}. Plain light grey seamless "
           f"background, even soft light, sharp focus, {'the whole body visible from head to feet' if p['encuadre']=='full' else 'framed from the thighs up'}.")
    trabajos.append((os.path.join(CAT, "poses", "fuentes", f"{pid}.png"), txt, ratio, 1.0))

for i, (dest, prompt, ratio, mp) in enumerate(trabajos):
    if os.path.exists(dest):
        continue
    tmp = dest + ".png"
    r = Q.generar(tmp, prompt=prompt, ratio=ratio, megapixeles=mp, steps=16, seed=7000 + i)
    from PIL import Image
    im = Image.open(tmp).convert("RGB")
    if dest.endswith(".jpg"):
        im.save(dest, quality=90); os.remove(tmp)
    else:
        os.replace(tmp, dest)
    print(f"{i+1}/{len(trabajos)} {os.path.basename(dest)} {r['segundos']}s {r['tam']}", flush=True)
print("CATALOGO_LISTO", flush=True)
