"""Build a package's sample photos on fal (Seedream 4.5 by default), not on the local GPU.

    python herramientas/crear_paquete_fal.py <package id> [shot ids...]

Sunburst on fal only exists as an edit, so every sample is drawn FROM a reference:
the package's house model (avatares/<modelo>_cara_hq.png + _cuerpo_hq.png). That is
also what keeps one character across the whole package, in any style.

The 4K master is kept in catalogo/_masters/<id>/ (local, not in the repository); the
package gets a 2048 px JPEG -- what the page shows and the recipe is read from. The
client is regenerated from the shot's prompt ("the subject", never the house model's
looks) and the sample's skeleton, as with every package (R3).
Then run esqueletos + preparar_paquete as for any package.
"""
import json, os, sys, time, urllib.request
from PIL import Image
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook import fal_inpaint as FAL, tomas as T

# fal caps an image at ~8.3 MP (4K UHD): ask inside the cap so the proportions hold
# (a 3:4 asked at 3072x4096 came back 2:3)
TAM_4K = {"2:3": (2336, 3520), "3:4": (2496, 3328), "1:1": (2880, 2880), "9:16": (2160, 3840)}


# the engines tried for the library (fal prices, 2026-09-26): Sunburst is billed by tokens
# and is the dearest at 4K; Nano Banana Pro $0.15/image, Seedream 4.5 $0.04/image
MOTORES = {"sunburst": "openai/gpt-image-2.5/sunburst/edit",
           "nbpro": "fal-ai/nano-banana-pro/edit",
           "seedream": "fal-ai/bytedance/seedream/v4.5/edit"}
# added to every drawing after the user's review of the first library: crossed-out shots
# had broken faces and feet, contorted bodies, or a posed, frontal stiffness
CALIDAD_DIBUJO = ("Exactly one main person. Natural anatomy: a real face, two hands, two feet, correct "
                  "limbs. A candid moment, caught doing something with attitude, not posing for the camera.")
MOTOR = os.environ.get("PHOTOBOOK_MOTOR_LIBRERIA", "seedream")   # the library was drawn on it
RATIO_NB = {"2:3": "2:3", "3:4": "3:4", "1:1": "1:1", "9:16": "9:16"}


def dibujar(prompt, refs, ancho, alto, destino, calidad="high", motor=None):
    motor = motor or MOTOR
    urls = [FAL._uri(r, "JPEG") for r in refs]
    if motor == "nbpro":
        r = min(RATIO_NB, key=lambda k: abs(eval(k.replace(":", "/")) - ancho / alto))
        args = {"prompt": prompt, "image_urls": urls, "aspect_ratio": RATIO_NB[r], "resolution": "4K",
                "output_format": "png", "num_images": 1}
    elif motor == "seedream":
        # as large as it allows (each side <= 4096) with the SAME proportions -- clipping
        # one side alone gave 3520x4096 for a 3:4 (fixed afterwards by recortar_muestras.py)
        k = 4096 / max(ancho, alto)
        args = {"prompt": prompt, "image_urls": urls, "num_images": 1,
                "image_size": {"width": int(ancho * k) // 16 * 16, "height": int(alto * k) // 16 * 16}}
    else:
        args = {"prompt": prompt, "image_urls": urls, "image_size": {"width": ancho, "height": alto},
                "quality": calidad, "output_format": "png", "num_images": 1}
    t0 = time.time()
    sub = FAL._pedir(FAL.COLA + MOTORES[motor], args)
    while True:
        st = FAL._pedir(sub["status_url"])
        if st.get("status") == "COMPLETED":
            break
        if st.get("status") in ("FAILED", "ERROR") or time.time() - t0 > 900:
            raise RuntimeError(f"fal {st.get('status')}: {json.dumps(st)[:300]}")
        time.sleep(3)
    res = FAL._pedir(sub["response_url"])
    with urllib.request.urlopen(res["images"][0]["url"], timeout=300) as r:
        open(destino, "wb").write(r.read())
    return round(time.time() - t0, 1)


def main(pid, solo=None):
    D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
    M = os.path.join(RAIZ, "catalogo", "_masters", pid)
    os.makedirs(M, exist_ok=True)
    pk = json.load(open(os.path.join(D, "paquete.json"), encoding="utf-8"))
    AV = os.path.join(RAIZ, "avatares")
    refs = [os.path.join(AV, f"{pk['modelo']}_cara_hq.png"), os.path.join(AV, f"{pk['modelo']}_cuerpo_hq.png")]
    for k, t in enumerate(pk["tomas"]):
        if solo and t["id"] not in solo:
            continue
        ratio, frase = T.ENCUADRE[t["encuadre"]]
        vest = t.get("vestuario") or pk["vestuario"]
        # the style leads and closes: it is the whole point of these packages
        prompt = (f"{pk['estilo']}. {t['camara']}, the subject {t['desc']}, {t['lugar']}, "
                  f"wearing {vest}. {frase} {pk['estilo_cierre']}")
        t.update({"ratio": ratio, "seed": 5100 + k, "prompt": prompt, "foto": f"{t['id']}.jpg"})
        master = os.path.join(M, f"{t['id']}.png")
        if not os.path.exists(master):
            dibujo = (f"Draw the person from the reference images as this character -- same face, "
                      f"hair, skin tone and build, fully restyled in the style described. {prompt} "
                      f"{CALIDAD_DIBUJO}")
            try:
                s = dibujar(dibujo, refs, *TAM_4K[ratio], master)
            except Exception as ex:          # e.g. fal's content checker: skip the shot, keep going
                detalle = ex.read().decode()[:300] if hasattr(ex, "read") else str(ex)[:300]
                print(t["id"], "FALLO", detalle, flush=True)
                t["foto"] = None
                continue
            print(t["id"], "fal", s, "s", flush=True)
        im = Image.open(master).convert("RGB")
        im.thumbnail((2048, 2048), Image.LANCZOS)
        im.save(os.path.join(D, t["foto"]), quality=93)
    json.dump(pk, open(os.path.join(D, "paquete.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("MUESTRAS_LISTAS", pid, flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or None)
