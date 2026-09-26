"""Face detailer, layer 1: crop the face, rebuild it, and put it back where it was.

The logic of the SmartMaskCrop / SmartMaskStitch nodes (comfyui-inpaint-cropstitch-nb2,
used by an eyewear SUNBURST inpainting workflow), plus the two things the first face pass
got wrong, both seen on sesiones/20260925-003540-5f9cfa (pruebas/diag_cara.jpg):

  - a double contour. Qwen's edit has no mask: it redraws the whole crop and the
    head moves a few pixels, so pasting through the mask shows two outlines.
    Fixed by ALIGNING the rebuilt crop onto the original with the five ArcFace
    landmarks (a similarity transform: shift, rotation, scale) before blending.
  - a green-yellow halo. Colour was matched per RGB channel, which bends hue.
    Now matched in CIELAB, lightness and the two colour axes separately.

Flow, and what each step keeps for the next -- the "stitcher":

  recortar()  mask bbox -> grown by `contexto` -> fitted to an aspect ratio ->
              slid inside the frame -> cropped -> resized so its AREA is the
              engine's budget (multiples of 16). Keeps rect, scale, crop mask.
  <engine>    any generator; the crop goes in, a crop of the same size comes out.
  alinear()   landmarks on both crops -> least-squares similarity -> warp.
  pegar()     back to rect size, LAB colour match inside the mask, blend through
              the mask grown + feathered AND faded to zero at the crop's edge, so
              nothing outside the rect can change.

Everything here is CPU and numpy/PIL; the landmarks come from faceid.py in
ComfyUI's Python, like the identity score.
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageFilter

from . import caras as C


# --------------------------------------------------------------- the crop

def recortar(img: Image.Image, mascara: Image.Image, *, contexto: float = 1.8,
             ratio: float | None = None, area: int = 1024 * 1024, umbral: int = 127) -> dict:
    """Crop around the mask the way SmartMaskCrop does. Returns the stitcher.

    `contexto` multiplies the mask's bbox side: the model needs to see some hair,
    neck and light around a face to redraw it consistently. `ratio` (w/h) of the
    crop; None takes the bbox's own, clamped to 3:4..4:3.
    """
    m = mascara.convert("L").resize(img.size, Image.BILINEAR) if mascara.size != img.size else mascara.convert("L")
    caja = m.point(lambda v: 255 if v > umbral else 0).getbbox()
    if not caja:
        raise ValueError("empty mask")
    x0, y0, x1, y1 = caja
    bw, bh = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = ratio or min(4 / 3, max(3 / 4, bw / max(1, bh)))
    # the smallest rect of aspect r that holds the grown bbox
    w = max(bw * contexto, bh * contexto * r)
    h = w / r
    W, H = img.size
    if w > W:
        w, h = W, W / r
    if h > H:
        h, w = H, H * r
    w, h = int(round(w)), int(round(h))
    l = int(round(cx - w / 2))
    t = int(round(cy - h / 2 - 0.04 * h))           # a little headroom for the hair
    l = max(0, min(l, W - w))
    t = max(0, min(t, H - h))
    rect = (l, t, l + w, t + h)

    # engine size: that aspect at the area budget, multiples of 16
    ow = max(256, int(round(math.sqrt(area * w / h) / 16)) * 16)
    oh = max(256, int(round(math.sqrt(area * h / w) / 16)) * 16)
    crop = img.crop(rect)
    return {"rect": rect, "tam_motor": (ow, oh), "caja_mascara": caja,
            "recorte": crop, "recorte_motor": crop.resize((ow, oh), Image.LANCZOS),
            "mascara": m.crop(rect), "cara_px": max(bw, bh)}


# --------------------------------------------------------------- alignment

def _similaridad(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """2x3 matrix of the similarity (scale, rotation, shift) taking src onto dst, least squares."""
    A, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, -y, 1, 0]); b.append(u)
        A.append([y, x, 0, 1]); b.append(v)
    a, bb, tx, ty = np.linalg.lstsq(np.asarray(A, float), np.asarray(b, float), rcond=None)[0]
    return np.array([[a, -bb, tx], [bb, a, ty]])


def puntos(rutas: list[str]) -> dict[str, list | None]:
    filas = C._correr([C.FACE_PY, "-W", "ignore", C.FACEID, "--puntos"] + list(rutas))
    return {os.path.normcase(os.path.abspath(f["image"])): f.get("puntos") for f in filas if "image" in f}


def alinear(nuevo: Image.Image, pts_nuevo, pts_orig, *, max_desvio: float = 0.25) -> tuple[Image.Image, dict]:
    """Warp `nuevo` so its landmarks land on the original's. Both in the same crop space.

    Refuses (returns `nuevo` untouched) when the fit says something else than a
    small correction -- a scale off by more than `max_desvio`, or a rotation over
    15 degrees means a landmark was misread, and warping on it would be worse
    than the double contour it is meant to fix.
    """
    if not pts_nuevo or not pts_orig:
        return nuevo, {"alineado": False, "motivo": "no landmarks"}
    src, dst = np.asarray(pts_nuevo, float), np.asarray(pts_orig, float)
    M = _similaridad(src, dst)
    escala = math.hypot(M[0, 0], M[1, 0])
    giro = math.degrees(math.atan2(M[1, 0], M[0, 0]))
    antes = float(np.linalg.norm(src - dst, axis=1).mean())
    despues = float(np.linalg.norm((src @ M[:, :2].T + M[:, 2]) - dst, axis=1).mean())
    info = {"escala": round(escala, 4), "giro": round(giro, 2),
            "desplazamiento": [round(M[0, 2], 1), round(M[1, 2], 1)],
            "error_px_antes": round(antes, 2), "error_px_despues": round(despues, 2)}
    if abs(escala - 1) > max_desvio or abs(giro) > 15:
        return nuevo, dict(info, alineado=False, motivo="fit out of range")
    # PIL wants the inverse map: output pixel -> input pixel
    Mi = np.linalg.inv(np.vstack([M, [0, 0, 1]]))[:2]
    out = nuevo.transform(nuevo.size, Image.AFFINE, tuple(Mi.flatten()), resample=Image.BICUBIC,
                          fillcolor=None)
    return out, dict(info, alineado=True)


# --------------------------------------------------------------- colour

def _srgb_a_lab(rgb: np.ndarray) -> np.ndarray:
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _lab_a_srgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    e, k = 216 / 24389, 24389 / 27
    x = np.where(fx ** 3 > e, fx ** 3, (116 * fx - 16) / k)
    y = np.where(lab[..., 0] > k * e, fy ** 3, lab[..., 0] / k)
    z = np.where(fz ** 3 > e, fz ** 3, (116 * fz - 16) / k)
    xyz = np.stack([x, y, z], -1) * np.array([0.95047, 1.0, 1.08883])
    Mi = np.array([[3.2404542, -1.5371385, -0.4985314],
                   [-0.9692660, 1.8760108, 0.0415560],
                   [0.0556434, -0.2040259, 1.0572252]])
    c = np.clip(xyz @ Mi.T, 0, 1)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)
    return np.clip(c * 255, 0, 255)


def igualar_color_lab(nuevo: Image.Image, viejo: Image.Image, mascara: Image.Image,
                      fuerza_contraste: float = 0.5) -> Image.Image:
    """Move the rebuilt face's colour onto the original's, inside the mask, in CIELAB.

    The mean is matched fully on all three axes; the spread only halfway
    (`fuerza_contraste`), because a rebuilt face is sharper than the soft one it
    replaces and stretching its contrast back down to the original's would undo
    the detail that was the point of the pass.
    """
    a = _srgb_a_lab(np.asarray(nuevo.convert("RGB"), dtype=np.float64))
    b = _srgb_a_lab(np.asarray(viejo.convert("RGB"), dtype=np.float64))
    m = np.asarray(mascara.convert("L").resize(nuevo.size), dtype=np.float64) > 127
    if m.sum() < 50:
        return nuevo
    out = a.copy()
    for c in range(3):
        ma, sa = a[..., c][m].mean(), a[..., c][m].std() + 1e-6
        mb, sb = b[..., c][m].mean(), b[..., c][m].std() + 1e-6
        k = 1 + fuerza_contraste * (sb / sa - 1)
        out[..., c] = (a[..., c] - ma) * k + mb
    return Image.fromarray(_lab_a_srgb(out).astype("uint8"))


def igualar_baja_frecuencia(nuevo: Image.Image, viejo: Image.Image, radio: float) -> Image.Image:
    """Lighting and colour from the original, detail from the rebuild.

    new + blur(original) - blur(new): the coarse layer -- light direction, skin
    tone, the colour cast of the scene -- is the original's at every pixel,
    and only the fine layer -- pores, eyes, the drawn features -- comes from
    the rebuild. Unlike a global match it also fixes the ring around the face,
    where hair and sky were being shifted by statistics taken from the skin:
    that was the green-yellow halo. Needs the two aligned first.
    """
    r = max(1.0, radio)
    a = np.asarray(nuevo.convert("RGB"), dtype=np.float64)
    ba = np.asarray(nuevo.convert("RGB").filter(ImageFilter.GaussianBlur(r)), dtype=np.float64)
    bb = np.asarray(viejo.convert("RGB").resize(nuevo.size).filter(ImageFilter.GaussianBlur(r)), dtype=np.float64)
    return Image.fromarray(np.clip(a - ba + bb, 0, 255).astype("uint8"))


def igualar_color_cara(nuevo: Image.Image, viejo: Image.Image, mascara: Image.Image,
                       cara_px: float) -> Image.Image:
    """The LAB match, applied only through the face mask.

    Measured in herramientas/test_detailer.py with an engine that re-tints the
    skin alone (what the rebuild does: it brings the reference's skin tone and
    leaves hair and sky): a per-channel match taken from the skin and applied
    to the whole crop pushed the ring around the face 15.7 dE off -- the halo.
    Weighting the correction by the (softened, not grown) face mask leaves the
    hair and background as the rebuild drew them, which the blend then fades
    into the original anyway.
    """
    corr = igualar_color_lab(nuevo, viejo, mascara)
    w = mascara.convert("L").resize(nuevo.size).filter(ImageFilter.GaussianBlur(max(1.0, cara_px * 0.04)))
    return Image.composite(corr, nuevo.convert("RGB"), w)


# --------------------------------------------------------------- the stitch

def mascara_mezcla(st: dict, *, crecer_pct: float = 10.0, difuminar_pct: float = 6.0,
                   borde_pct: float = 4.0) -> Image.Image:
    """The blend mask in crop space: the face mask grown and feathered by a share
    of the face size, multiplied by a ramp that reaches zero at the crop's border
    (SmartMaskStitch's edge feather) -- so the rect's outline can never show."""
    m = st["mascara"]
    t = st["cara_px"]
    g = max(3, int(t * crecer_pct / 100)) | 1
    m = m.filter(ImageFilter.MaxFilter(min(g, 61)))
    m = m.filter(ImageFilter.GaussianBlur(max(1.0, t * difuminar_pct / 100)))
    w, h = m.size
    e = max(2, int(min(w, h) * borde_pct / 100))
    yy, xx = np.mgrid[:h, :w]
    d = np.minimum(np.minimum(xx, w - 1 - xx), np.minimum(yy, h - 1 - yy)).astype(float)
    rampa = np.clip(d / e, 0, 1)
    rampa = rampa * rampa * (3 - 2 * rampa)            # smoothstep
    a = np.asarray(m, dtype=float) * rampa
    return Image.fromarray(np.clip(a, 0, 255).astype("uint8"))


def pegar(img: Image.Image, st: dict, generado_rect: Image.Image, **mezcla) -> Image.Image:
    """Blend the rebuilt crop (already at rect size, aligned, colour-matched) back in."""
    l, t, r, b = st["rect"]
    mm = mascara_mezcla(st, **mezcla)
    parche = Image.composite(generado_rect.convert("RGB"), st["recorte"].convert("RGB"), mm)
    out = img.convert("RGB").copy()
    out.paste(parche, (l, t))
    return out


def banda_costura(st: dict, *, fuera_pct: float = 8.0, dentro_pct: float = 6.0,
                  difuminar_pct: float = 2.0) -> Image.Image:
    """The seam band around the pasted face, in crop space -- for layer 2.

    Same construction as the SUNBURST workflow's frame band (blob minus eroded
    blob, softened): the face mask grown by `fuera_pct` of the face size minus
    the mask eroded by `dentro_pct`. A mask-aware inpaint over this band alone
    can knit the rebuilt face into the photo without touching the face itself.
    """
    m = st["mascara"].convert("L")
    t = st["cara_px"]
    g = max(3, int(t * fuera_pct / 100)) | 1
    e = max(3, int(t * dentro_pct / 100)) | 1
    grande = np.asarray(m.filter(ImageFilter.MaxFilter(min(g, 61))), float)
    chica = np.asarray(m.filter(ImageFilter.MinFilter(min(e, 61))), float)
    banda = Image.fromarray(np.clip(grande - chica, 0, 255).astype("uint8"))
    return banda.filter(ImageFilter.GaussianBlur(max(1.0, t * difuminar_pct / 100)))


def prompt_cabeza(expresion: str = "", luz: str = "") -> str:
    """The head-and-shoulders rebuild: face AND hair are the client's, the rest stays.

    Asked for after exp11: rebuilding only the face oval put the seam across
    forehead, cheeks and jaw, where any difference in skin or light shows, and
    the crop gave the model too little around it -- it looked pasted. With the
    SAM 3 "head and neck" mask the seam falls on the outer hair and the collar.
    """
    e = f", with {expresion}" if expresion else ""
    l = f", lit by {luz} like the rest of <image1>" if luz else ", lit exactly like the rest of <image1>"
    return (f"Redraw the head of the person in <image1> -- the face and the hair -- as the subject "
            f"from <image2>: the same facial structure, eyes, nose, mouth, skin tone, age, hairstyle "
            f"and hair colour{e}{l}. The neck, the shoulders and the clothing stay as they are. "
            f"Natural skin texture.")


# --------------------------------------------------------------- the whole pass

def reforzar(imagen: str, mascara: str, cara_cliente: str, destino: str, *, seed: int = 0,
             cfg: float = 3.0, steps: int = 40, prompt: str = C.PROMPT_CARA,
             negativo: str = C.NEGATIVO_CARA, contexto: float = 1.8,
             area: int = 1024 * 1024, alinear_cara: bool = True, color: str = "lab_mascara",
             radio_color: float = 0.12, motor=None) -> dict:
    """Detailer layer 1 end to end. `motor(crop_path, out_path)` replaces the
    Qwen edit, which is how the offline test runs it without the GPU."""
    img = Image.open(imagen).convert("RGB")
    st = recortar(img, Image.open(mascara), contexto=contexto, area=area)
    base = os.path.splitext(destino)[0]
    ent, sal = base + "._in.png", base + "._out.png"
    st["recorte_motor"].save(ent)
    if motor is None:
        r = C.Q.editar(sal, imagen=ent, prompt=prompt, referencias=[cara_cliente],
                       steps=steps, seed=seed, cfg=cfg, negativo=negativo)
        segundos = r["segundos"]
    else:
        motor(ent, sal)
        segundos = 0.0
    l, t, rr, bb = st["rect"]
    nuevo = Image.open(sal).convert("RGB").resize((rr - l, bb - t), Image.LANCZOS)

    info = {"rect": list(st["rect"]), "tam_motor": list(st["tam_motor"]), "cara_px": st["cara_px"],
            "segundos": segundos}
    if alinear_cara:
        a_n, a_o = base + "._n.png", base + "._o.png"
        nuevo.save(a_n); st["recorte"].save(a_o)
        p = puntos([a_n, a_o])
        nuevo, ia = alinear(nuevo, p.get(os.path.normcase(os.path.abspath(a_n))),
                            p.get(os.path.normcase(os.path.abspath(a_o))))
        info["alineacion"] = ia
        for f in (a_n, a_o):
            os.remove(f)
    if color == "lab_mascara":
        nuevo = igualar_color_cara(nuevo, st["recorte"], st["mascara"], st["cara_px"])
    elif color == "baja":
        nuevo = igualar_baja_frecuencia(nuevo, st["recorte"], st["cara_px"] * radio_color)
    elif color == "lab":
        nuevo = igualar_color_lab(nuevo, st["recorte"], st["mascara"])
    elif color == "rgb":
        nuevo = C.igualar_color(nuevo, st["recorte"], st["mascara"])
    pegar(img, st, nuevo).save(destino)
    for f in (ent, sal):
        if os.path.exists(f):
            os.remove(f)
    info["archivo"] = destino
    return info


# --------------------------------------------------------------- fal backend

def prompt_gpt(expresion: str = "", luz: str = "", ficha: dict | None = None) -> str:
    """The face version of a SUNBURST eyewear inpainting prompt, same structure:
    a CRITICAL block that fixes the geometry, what must not change, the authority
    of the references, the priority detail, what to preserve, the constraints,
    and a closed checklist -- there the SKU inventory, here the client's identity
    read from their close-up (lectura.leer_identidad). GPT Image 2.5 follows long
    instructions without drawing them (Qwen does not: qwen-inpaint-prompt-length).
    """
    e = expresion or "exactly the expression it has now"
    l = luz or "exactly the light it has now"
    ficha = {k: v for k, v in (ficha or {}).items() if not k.startswith("_") and v}
    spec = "\n".join(f"{k}: {v}" for k, v in ficha.items())
    return f"""CRITICAL - THIS RULE OVERRIDES EVERY INSTRUCTION BELOW IT.

