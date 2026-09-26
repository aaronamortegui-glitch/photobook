"""From the client's choices to the list of shots: poses spread, prompts written.

The prompt per shot is short on purpose. The measured rule from QwenStudio is
about 35 words naming wardrobe, place and light: longer, and the model's own
idea of a generic person overrules the reference. QwenStudio adds the identity
and pose scaffolding around this text and puts the identity sentence last.
"""
from __future__ import annotations

import json
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOGO = os.path.join(RAIZ, "catalogo")

ENCUADRE = {
    "full": ("2:3", "Full-length shot, the whole body visible from head to feet."),
    "half": ("3:4", "Waist-up shot."),
    # extreme close-ups and art portraits: the angle and the crop are the point of the
    # shot, so the framing sentence says so -- a trailing "Waist-up shot" overrode them
    "closeup": ("3:4", "Extreme close-up, the face filling the frame."),
}


def categorias() -> dict:
    """catalogo/prompts_categoria.json: per-category prompt pieces (close-up, half, full).
    Missing file or missing fields -> the built-in defaults; nothing is required."""
    f = os.path.join(CATALOGO, "prompts_categoria.json")
    try:
        return json.load(open(f, encoding="utf-8"))
    except (OSError, ValueError):
        return {"orden": []}


def categoria_por_altura(altura_rel: float, cats: dict | None = None) -> tuple[str, dict]:
    """(name, fields) of the first category in `orden` whose umbral_cara the head's
    relative height reaches. Falls back to ("", {})."""
    cats = cats or categorias()
    for nombre in cats.get("orden", []):
        c = cats.get(nombre) or {}
        if altura_rel >= float(c.get("umbral_cara", 0.0)):
            return nombre, c
    return "", {}


def paquetes() -> list[dict]:
    """Packages that have been prepared (herramientas/preparar_paquete.py)."""
    raiz = os.path.join(CATALOGO, "paquetes")
    out = []
    if not os.path.isdir(raiz):
        return out
    for pid in sorted(os.listdir(raiz)):
        f = os.path.join(raiz, pid, "paquete.json")
        if not os.path.exists(f):
            continue
        pk = json.load(open(f, encoding="utf-8"))
        # private (a client's own photos) and retired (the pre-fal library, kept on disk
        # so old shoots still show their samples) never reach the library
        if pk.get("privado") or pk.get("retirado") or pid.startswith("u_"):
            continue
        # curating a package = deleting a sample's NN.jpg: a shot whose photo is gone is not offered
        tomas = [t for t in pk.get("tomas", []) if t.get("receta") and t.get("foto")
                 and os.path.exists(os.path.join(raiz, pid, t["foto"]))]
        if not tomas:
            continue
        url = f"/catalogo/paquetes/{pid}/"
        out.append({"id": pid, "label": pk.get("label", pid), "hint": pk.get("hint", ""),
                    "genero": pk.get("genero") or ("f" if pk.get("corte") == "f" else "m" if pk.get("corte") == "m" else "u"),
                    "n": len(tomas), "portada": url + pk.get("portada", tomas[0]["foto"]),
                    "fotos": [url + t["foto"] for t in tomas], "ids": [t["id"] for t in tomas],
                    "adulto": bool(pk.get("adulto")),
                    "lecturas": [(t.get("lectura") or {}).get("place", "") for t in tomas]})
    # the photographic stories first, then the illustrated ones, in the story order
    orden = ["paris", "amalfi", "alpes", "arte_abstracto", "scifi", "ochentas", "comic", "manga", "pixel", "animado3d",
             "boudoir_noir", "boudoir_velvet", "boudoir_blush", "boudoir_soft",
             "boudoir_classic", "boudoir_dark", "boudoir_bridal", "boudoir_playful"]
    out.sort(key=lambda p: (orden.index(p["id"].rsplit("_", 1)[0]) if p["id"].rsplit("_", 1)[0] in orden else 99, p["id"]))
    return out


def catalogo() -> dict:
    cat = json.load(open(os.path.join(CATALOGO, "catalogo.json"), encoding="utf-8"))
    cat["poses"] = json.load(open(os.path.join(CATALOGO, "poses", "index.json"), encoding="utf-8"))
    cat["paquetes"] = paquetes()
    return cat


