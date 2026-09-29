"""Make an AI-Toolkit Qwen-Image 2.1 LoRA fully loadable by diffusers (QwenStudio).

    python herramientas/convertir_lora_qwen21.py <in.safetensors> <out.safetensors>

AI-Toolkit trains the image MLP as ONE fused linear, `img_mlp.gate_up` = [gate_layer; proj]
(extensions_built_in/diffusion_models/qwen_image_2/src/transformer.py). Diffusers has two,
`img_mlp.gate_layer` and `img_mlp.proj`, so it DROPS those LoRA weights -- silently, with only
an "unexpected keys" line in the log: every MLP adapter of all 32 blocks was being ignored.
A LoRA product B·A on the fused layer splits exactly: A is shared, B's rows split in half.
"""
import sys

from safetensors.torch import load_file, save_file


def convertir(src: str, dst: str) -> int:
    sd = load_file(src)
    out, n = {}, 0
    for k, v in sd.items():
        if ".img_mlp.gate_up." not in k:
            out[k] = v
            continue
        if "lora_A" in k:
            out[k.replace("gate_up", "gate_layer")] = v.clone()
            out[k.replace("gate_up", "proj")] = v.clone()
        elif "lora_B" in k:
            mitad = v.shape[0] // 2
            out[k.replace("gate_up", "gate_layer")] = v[:mitad].contiguous()
            out[k.replace("gate_up", "proj")] = v[mitad:].contiguous()
            n += 1
        else:                                  # alpha or other per-layer scalars
            out[k.replace("gate_up", "gate_layer")] = v.clone()
            out[k.replace("gate_up", "proj")] = v.clone()
    save_file(out, dst)
    return n


if __name__ == "__main__":
    print("split", convertir(sys.argv[1], sys.argv[2]), "fused MLP adapters")
