r"""Captions for a likeness LoRA dataset, written locally by Qwen3-VL (QwenStudio).

    python herramientas\recaption_lora.py <dataset folder> <trigger>

The rule for character LoRAs: describe only what CHANGES between photos -- clothes, place,
pose, framing, light, expression -- never the person's fixed traits (hair, face, skin, eyes,
make-up, build). Whatever the caption names is learned as that word; what it leaves out is
learned as the trigger. The old captions ("long straight black hair and bangs, fair skin,
defined eyebrows, red lipstick") tied her identity to generic words instead of the trigger.
"""
import glob, os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook import motor_qwen as Q

PREGUNTA = ("Write a training caption for this photo, one sentence of at most 45 words, starting "
            "exactly with '{trigger}, a woman,'. Describe ONLY: her clothing, the place and background, "
            "her pose, the camera framing (close-up, half body, full body, selfie), the lighting, and her "
            "expression. NEVER describe her hair, face, skin, eyes, eyebrows, lips, make-up, age or body.")


def main(carpeta, trigger):
    fs = sorted(glob.glob(os.path.join(carpeta, "*.jpg")) + glob.glob(os.path.join(carpeta, "*.png")))
    for f in fs:
        txt = os.path.splitext(f)[0] + ".txt"
        if os.path.exists(txt) and open(txt, encoding="utf-8").read().startswith(trigger + ", a woman,"):
            continue
        c = " ".join(Q.describir(f, PREGUNTA.format(trigger=trigger), max_tokens=120).split())
        if not c.startswith(trigger):
            c = f"{trigger}, a woman, " + c
        open(txt, "w", encoding="utf-8").write(c)
        print(os.path.basename(f), "|", c, flush=True)
    Q.liberar_vision()
    print("CAPTIONS_LISTAS", len(fs), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
