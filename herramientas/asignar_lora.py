r"""Set up (or remove) a character's personal likeness LoRA -- behind the scenes; the page
only shows whether it is active.

    python herramientas\asignar_lora.py                         list characters
    python herramientas\asignar_lora.py <name or id> <file.safetensors> <trigger>
    python herramientas\asignar_lora.py <name or id> --quitar

The file must be in QwenStudio's loras/ folder, already converted
(herramientas/convertir_lora_qwen21.py) if it comes from AI-Toolkit.
"""
import os, sys
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
from photobook import servicio as S


def main(a):
    nombres = S._nombres()
    if not a:
        for pid in nombres:
            p = S.perfil_de(pid)
            print(pid, "|", p["nombre"] or "-", "|", p["lora"] or "no likeness model")
        return
    pid = next((k for k in nombres if k == a[0] or S.perfil_de(k)["nombre"].lower() == a[0].lower()), None)
    if not pid:
        sys.exit(f"no character called {a[0]!r}")
    if a[1:] == ["--quitar"]:
        print(S.guardar_perfil(pid, lora="", trigger=""))
    else:
        print(S.guardar_perfil(pid, lora=a[1], trigger=a[2] if len(a) > 2 else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