def planificar_paquete(pid: str) -> list[dict]:
    """One shot per package photo, each regenerated from its recipe."""
    pk = json.load(open(os.path.join(CATALOGO, "paquetes", pid, "paquete.json"), encoding="utf-8"))
    tomas = []
    D = os.path.join(CATALOGO, "paquetes", pid)
    for k, t in enumerate(x for x in pk["tomas"] if x.get("receta") and x.get("foto")
                          and os.path.exists(os.path.join(D, x["foto"]))):
        r = t["ratio"]
        sk = os.path.join(CATALOGO, "paquetes", pid, t["foto"].rsplit(".", 1)[0] + "_pose.png")
        tomas.append({"n": k + 1, "id_muestra": t["id"], "pose": None, "ilustrado": bool(pk.get("ilustrado")), "framing": t.get("encuadre") if t.get("encuadre") in ("full", "half", "closeup")
                      else "full" if r in ("2:3", "9:16") else "half",
                      "prompt": t["receta"], "ratio": r, "seed": t["seed"],
                      "cara_prompt": t.get("cara_prompt"),
                      "expresion": (t.get("lectura") or {}).get("expression", ""),
                      "luz": (t.get("lectura") or {}).get("light", ""),
                      # R3: the sample's own skeleton. Picked by eye on pruebas/exp9 --
                      # it keeps the leap, the flying coat and the laugh, which the
                      # likeness score undervalues on small, turned faces.
                      "esqueleto": sk if os.path.exists(sk) else None,
                      "muestra": f"/catalogo/paquetes/{pid}/{t['foto']}"})
    return tomas


def _por_id(lista, i):
    for e in lista:
        if e["id"] == i:
            return e
    raise KeyError(i)


def texto_vestuario(cat, vestuario_id: str, corte: str = "n", propio: str = "",
                    extra: str = "") -> str:
    if vestuario_id == "own":
        base = propio or "the same outfit as in the full-length photo"
    else:
        p = _por_id(cat["vestuarios"], vestuario_id)["prompt"]
        base = p.get(corte) or p["n"]
    return (base + (", " + extra.strip() if extra.strip() else "")).strip()


def prompt_toma(cat, eleccion: dict, pose: dict, pose_en_texto: bool = False) -> tuple[str, str]:
    """(prompt, ratio) for one shot.

    `pose_en_texto`: the pose is described in words instead of passed as a
    skeleton, which leaves the person sheet as the only reference and lets the
    shot go from 1.0 MP to ~1.8 MP (QwenStudio's ceiling is per reference count).
    """
    c = _por_id(cat["conceptos"], eleccion["concepto"])
    a = _por_id(cat["ambientes"], eleccion["ambiente"])
    l = _por_id(cat["luces"], eleccion["luz"])
    v = eleccion.get("vestuario_texto") or texto_vestuario(cat, eleccion["vestuario"],
                                                          eleccion.get("corte", "n"))
    ratio, frase = ENCUADRE[pose["framing"]]
    frase = (categorias().get(pose["framing"]) or {}).get("encuadre", frase)
    quien = f"of the subject, {pose['desc']}," if pose_en_texto and pose.get("desc") else "of the subject"
    txt = f"{c['prompt']} {quien} {a['prompt']}, wearing {v}, {l['prompt']}. {frase}"
    return txt, ratio


def planificar(cat, eleccion: dict, total: int = 30, semilla: int = 1000,
               pose_en_texto: bool = False) -> list[dict]:
    """Spread `total` shots across the chosen poses, full and half alternating.

    Each pose gets an equal share; the remainder goes to the first ones picked.
    Every shot has its own seed, so two shots of one pose are two photographs.
    """
    poses = [_por_id(cat["poses"], p) for p in eleccion["poses"]]
    if not poses:
        raise ValueError("pick at least one pose")
    llenas = [p for p in poses if p["framing"] == "full"]
    medias = [p for p in poses if p["framing"] != "full"]
    orden = []
    i = j = 0
    while len(orden) < total:
        if llenas and (not medias or len(orden) % 2 == 0):
            orden.append(llenas[i % len(llenas)]); i += 1
        else:
            orden.append(medias[j % len(medias)]); j += 1
    tomas = []
    for k, pose in enumerate(orden):
        prompt, ratio = prompt_toma(cat, eleccion, pose, pose_en_texto)
        tomas.append({"n": k + 1, "pose": pose["id"], "framing": pose["framing"],
                      "prompt": prompt, "ratio": ratio, "seed": semilla + k * 7919})
    return tomas
