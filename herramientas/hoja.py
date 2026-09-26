"""Labelled contact sheet: hoja.py out.jpg "label|path" "label|path" ... [--cols N] [--h 520]"""
import sys
from PIL import Image, ImageDraw, ImageFont

def hoja(salida, items, cols=None, alto=520):
    try:
        fnt = ImageFont.truetype("segoeui.ttf", 18)
    except Exception:
        fnt = ImageFont.load_default()
    celdas = []
    for lbl, ruta in items:
        im = Image.open(ruta).convert("RGB")
        im = im.resize((int(im.width * alto / im.height), alto), Image.LANCZOS)
        c = Image.new("RGB", (im.width, alto + 34), "white")
        c.paste(im, (0, 0))
        ImageDraw.Draw(c).text((6, alto + 6), lbl, fill=(20, 20, 20), font=fnt)
        celdas.append(c)
    cols = cols or len(celdas)
    filas = [celdas[i:i + cols] for i in range(0, len(celdas), cols)]
    W = max(sum(c.width for c in f) + 8 * (len(f) - 1) for f in filas)
    H = sum(max(c.height for c in f) for f in filas) + 8 * (len(filas) - 1)
    S = Image.new("RGB", (W, H), (235, 235, 235))
    y = 0
    for f in filas:
        x = 0
        for c in f:
            S.paste(c, (x, y)); x += c.width + 8
        y += max(c.height for c in f) + 8
    S.save(salida, quality=90)
    return salida

if __name__ == "__main__":
    a = sys.argv[1:]
    cols = int(a[a.index("--cols") + 1]) if "--cols" in a else None
    alto = int(a[a.index("--h") + 1]) if "--h" in a else 520
    its = [x.split("|", 1) for x in a[1:] if "|" in x]
    hoja(a[0], its, cols, alto)
