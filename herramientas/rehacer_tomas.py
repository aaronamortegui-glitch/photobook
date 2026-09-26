"""Redraw the library shots the user crossed out (2026-09-26): faces and feet gone wrong,
contorted bodies, pixel-art portraits that were not pixel art. Each gets a new, simpler
action with attitude and a less frontal camera; the drawing prompt now also asks for one
person with natural anatomy (crear_paquete_fal.CALIDAD_DIBUJO).

    python herramientas/rehacer_tomas.py
Then: recortar_muestras, esqueletos_paquete, preparar_paquete for the packages touched.
"""
import json, os, shutil, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "herramientas"))

NUEVAS = {  # (story, shot): (camera, action, place or None to keep)
 ("amalfi", "03"): ("three-quarter view from the stern", "sitting on the bow of a small wooden boat, legs over the side, one hand on the hat, laughing", None),
 ("amalfi", "06"): ("candid three-quarter view", "reaching up to pick a lemon from a branch, laughing over the shoulder", None),
 ("amalfi", "08"): ("eye level, candid, mid-stride", "walking across the piazza with a gelato cone, a playful grin", None),
 ("alpes", "06"): ("from inside the cabin, over the shoulder", "leaning on the window rail, looking out at the valley below, amazed", None),
 ("alpes", "08"): ("side view, soft steam light", "sitting on the edge of the pool with the legs in the steaming water, eyes closed, smiling", None),
 ("pixel", "01"): ("side view, classic platformer", "walking out of a cottage door, waving to the player", None),
 ("pixel", "02"): ("chunky low-resolution pixel portrait, like a 64x64 dialogue sprite", "winking, cheerful", None),
 ("pixel", "05"): ("side view", "holding a torch up, peering into the dark, cautious", None),
 ("pixel", "06"): ("side view, the hero large in the foreground", "raising a glowing sword, a big pixel dragon rearing behind", None),
 ("pixel", "08"): ("side view, festival stage", "raising a trophy above the head, villagers cheering", None),
 ("animado3d", "04"): ("three-quarter view", "sitting astride a giant paper airplane, holding its edge, hair blowing, delighted", None),
 ("scifi", "06"): ("low three-quarter angle", "leaning on a parked hover-bike, helmet under the arm, confident half smile", None),
 ("scifi", "07"): ("three-quarter view", "floating weightless, reaching for a drifting tablet, laughing", None),
 ("ochentas", "06"): ("close-up, direct flash, candid", "laughing, taking a selfie with a vintage instant camera held at arm's length", None),
}
TACHADAS = {"amalfi_f": ["03"], "amalfi_m": ["03", "06", "08"], "alpes_f": ["06", "08"], "alpes_m": ["06", "08"],
            "pixel_f": ["01", "08"], "pixel_m": ["01", "02", "05", "06", "08"], "animado3d_f": ["04"],
            "animado3d_m": ["04"], "scifi_f": ["06", "07"], "scifi_m": ["06"], "ochentas_f": ["06"], "ochentas_m": ["06"]}

if __name__ == "__main__":
    fuera = os.path.join(RAIZ, "pruebas", "libreria_seedream", "descartes")
    os.makedirs(fuera, exist_ok=True)
    for pid, ids in TACHADAS.items():
        historia = pid.rsplit("_", 1)[0]
        D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
        f = os.path.join(D, "paquete.json")
        pk = json.load(open(f, encoding="utf-8"))
        for t in pk["tomas"]:
            if t["id"] not in ids:
                continue
            cam, desc, lugar = NUEVAS[(historia, t["id"])]
            t.update({"camara": cam, "desc": desc})
            if lugar:
                t["lugar"] = lugar
            for k in ("lectura", "receta", "cara_prompt", "prompt"):
                t.pop(k, None)
            m = os.path.join(RAIZ, "catalogo", "_masters", pid, f"{t['id']}.png")
            if os.path.exists(m):
                shutil.move(m, os.path.join(fuera, f"{pid}_{t['id']}_v1.png"))
            for x in (f"{t['id']}.jpg", f"{t['id']}_pose.png"):
                if os.path.exists(os.path.join(D, x)):
                    os.remove(os.path.join(D, x))
        json.dump(pk, open(f, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        print("reset", pid, ids)
