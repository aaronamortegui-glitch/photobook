r"""SAM 3 masks from text, run headless on ComfyUI's own SAM 3 implementation.

The transformers build of SAM 3 needs the gated `facebook/sam3` repo. This
machine already has ComfyUI's port of it and the `sam3.1_multiplex` checkpoint,
so this script imports those directly: no ComfyUI server, no second copy of
the weights. It runs with ComfyUI's embedded Python, in its own process, and
exits when done -- the GPU is handed back before the image model runs again.

    python_embeded\python.exe sam3_masks.py jobs.json

jobs.json: {"text": "face", "threshold": 0.5,
            "items": [{"image": "a.png", "mask": "a_mask.png"}, ...]}
Writes one L-mode PNG per item and prints one JSON line per item.
"""
import json
import os
import sys
import time

COMFY = os.environ.get("PHOTOBOOK_COMFY",
                       r"D:\ComfyUI_windows_portable_nvidia\ComfyUI_windows_portable\ComfyUI")
CKPT = os.environ.get("PHOTOBOOK_SAM3_CKPT", "sam3.1_multiplex_fp16.safetensors")


def main():
    jobs = json.load(open(sys.argv[1], encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(sys.argv[1]))
    for it in jobs["items"]:
        it["image"] = os.path.join(base, it["image"])
        it["mask"] = os.path.join(base, it["mask"])
    sys.argv = [sys.argv[0]]
    sys.path.insert(0, COMFY)
    os.chdir(COMFY)

    import numpy as np
    import torch
    from PIL import Image
    import folder_paths
    import comfy.sd
    from comfy_extras.nodes_sam3 import SAM3_Detect

    t0 = time.time()
    ruta = folder_paths.get_full_path("checkpoints", CKPT)
    out = comfy.sd.load_checkpoint_guess_config(ruta, output_vae=False, output_clip=True)
    model, clip = out[0], out[1]
    textos = jobs.get("text", "face")
    cond = clip.encode_from_tokens_scheduled(clip.tokenize(textos))
    print(json.dumps({"loaded_s": round(time.time() - t0, 1)}), flush=True)

    for it in jobs["items"]:
        t1 = time.time()
        img = Image.open(it["image"]).convert("RGB")
        arr = torch.from_numpy(np.asarray(img).astype(np.float32) / 255.0)[None]
        res = SAM3_Detect.execute(model, arr, conditioning=cond,
                                  threshold=float(jobs.get("threshold", 0.5)),
                                  refine_iterations=int(jobs.get("refine", 2)),
                                  individual_masks=bool(jobs.get("individual", False)))
        vals = res.result if hasattr(res, "result") else res
        mask = vals[0]
        m = mask[0] if mask.dim() == 3 else mask
        m = (m.float().clamp(0, 1).cpu().numpy() * 255).astype("uint8")
        Image.fromarray(m, "L").resize(img.size).save(it["mask"])
        cover = float((m > 127).mean())
        print(json.dumps({"image": it["image"], "mask": it["mask"],
                          "coverage": round(cover, 4), "s": round(time.time() - t1, 2)}),
              flush=True)


if __name__ == "__main__":
    main()
