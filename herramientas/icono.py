"""Draw Photobook's icon: two tilted photo cards on a night-blue tile, the front one a
polaroid whose picture is the magenta -> violet -> cyan gradient of the brand.

    python herramientas/icono.py
Writes photobook/web/icon.svg, icon-512.png, apple-touch-icon.png (180) and
photobook.ico (16-256) -- the .ico is the desktop shortcut's icon.
"""
import os
from PIL import Image, ImageDraw

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = os.path.join(RAIZ, "photobook", "web")
NOCHE, MAGENTA, VIOLETA, CIAN = (13, 14, 26), (255, 63, 208), (139, 92, 246), (63, 224, 255)

SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ff3fd0"/><stop offset=".5" stop-color="#8b5cf6"/><stop offset="1" stop-color="#3fe0ff"/>
    </linearGradient>
    <linearGradient id="b" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3fe0ff"/><stop offset="1" stop-color="#8b5cf6"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="112" fill="#0d0e1a"/>
  <rect x="118" y="112" width="228" height="276" rx="26" fill="url(#b)" opacity=".55" transform="rotate(-12 232 250)"/>
  <g transform="rotate(7 272 270)">
    <rect x="150" y="116" width="244" height="296" rx="26" fill="#f6f4ff"/>
    <rect x="172" y="138" width="200" height="200" rx="14" fill="url(#g)"/>
    <circle cx="322" cy="186" r="24" fill="#ffffff" opacity=".92"/>
  </g>
</svg>
'''


def _grad(w, h, stops):
    """Diagonal gradient through the given colours."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    n = len(stops) - 1
    for y in range(h):
        for x in range(w):
            t = (x / max(1, w - 1) + y / max(1, h - 1)) / 2
            i = min(n - 1, int(t * n))
            f = t * n - i
            a, b = stops[i], stops[i + 1]
            px[x, y] = tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))
    return im


def _carta(w, h, r, relleno):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    capa = Image.new("RGBA", (w, h))
    capa.paste(relleno, (0, 0), m)
    return capa


def dibujar(S=1024):
    k = S / 512
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    fondo = Image.new("L", (S, S), 0)
    ImageDraw.Draw(fondo).rounded_rectangle((0, 0, S - 1, S - 1), int(112 * k), fill=255)
    im.paste(Image.new("RGBA", (S, S), NOCHE + (255,)), (0, 0), fondo)
    # back card
    atras = _carta(int(228 * k), int(276 * k), int(26 * k), _grad(int(228 * k), int(276 * k), [CIAN, VIOLETA]))
    atras.putalpha(atras.getchannel("A").point(lambda v: int(v * .55)))
    atras = atras.rotate(12, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(atras, (int(232 * k - atras.width / 2), int(250 * k - atras.height / 2)))
    # front polaroid
    cw, ch = int(244 * k), int(296 * k)
    frente = _carta(cw, ch, int(26 * k), Image.new("RGB", (cw, ch), (246, 244, 255)))
    foto = _carta(int(200 * k), int(200 * k), int(14 * k), _grad(int(200 * k), int(200 * k), [MAGENTA, VIOLETA, CIAN]))
    ImageDraw.Draw(foto).ellipse((int(126 * k), int(24 * k), int(174 * k), int(72 * k)), fill=(255, 255, 255, 235))
    frente.alpha_composite(foto, (int(22 * k), int(22 * k)))
    frente = frente.rotate(-7, expand=True, resample=Image.BICUBIC)
    im.alpha_composite(frente, (int(272 * k - frente.width / 2), int(264 * k - frente.height / 2)))
    return im


if __name__ == "__main__":
    open(os.path.join(W, "icon.svg"), "w", encoding="utf-8").write(SVG)
    big = dibujar(1024)
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(W, "icon-512.png"))
    big.resize((180, 180), Image.LANCZOS).save(os.path.join(W, "apple-touch-icon.png"))
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(W, "photobook.ico"),
                                               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("icon written")
