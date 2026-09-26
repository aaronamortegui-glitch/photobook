r"""Identity score: how much a generated face is the client's face.

ArcFace (insightface buffalo_l: SCRFD detector + w600k_r50 recogniser) through
onnxruntime on the CPU, from the model files ComfyUI already has on this
machine. No insightface package: the SCRFD decode and the 5-point alignment
are the few lines below.

Cosine similarity between embeddings. Rough reading for ArcFace r50: > 0.55 is
very likely the same person, 0.35-0.55 plausible, < 0.30 someone else. This is
a locator, not the judge -- the picture is looked at too.

    python faceid.py ref.png img1.png img2.png ...   -> JSON lines
    python faceid.py --puntos img1.png img2.png ...  -> the 5 landmarks of the
        largest face (eyes, nose, mouth corners), for aligning a rebuilt face
"""
import json
import os
import sys

import cv2
import numpy as np
import onnxruntime as ort

# buffalo_l (det_10g + w600k_r50), fetched by the installer into modelos/buffalo_l
MODELOS = os.environ.get("PHOTOBOOK_INSIGHTFACE", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modelos", "buffalo_l"))

ARC_DST = np.array([[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
                    [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)


class Caras:
    def __init__(self, ruta=MODELOS):
        so = ort.SessionOptions()
        so.log_severity_level = 3
        prov = ["CPUExecutionProvider"]
        self.det = ort.InferenceSession(os.path.join(ruta, "det_10g.onnx"), so, providers=prov)
        self.rec = ort.InferenceSession(os.path.join(ruta, "w600k_r50.onnx"), so, providers=prov)
        self.din = self.det.get_inputs()[0].name
        self.rin = self.rec.get_inputs()[0].name

    def detectar(self, img, umbral=0.5, lado=640):
        h, w = img.shape[:2]
        esc = lado / max(h, w)
        nh, nw = int(round(h * esc)), int(round(w * esc))
        lienzo = np.zeros((lado, lado, 3), dtype=np.uint8)
        lienzo[:nh, :nw] = cv2.resize(img, (nw, nh))
        blob = cv2.dnn.blobFromImage(lienzo, 1.0 / 128, (lado, lado), (127.5, 127.5, 127.5), swapRB=True)
        outs = self.det.run(None, {self.din: blob})
        cajas, puntos, notas = [], [], []
        for k, paso in enumerate((8, 16, 32)):
            sc, bb, kp = outs[k][:, 0], outs[k + 3] * paso, outs[k + 6] * paso
            g = lado // paso
            yy, xx = np.mgrid[:g, :g]
            centros = np.stack([xx, yy], -1).reshape(-1, 2).astype(np.float32) * paso
            centros = np.repeat(centros, 2, axis=0)
            sel = np.where(sc >= umbral)[0]
            c = centros[sel]
            b = bb[sel]
            cajas.append(np.stack([c[:, 0] - b[:, 0], c[:, 1] - b[:, 1],
                                   c[:, 0] + b[:, 2], c[:, 1] + b[:, 3]], -1))
            p = kp[sel].reshape(-1, 5, 2) + c[:, None, :]
            puntos.append(p)
            notas.append(sc[sel])
        cajas = np.concatenate(cajas) / esc
        puntos = np.concatenate(puntos) / esc
        notas = np.concatenate(notas)
        orden = notas.argsort()[::-1]
        keep = []
        while len(orden):
            i = orden[0]
            keep.append(i)
            xx1 = np.maximum(cajas[i, 0], cajas[orden[1:], 0])
            yy1 = np.maximum(cajas[i, 1], cajas[orden[1:], 1])
            xx2 = np.minimum(cajas[i, 2], cajas[orden[1:], 2])
            yy2 = np.minimum(cajas[i, 3], cajas[orden[1:], 3])
            inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
            a = lambda j: (cajas[j, 2] - cajas[j, 0]) * (cajas[j, 3] - cajas[j, 1])
            iou = inter / (a(i) + a(orden[1:]) - inter + 1e-6)
            orden = orden[1:][iou < 0.4]
        return [(cajas[i], puntos[i], float(notas[i])) for i in keep]

    def embedding(self, img, puntos):
        M, _ = cv2.estimateAffinePartial2D(puntos.astype(np.float32), ARC_DST, method=cv2.LMEDS)
        cara = cv2.warpAffine(img, M, (112, 112), borderValue=0)
        blob = cv2.dnn.blobFromImage(cara, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        e = self.rec.run(None, {self.rin: blob})[0][0]
        return e / np.linalg.norm(e)

    def principal(self, ruta):
        """Embedding and box of the largest face in the picture, or (None, None)."""
        img = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
        d = self.detectar(img)
        if not d:
            return None, None
        caja, pts, _ = max(d, key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]))
        return self.embedding(img, pts), [float(v) for v in caja]


def puntos(c, rutas):
    for ruta in rutas:
        img = cv2.imdecode(np.fromfile(ruta, dtype=np.uint8), cv2.IMREAD_COLOR)
        d = c.detectar(img) if img is not None else []
        if not d:
            print(json.dumps({"image": ruta, "puntos": None}), flush=True)
            continue
        caja, pts, nota = max(d, key=lambda t: (t[0][2] - t[0][0]) * (t[0][3] - t[0][1]))
        print(json.dumps({"image": ruta, "puntos": [[float(x), float(y)] for x, y in pts],
                          "box": [float(v) for v in caja], "nota": round(nota, 3)}), flush=True)


def main():
    c = Caras()
    if sys.argv[1] == "--puntos":
        return puntos(c, sys.argv[2:])
    refs = sys.argv[1].split(";")
    er = [e for e in (c.principal(r)[0] for r in refs) if e is not None]
    if not er:
        print(json.dumps({"error": "no face in the reference"}))
        return
    ref = np.mean(er, axis=0)
    ref /= np.linalg.norm(ref)
    for ruta in sys.argv[2:]:
        e, caja = c.principal(ruta)
        print(json.dumps({"image": ruta, "score": None if e is None else round(float(e @ ref), 4),
                          "box": caja}), flush=True)


if __name__ == "__main__":
    main()
