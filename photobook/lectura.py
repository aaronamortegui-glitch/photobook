"""Read a photograph into the words a regeneration needs.

Qwen3-VL looks at a package photo (real or made here) and returns five short
fields: where it is, what the person wears, how they stand, their expression
and the light on them. Never who they are -- face, hair, age and body are the
client's, and naming the model's would pull the model back in.

Why words: the swap test (pruebas/exp6) looked like a bad composite because the
client's close-up brought its own flat light and neutral face with it. The
expression and the light have to be asked for, by name, in the generation AND
in the face pass, or the face pass puts the neutral close-up back.
"""
from __future__ import annotations

import re

from . import motor_qwen as Q

PREGUNTA = (
    "Describe this photograph so it can be recreated with a different person. Answer in "
    "exactly five lines, English, each under 25 words:\n"
    "PLACE: where it is, naming the landmark or setting\n"
    "WEAR: every garment by name, top to bottom, with colour and pattern, shoes included "
    "(e.g. a navy-and-white striped Breton top, cream wide trousers, a camel trench coat, white sneakers)\n"
    "POSE: body position, what the hands do, where the eyes look, the framing\n"
    "EXPRESSION: the facial expression, precisely (e.g. broad open-mouthed laugh, soft closed smile)\n"
    "LIGHT: direction, colour and quality of the light on the person\n"
    "Never describe the person's face shape, hair, age, skin or body.")

CAMPOS = ("PLACE", "WEAR", "POSE", "EXPRESSION", "LIGHT")


def leer(ruta: str) -> dict:
    txt = Q.describir(ruta, PREGUNTA, max_tokens=200)
    out = {}
    for c in CAMPOS:
        m = re.search(rf"{c}\s*:\s*(.+)", txt, re.I)
        out[c.lower()] = m.group(1).strip().rstrip(".") if m else ""
    # The model sometimes answers the five lines in order but without the
    # labels (seen on the first run of pruebas/exp8). Positional fallback.
    lineas = [l.strip(" -*	").rstrip(".") for l in txt.splitlines() if l.strip()]
    lineas = [re.sub(r"^[A-Z]+\s*:\s*", "", l) for l in lineas]
    if sum(bool(out[c.lower()]) for c in CAMPOS) < 3 and len(lineas) >= 5:
        for c, l in zip(CAMPOS, lineas[:5]):
            out[c.lower()] = l
    out["_crudo"] = txt
    return out


def _min(t: str) -> str:
    return t[:1].lower() + t[1:] if t and not t[:2].isupper() else t


def prompt_regenerar(l: dict, estilo: str = "A candid travel photograph", encuadre: str = "") -> str:
    """Regeneration, not substitution: the subject photographed in that moment.

    `encuadre` is set by the caller from the photo's proportions: the model
    reading the photo called a full-length shot a "medium close-up".
    """
    # a plain studio backdrop is often read as no place at all: say what it is
    lugar = (l.get("place") or "").strip() or "a photo studio, against the same plain backdrop"
    return (f"{estilo} of the subject, photographed in that same moment at {lugar}: "
            f"{_min(l['pose'])}, {_min(l['expression'])}, wearing {_min(l['wear'])}. "
            f"Lit by {_min(l['light'])}, the same colour, contrast and grain throughout the frame. "
            f"{encuadre}").strip()


def prompt_cara(l: dict) -> str:
    """The face pass, told what the face is doing and how it is lit."""
    return (f"Redraw the face of the person in <image1> as the subject from <image2>: the same "
            f"facial structure, eyes, nose, mouth, skin tone and age, with {_min(l['expression'])}, "
            f"lit by {_min(l['light'])} exactly as the rest of <image1>. Natural skin texture.")


# --------------------------------------------------------------- identity spec

PREGUNTA_IDENTIDAD = (
    "This is a reference photo of a client whose likeness must be reproduced. Write their "
    "identity checklist in exactly these nine lines, English, each under 18 words, concrete and "
    "visual (no names, no guesses about personality):\n"
    "face_shape: ...\neyes: shape, size, spacing, colour, eyelids\nbrows: ...\nnose: ...\n"
    "lips_mouth: ...\nskin: tone, texture, freckles, moles, lines\nfacial_hair: ... or none\n"
    "hair: colour, length, texture, hairline, parting\nage_look: apparent age range")
CAMPOS_ID = ("face_shape", "eyes", "brows", "nose", "lips_mouth", "skin", "facial_hair", "hair", "age_look")


def leer_identidad(ruta_cara: str) -> dict:
    """The client's identity as a written checklist -- the face's EYEWEAR SPEC.

    Same role as the SKU inventory in a SUNBURST eyewear prompt: the reference
    image stays the authority, this only makes sure no feature is skipped.
    """
    txt = Q.describir(ruta_cara, PREGUNTA_IDENTIDAD, max_tokens=260)
    out = {}
    for c in CAMPOS_ID:
        # anchored to the line start: "hair:" must not match inside "facial_hair:"
        m = re.search(rf"(?im)^\W*{c}\s*:\s*(.+)", txt)
        out[c] = m.group(1).strip().rstrip(".") if m else ""
    lineas = [re.sub(r"^[\w ]+:\s*", "", l).strip() for l in txt.splitlines() if l.strip()]
    if sum(bool(v) for v in out.values()) < 5 and len(lineas) >= 9:
        out = dict(zip(CAMPOS_ID, lineas[:9]))
    out["_crudo"] = txt
    return out
