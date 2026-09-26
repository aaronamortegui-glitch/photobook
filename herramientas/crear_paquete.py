"""Build a ready-made photobook package: one house model, one outfit, many places.

    python herramientas/crear_paquete.py paris

Uses the same composing path as a custom shoot (person sheet + pose in words,
1.5K, 40 steps). The package is curated once, before any client sees it: bad
frames are deleted by hand and simply not offered.
"""
import json, os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook import motor_qwen as Q, tomas as T, caras as C

pid = sys.argv[1]
D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
pk = json.load(open(os.path.join(D, "paquete.json"), encoding="utf-8"))
AV = os.path.join(RAIZ, "avatares")
hoja = C.hoja_identidad(os.path.join(AV, f"{pk['modelo']}_cara_hq.png"),
                        os.path.join(AV, f"{pk['modelo']}_cuerpo_hq.png"), os.path.join(D, "_modelo.png"))
poses = {p["id"]: p for p in T.catalogo()["poses"]}
for k, t in enumerate(pk["tomas"]):
    f = os.path.join(D, f"{t['id']}.png")
    if os.path.exists(f):
        continue
    pose = poses[t["pose"]] if t.get("pose") else {"desc": t["desc"], "framing": t["encuadre"]}
    ratio, frase = T.ENCUADRE[pose["framing"]]
    vest = t.get('vestuario') or pk['vestuario']
    if pose["framing"] == "closeup" and t.get("camara"):
        # the camera leads AND closes: in this model the last words weigh most, and an
        # art portrait lives or dies by its angle, crop, light and grade (exp24 v1 came
        # back as eight identical frontal waist-up shots with the camera mid-sentence)
        prompt = (f"{t['camara']}. {pk['estilo']} of the subject, {pose['desc']}, {t['lugar']}, "
                  f"wearing {vest}. {frase} {t['camara']}.")
    else:
        cam = f", {t['camara']}," if t.get("camara") else ""   # lens and angle, for hard shots
        prompt = f"{pk['estilo']}{cam} of the subject, {pose['desc']}, {t['lugar']}, wearing {vest}. {frase}"
    t["ratio"], t["seed"] = ratio, 5100 + k
    # "sujeto": a package can describe its sample person in words instead of using the
    # house model's sheet. A person reference anchors composition to its own frontal,
    # centred framing -- the art portraits all came back straight-on -- so text-only
    # samples are free to take the angle, crop and light the shot asks for.
    # The stored prompt keeps "the subject": it becomes the client's recipe, and naming
    # the sample person's looks there would fight the client's identity.
    if pk.get("sujeto"):
        muestra = prompt.replace("of the subject,", f"of {pk['sujeto']},").replace("the subject", pk["sujeto"])
        r = Q.generar(f, prompt=muestra, ratio=ratio, megapixeles=1.77, steps=40, seed=5100 + k)
    else:
        r = Q.generar(f, prompt=prompt, personas=[hoja], ratio=ratio, megapixeles=1.77, steps=40, seed=5100 + k)
    t["prompt"] = prompt
    print(t["id"], r["segundos"], r["tam"], flush=True)
json.dump(pk, open(os.path.join(D, "paquete.json"), "w", encoding="utf-8"), indent=1)
print("PAQUETE_LISTO", flush=True)
