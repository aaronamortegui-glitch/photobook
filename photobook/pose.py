"""DWPose skeletons without torch, in Photobook's own light environment.

easy-dwpose runs its two models with onnxruntime; torch is imported only for a
decorator, and matplotlib only to colour the hand bones. Both are stubbed here
when they are missing, so the skeletons come out the same as with the full
package (the catalogue's were made that way) without pulling in ~3 GB of torch.

    python -m photobook.pose <image> [<image> ...]     writes <image>_pose.png
"""
from __future__ import annotations

import colorsys
import sys
import types

import numpy as np
from PIL import Image


def _stubs() -> None:
    try:
        import torch  # noqa: F401
    except ImportError:
        t = types.ModuleType("torch")
        t.inference_mode = lambda *a, **k: (lambda f: f)
        sys.modules["torch"] = t
    try:
        import matplotlib.colors  # noqa: F401
    except ImportError:
        m, c = types.ModuleType("matplotlib"), types.ModuleType("matplotlib.colors")
        c.hsv_to_rgb = lambda hsv: np.array(colorsys.hsv_to_rgb(*hsv))
        m.colors = c
        sys.modules["matplotlib"], sys.modules["matplotlib.colors"] = m, c


_det = None


def detector():
    global _det
    if _det is None:
        _stubs()
        from easy_dwpose import DWposeDetector   # downloads its two .onnx files once
        # it reads and writes them in "./checkpoints": pin that to modelos/, whatever the
        # folder the app was started from
        import os
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modelos")
        os.makedirs(d, exist_ok=True)
        antes = os.getcwd()
        os.chdir(d)
        try:
            _det = DWposeDetector(device="cpu")
        finally:
            os.chdir(antes)
    return _det


def esqueleto(im: Image.Image) -> Image.Image | None:
    """The OpenPose skeleton (body, hands, face) at the image's size, or None when no
    person is found."""
    im = im.convert("RGB")
    sk = detector()(im, output_type="pil", include_hands=True, include_face=True).resize(im.size)
    return sk if np.asarray(sk).max() >= 30 else None


if __name__ == "__main__":
    for f in sys.argv[1:]:
        sk = esqueleto(Image.open(f))
        if sk is None:
            print("empty", f, flush=True)
            continue
        dst = f.rsplit(".", 1)[0] + "_pose.png"
        sk.save(dst)
        print("ok", dst, flush=True)
