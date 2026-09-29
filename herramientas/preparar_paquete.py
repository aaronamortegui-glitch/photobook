"""Turn a folder of package photos into recipes -- the one-time curation step.

    python herramientas/preparar_paquete.py paris

For each photo NN.png in catalogo/paquetes/<id>/, Qwen3-VL reads place, wear,
pose, expression and light (photobook/lectura.py). The recipe the client's
shot is regenerated from is then:
  - the package's own prompt when we generated the photo (measured best,
    pruebas/exp7 R2), with the read expression added;
  - the read description when the photo is a real one and has no prompt.
The face pass is told the expression and the light, so it stops putting the
close-up's neutral face back. Everything lands in paquete.json, where a person
can read and correct it before the package is offered.
"""
import json, os, sys
from PIL import Image
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook import motor_qwen as Q, lectura as L

PREGUNTA_DETALLE = (
    "Describe this photograph so it can be recreated with a DIFFERENT woman, in one paragraph of "
    "at most 90 words, as a photographer would: the camera angle and lens; the light (direction, "
    "hardness, colour, what is lit and what falls into shadow); colour or black and white, the colour "
    "grade, film grain and contrast; the set and props; the garment in exact detail (colour, lace, "
    "cut); the body pose; where the head turns and where the eyes look. Say 'the woman'. Never "
    "describe her hair, face, skin, tattoos, age or body type.")

RATIOS = {"2:3": 2 / 3, "3:4": 3 / 4, "1:1": 1.0, "4:3": 4 / 3, "3:2": 3 / 2, "16:9": 16 / 9, "9:16": 9 / 16}


def ratio_de(ruta):
    w, h = Image.open(ruta).size
    return min(RATIOS, key=lambda k: abs(RATIOS[k] - w / h))


def main(pid):
    D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
    pk_path = os.path.join(D, "paquete.json")
    pk = json.load(open(pk_path, encoding="utf-8")) if os.path.exists(pk_path) else {"id": pid, "label": pid, "tomas": []}
    por_id = {t["id"]: t for t in pk.get("tomas", [])}
    fotos = sorted(f for f in os.listdir(D) if f[:2].isdigit() and f.endswith((".png", ".jpg")) and "_" not in f)
    tomas = []
    for k, f in enumerate(fotos):
        tid = f.split(".")[0]
        t = por_id.get(tid, {"id": tid})
        ruta = os.path.join(D, f)
        if not t.get("lectura"):
            t["lectura"] = {k2: v for k2, v in L.leer(ruta).items() if not k2.startswith("_")}
        lec = t["lectura"]
        if pk.get("receta_detallada"):
            # the scene in full detail (the user, 2026-09-26): with a depth map the
            # geometry comes from the sample, so the words must carry everything a depth
            # map cannot -- light, colour or black and white, grain, lens, garment, set,
            # where the head turns -- and never the sample model's own looks
            if not t.get("escena_detallada"):
                t["escena_detallada"] = " ".join(Q.describir(ruta, PREGUNTA_DETALLE, max_tokens=260).split())
            t["receta"] = (f"{pk.get('estilo', 'A photograph')}. {t['escena_detallada'].rstrip('.')}. "
                           f"{lec.get('expression', '')}. {pk.get('estilo_cierre', '')}").replace(" . ", " ").strip()
        elif t.get("prompt"):
            base = t["prompt"].rstrip(".")
            t["receta"] = base if lec.get("expression", "") in base else f"{base}, {lec['expression']}."
        else:
            # a real photo, read: the package's own style when it has one (a studio portrait set is not
            # "a candid travel photograph"), and its closing line
            t["receta"] = L.prompt_regenerar(lec, estilo=pk.get("estilo") or "A candid travel photograph")
            if pk.get("estilo_cierre"):
                t["receta"] = t["receta"].rstrip() + " " + pk["estilo_cierre"]
        t["cara_prompt"] = L.prompt_cara(lec)
        t["ratio"] = t.get("ratio") or ratio_de(ruta)
        t["seed"] = t.get("seed") or 5100 + k
        t["foto"] = f
        tomas.append(t)
        print(tid, "|", t["receta"], flush=True)
    Q.liberar_vision()
    pk["tomas"] = tomas
    pk["portada"] = pk.get("portada") or fotos[0]
    json.dump(pk, open(pk_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("PREPARADO", len(tomas))


if __name__ == "__main__":
    main(sys.argv[1])
