"""Any folder of photos becomes a package: the client is recreated in each one.

    D:\\QwenStudio\\.venv\\Scripts\\python.exe herramientas\\importar_carpeta.py <folder> <id> ["Label"] ["hint"]

No naming rules for the folder: every .jpg/.jpeg/.png/.webp in it is taken, in
name order, copied as 01.png, 02.png... into catalogo/paquetes/<id>/. Then, per
photo, the three things a recreation needs:

  1. DWPose skeleton -> <n>_pose.png      the pose and the moment (R3, picked by
                                          eye on pruebas/exp9)
  2. Qwen3-VL reading -> paquete.json     place, wear, expression, light --
                                          never the person in the photo
  3. the recipe and the face-pass prompt, written from that reading

Open paquete.json afterwards and read the recipes: for real photos this is the
curation step. The package then shows up in the page under "A ready-made trip".
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageOps

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DWPOSE_PY = sys.executable      # photobook/pose.py: DWPose on onnxruntime, no torch
EXT = (".jpg", ".jpeg", ".png", ".webp")
LADO_MAX = 2048


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    origen, pid = sys.argv[1], sys.argv[2]
    label = sys.argv[3] if len(sys.argv) > 3 else pid.replace("_", " ").title()
    hint = sys.argv[4] if len(sys.argv) > 4 else ""
    D = os.path.join(RAIZ, "catalogo", "paquetes", pid)
    os.makedirs(D, exist_ok=True)

    fotos = sorted(f for f in os.listdir(origen) if f.lower().endswith(EXT))
    if not fotos:
        raise SystemExit(f"no photos in {origen}")
    sys.path.insert(0, RAIZ)
    from photobook import optimizar as OP
    tomas = []
    peso_origen = OP.peso_mb([os.path.join(origen, f) for f in fotos])
    for k, f in enumerate(fotos, 1):
        src = Image.open(os.path.join(origen, f))
        tam0 = src.size
        im = OP.normalizar(src)
        tid = f"{k:02d}"
        dst = os.path.join(D, tid + ".png")
        im.save(dst, optimize=True)
        OP.mini(dst, 480)                        # the page's card, made once here
        tomas.append({"id": tid, "origen": f})
        aviso = "  (reduced from %dx%d)" % tam0 if tam0 != im.size else ""
        print(tid, "<-", f, im.size, aviso, flush=True)
    peso = OP.peso_mb([os.path.join(D, t["id"] + ".png") for t in tomas])
    print(f"weight: source {peso_origen} MB -> working files {peso} MB (cap {OP.LADO_MAX} px); "
          f"the page loads 480 px JPEG thumbnails", flush=True)

    pk_path = os.path.join(D, "paquete.json")
    pk = {"id": pid, "label": label, "hint": hint, "tomas": tomas, "origen": os.path.abspath(origen)}
    json.dump(pk, open(pk_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)

    print("skeletons...", flush=True)
    subprocess.run([DWPOSE_PY, os.path.join(RAIZ, "herramientas", "esqueletos_paquete.py"), pid], check=True)
    print("reading the photos...", flush=True)
    subprocess.run([sys.executable, os.path.join(RAIZ, "herramientas", "preparar_paquete.py"), pid], check=True)
    sin = [t["id"] for t in tomas if not os.path.exists(os.path.join(D, t["id"] + "_pose.png"))]
    if sin:
        print("no skeleton (will be recreated from the words only):", ", ".join(sin))
    print(f"IMPORTADO {pid}: {len(tomas)} photos -> {pk_path}")


if __name__ == "__main__":
    main()