Image 1's head is correctly placed and its pose is fixed. You are re-rendering the
SAME head, in the same place, at higher fidelity, with the identity of the person in
Image 2. You are never pasting a different head onto this body.

Do not change any of these in Image 1:
- the head's position, size, tilt and turn, and the angle of the neck
- the direction of the gaze
- the expression: {e} -- how open the mouth is, the smile, the eyebrows
- the light on the face: {l} -- its direction, colour, hardness and the shadows it casts
- the silhouette where the hair meets the background, the neck and the collar

THE HEAD'S VISIBLE EXTENT IS FIXED. Whatever part of the head Image 1 does not show
stays unshown: if hair, a raised arm, a collar or the frame edge hides part of it,
it stays hidden. Do not turn the head toward the camera or complete a profile.

Change only who it is: facial structure and features, skin tone and texture, age,
facial hair, hair colour and texture. If any instruction below would change the
pose, the expression, the light or the framing, ignore that instruction.

---

Image 1: the photo to edit. Image 2: reference photo of the person. Mask: white = the
only region that may change. AUTHORITY: Image 2 is the ground truth for identity. The
IDENTITY SPEC at the end is a written checklist derived from it - use it to make sure
no feature is overlooked, never to override what Image 2 shows.

Change: redraw the face and hair in Image 1 so that the person is unmistakably the
person in Image 2.

PRIORITY DETAIL - the eyes. They are what is most often lost: their shape, size,
spacing and the lids, then the nose, the mouth and the jawline. Resolve them first,
seen from Image 1's camera angle.

Preserve exactly: the expression, the gaze, the head angle, the lighting and colour
grade of Image 1, the background, the clothing, the neckline, film grain, focus and
depth of field. The skin at the edge of the mask continues seamlessly into the skin
outside it; the hair edge blends into the background exactly as in Image 1.

Constraints: no beauty retouching, no added make-up, no younger or older look than
Image 2, no glasses, jewellery or accessories that Image 2 and Image 1 do not show.
Nothing outside the white mask region changes.

IDENTITY SPEC (checklist only - Image 2 takes precedence):
{spec or "(none)"}"""


def mascara_holgada(m: Image.Image, cara_px: float, crecer_pct: float) -> Image.Image:
    """The mask sent to fal: the head-and-neck silhouette grown by `crecer_pct` of the
    head size, with a smooth outline instead of every strand.

    Asked for on exp14 (the user's call: "it is cutting too close to the head"). A
    mask hugging the silhouette makes the model fit the new hair inside the old
    outline, and it softens that edge -- the halo against the sky survived every
    wider blend tried on the saved outputs. A loose mask lets it draw the hair edge
    and the background around it itself, and the seam lands on flat background.
    Grown by blur-and-threshold, which rounds the outline and has no kernel cap.
    """
    r = max(2.0, cara_px * crecer_pct / 100.0)
    b = m.convert("L").point(lambda v: 255 if v > 127 else 0).filter(ImageFilter.GaussianBlur(r))
    return b.point(lambda v: 255 if v > 12 else 0)


def reforzar_fal(imagen: str, mascara: str, referencias: list[str], destino: str, *,
                 expresion: str = "", luz: str = "", ficha: dict | None = None,
                 contexto: float = 1.9, lado: int = 2048, crecer_pct: float = 6.0,
                 holgada: bool = False,
                 calidad: str = "high", color: str = "none",
                 mezcla_crecer_pct: float = 4.0, mezcla_difuminar_pct: float = 5.0,
                 borde_pct: float = 7.0, corregir_escala: bool = False,
                 crudo: str | None = None) -> dict:
    """Head-and-shoulders pass on fal with a real mask (Sunburst), locked outside it.

    Sizes and seams follow the SUNBURST workflow: the crop goes at 2048 on its long
    side (SmartMaskCrop resize_to_target 2048), and the paste back fades over the
    last 7% of the crop (SmartMaskStitch edge_feather 7). The blend mask is the sent
    mask grown a little more and feathered wider than before (exp13 showed a hard
    hair-against-sky edge and a smear across the neck at 2.5%), so the transition
    falls where the model reproduced the original rather than on the new hair.

    `crudo`: an earlier raw fal output for this crop -- re-stitches without a call.
    """
    from . import fal_inpaint as FAL
    img = Image.open(imagen).convert("RGB")
    st = recortar(img, Image.open(mascara), contexto=contexto)
    l, t, r, b = st["rect"]
    w, h = r - l, b - t
    k = lado / max(w, h)
    aw, ah = max(256, int(round(w * k / 16)) * 16), max(256, int(round(h * k / 16)) * 16)
    if holgada:
        m_edit = mascara_holgada(st["mascara"], st["cara_px"], crecer_pct)
    else:
        g = max(3, int(st["cara_px"] * crecer_pct / 100)) | 1
        m_edit = st["mascara"].filter(ImageFilter.MaxFilter(min(g, 61))).point(lambda v: 255 if v > 127 else 0)
    base = os.path.splitext(destino)[0]
    info = {}
    if crudo and os.path.exists(crudo):
        out = Image.open(crudo).convert("RGB")
        info["segundos"] = 0.0
    else:
        crop = st["recorte"].resize((aw, ah), Image.LANCZOS)
        out, info = FAL.editar(crop, referencias, m_edit.resize((aw, ah), Image.NEAREST),
                               prompt_gpt(expresion, luz, ficha), ancho=aw, alto=ah, calidad=calidad)
        out.save(base + "_fal_crudo.png")       # kept: the stitch can be re-tuned offline
    nuevo = out.resize((w, h), Image.LANCZOS)
    if corregir_escala:
        # A loose mask gives the model room, and it fills it: on exp15 the head came
        # back 16-37% larger (eye distance). Warp the output so its five landmarks
        # land on the original's -- the head returns to its size and place, and the
        # clean hair edge the loose mask bought comes along with it.
        a_n, a_o = base + "._n.png", base + "._o.png"
        nuevo.save(a_n); st["recorte"].save(a_o)
        pp = puntos([a_n, a_o])
        nuevo, ia = alinear(nuevo, pp.get(os.path.normcase(os.path.abspath(a_n))),
                            pp.get(os.path.normcase(os.path.abspath(a_o))), max_desvio=0.45)
        info["escala"] = ia
        for f in (a_n, a_o):
            os.remove(f)
    if color == "lab_mascara":
        nuevo = igualar_color_cara(nuevo, st["recorte"], st["mascara"], st["cara_px"])
    st_m = dict(st, mascara=m_edit)
    pegar(img, st_m, nuevo, crecer_pct=mezcla_crecer_pct, difuminar_pct=mezcla_difuminar_pct,
          borde_pct=borde_pct).save(destino)
    info.update({"rect": list(st["rect"]), "enviado": f"{aw}x{ah}", "cara_px": st["cara_px"],
                 "archivo": destino, "crudo": base + "_fal_crudo.png"})
    return info


def prompt_banda() -> str:
    """Second pass, the SUNBURST frame-band idea applied to a head: only the ring
    along the hair, neck and collar outline may change, so the model can knit the
    edge into the background but cannot touch the face or resize the head."""
    return """CRITICAL - THIS RULE OVERRIDES EVERY INSTRUCTION BELOW IT.

Image 1 is a finished photograph. The person's face, head size, head shape, hair
colour, hair length and pose are final and must not change. The mask is a thin band
that follows the outline where the hair, neck and collar meet the background.

Inside the white band only: make the transition between the person and the
background photographically seamless. Hair strands continue naturally past the
outline with the same edge softness as the rest of Image 1's focus; the background
continues behind them with the same colour, light, blur and grain; the neck and the
collar meet the clothing without any smear, halo, glow or ghost outline.

Do not move, enlarge, shrink or redraw the head. Do not add hair volume. Nothing
outside the white mask region changes."""


def pasada_banda(imagen: str, mascara: str, destino: str, *, contexto: float = 1.9,
                 lado: int = 2048, fuera_pct: float = 10.0, dentro_pct: float = 5.0,
                 calidad: str = "high", crudo: str | None = None) -> dict:
    """Knit the head pass's outline into the photo with a masked band edit on fal."""
    from . import fal_inpaint as FAL
    img = Image.open(imagen).convert("RGB")
    st = recortar(img, Image.open(mascara), contexto=contexto)
    l, t, r, b = st["rect"]
    w, h = r - l, b - t
    k = lado / max(w, h)
    aw, ah = max(256, int(round(w * k / 16)) * 16), max(256, int(round(h * k / 16)) * 16)
    banda = banda_costura(st, fuera_pct=fuera_pct, dentro_pct=dentro_pct, difuminar_pct=0.0)
    banda = banda.point(lambda v: 255 if v > 127 else 0)
    base = os.path.splitext(destino)[0]
    info = {}
    if crudo and os.path.exists(crudo):
        out = Image.open(crudo).convert("RGB"); info["segundos"] = 0.0
    else:
        out, info = FAL.editar(st["recorte"].resize((aw, ah), Image.LANCZOS), [],
                               banda.resize((aw, ah), Image.NEAREST), prompt_banda(),
                               ancho=aw, alto=ah, calidad=calidad)
        out.save(base + "_banda_crudo.png")
    nuevo = out.resize((w, h), Image.LANCZOS)
    st_b = dict(st, mascara=banda)
    pegar(img, st_b, nuevo, crecer_pct=0.0, difuminar_pct=2.0, borde_pct=7.0).save(destino)
    info.update({"rect": list(st["rect"]), "enviado": f"{aw}x{ah}", "archivo": destino})
    return info


# --------------------------------------------------------------- local enhance (Qwen upscale)

PROMPT_UPSCALE_ID = ("Enhance <image1> to high resolution: natural skin texture, sharp eyes, eyelashes "
                     "and hair strands, clean edges. Keep the composition, the pose, the head angle, the "
                     "expression, the gaze, the lighting and the colours exactly as they are. The face is "
                     "the person in <image2>: the same facial structure, eyes, nose, mouth, skin tone and age.")


def reforzar_qwen_upscale(imagen: str, mascara: str, destino: str, *, referencia: str | None = None,
                          contexto: float = 1.9, objetivo: int = 1400, seed: int = 11, steps: int = 40,
                          alinear_cara: bool = True, color: str = "lab_mascara",
                          crudo: str | None = None, extra: str = "") -> dict:
    """The face enhanced locally by QwenStudio's own upscale, on the cropped area only.

    Asked for after the fal pass (2026-09-25): QwenStudio's /api/reescalar redraws an
    image larger with itself as the reference, so pose, angle and expression come from
    the photo -- it adds detail instead of reinventing the head, which is what made the
    earlier local pass ghost on turned heads. Applied to the head-and-shoulders crop, a
    150 px face is redrawn at ~1000 px and pasted back through the head mask.

    `referencia` given: instead of the plain upscale, a whole-crop edit with an
    upscale-style instruction and the client's close-up as <image2>, so the added
    detail is the client's (guided, cfg 3 + negative, as QwenStudio measured edits need).
    """
    img = Image.open(imagen).convert("RGB")
    st = recortar(img, Image.open(mascara), contexto=contexto)
    l, t, r, b = st["rect"]
    w, h = r - l, b - t
    base = os.path.splitext(destino)[0]
    ent, sal = base + "._in.png", base + "._up.png"
    if crudo and os.path.exists(crudo):
        Image.open(crudo).save(sal); rr = {"segundos": 0.0}
    elif referencia:
        st["recorte_motor"].save(ent)             # 1 MP: two references (crop + face)
        prompt = PROMPT_UPSCALE_ID + (" " + extra.strip() if extra.strip() else "")
        rr = C.Q.editar(sal, imagen=ent, prompt=prompt, referencias=[referencia],
                        steps=steps, seed=seed, cfg=3.0, negativo=C.NEGATIVO_CARA)
    else:
        st["recorte"].save(ent)
        rr = C.Q.reescalar(sal, imagen=ent, objetivo=objetivo, seed=seed, steps=steps)
    nuevo = Image.open(sal).convert("RGB").resize((w, h), Image.LANCZOS)
    info = {"rect": list(st["rect"]), "segundos": rr.get("segundos"), "tam_motor": rr.get("tam"),
            "cara_px": st["cara_px"]}
    if alinear_cara:
        a_n, a_o = base + "._n.png", base + "._o.png"
        nuevo.save(a_n); st["recorte"].save(a_o)
        pp = puntos([a_n, a_o])
        pn, po = pp.get(os.path.normcase(os.path.abspath(a_n))), pp.get(os.path.normcase(os.path.abspath(a_o)))
        # only a real correction: under 1.5 px the warp would only resample for nothing
        if pn and po and float(np.linalg.norm(np.asarray(pn) - np.asarray(po), axis=1).mean()) > 1.5:
            nuevo, info["alineacion"] = alinear(nuevo, pn, po, max_desvio=0.15)
        for f in (a_n, a_o):
            os.remove(f)
    if not crudo:
        nuevo.save(base + "_up_crudo.png")
    if color == "lab_mascara":
        # the guided edit pushes saturation (exp18: skin went orange); colour and
        # light go back to the photo's, inside the head mask only
        nuevo = igualar_color_cara(nuevo, st["recorte"], st["mascara"], st["cara_px"])
    pegar(img, st, nuevo, crecer_pct=6.0, difuminar_pct=5.0, borde_pct=7.0).save(destino)
    for f in (ent, sal):
        if os.path.exists(f):
            os.remove(f)
    info["archivo"] = destino
    return info


# --------------------------------------------------------------- whole-image passes (no mask)

PROMPT_ENTERO_ID = ("Re-render <image1> as the same photograph at higher fidelity: the same composition, "
                    "pose, camera angle, framing, lighting, colours and background. The person is the person "
                    "in <image2> -- the same facial structure, eyes, nose, mouth, skin tone, age and hair -- "
                    "with {expresion}. Natural skin texture, sharp detail.")


def entero(imagen: str, destino: str, *, referencia: str | None = None, expresion: str = "",
           seed: int = 21, steps: int = 40, objetivo: int = 2048) -> dict:
    """The whole photo redrawn in the latent -- no mask, no crop, no stitch.

    The user's call on the 2K upscale workflow (qwen212KUpscale_v10: the photo as
    image_1, an empty latent at the 2048^2 area capped at 4x, cfg 1, denoise 1), which
    is what QwenStudio's /api/reescalar already does. With nothing pasted there is no
    seam to feather.

    `referencia` given: an identity pass instead -- the client's close-up as <image2>.
    Two references cap this card at 1.0 MP, so that pass cannot also enlarge; call
    this again without `referencia` to upscale its result (two whole-image passes).
    """
    if referencia:
        e = expresion or "exactly the expression the person has in <image1>"
        r = C.Q.editar(destino, imagen=imagen, prompt=PROMPT_ENTERO_ID.format(expresion=e),
                       referencias=[referencia], steps=steps, seed=seed, cfg=3.0,
                       negativo=C.NEGATIVO_CARA)
    else:
        r = C.Q.reescalar(destino, imagen=imagen, objetivo=objetivo, seed=seed, steps=steps)
    return {"archivo": destino, "segundos": r.get("segundos"), "tam": r.get("tam")}
