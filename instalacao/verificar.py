"""
Verificação rápida da instalação: dependências, GPU, modelos e VAD.
Uso: python instalacao/verificar.py [--completo]   (--completo confere o SHA-256 dos modelos)
"""

import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PYTHONUTF8", "1")


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def falha(msg: str) -> None:
    print(f"  [ERRO] {msg}")


def main() -> int:
    erros = 0
    completo = "--completo" in sys.argv
    print("Verificando a instalação do GMP Tradutor...")

    # 1) pacotes
    for pacote in ("faster_whisper", "ctranslate2", "onnxruntime", "sentencepiece", "fastapi", "uvicorn", "docx", "numpy"):
        try:
            __import__(pacote)
            ok(f"pacote {pacote}")
        except Exception as e:
            falha(f"pacote {pacote}: {e}")
            erros += 1

    # 2) GPU
    try:
        from servidor import gpu
        if gpu.cuda_disponivel():
            ok(f"GPU NVIDIA utilizável: {gpu.nome_gpu() or 'sim'}")
        else:
            print(f"  [--]   sem GPU NVIDIA utilizável: será usada a CPU ({gpu.nucleos_fisicos()} núcleos físicos)")
    except Exception as e:
        falha(f"detecção de GPU: {e}")

    # 3) modelos
    from servidor import config
    pasta = config.pasta_modelos()
    whispers = [p for p in pasta.glob("whisper-*") if (p / "model.bin").exists()]
    if whispers:
        ok("Whisper: " + ", ".join(p.name.replace("whisper-", "") for p in whispers))
    else:
        falha(f"nenhum modelo Whisper em {pasta}")
        erros += 1
    nllbs = [p for p in pasta.glob("nllb-*") if (p / "model.bin").exists()]
    if nllbs:
        ok("NLLB-200: " + ", ".join(p.name.replace("nllb-200-distilled-", "") for p in nllbs))
    else:
        falha("modelo NLLB não encontrado")
        erros += 1
    if completo:
        from instalacao.baixar_modelos import _verificar_pasta
        for sub in sorted(pasta.iterdir()):
            m = sub / "manifesto.json"
            if m.exists():
                with open(m, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                problemas = _verificar_pasta(sub, meta, completo=True)
                if problemas:
                    falha(f"{sub.name}: " + "; ".join(problemas))
                    erros += 1
                else:
                    ok(f"{sub.name}: SHA-256 confere")

    # 4) VAD
    try:
        import numpy as np
        from servidor.vad import VadSilero
        v = VadSilero()
        p = v.probabilidade(np.zeros(512, dtype=np.float32))
        ok(f"VAD Silero carregado (silêncio = {p:.2f})")
    except Exception as e:
        falha(f"VAD: {e}")
        erros += 1

    # 5) navegador
    from servidor import navegador
    encontrados = [c for c in navegador._candidatos() if c and Path(c).exists()]
    if encontrados:
        ok(f"navegador: {encontrados[0]}")
    else:
        print("  [--]   Chrome/Edge não encontrados; será usado o navegador padrão")

    print()
    if erros:
        print(f"Foram encontrados {erros} problema(s). Rode instalar.bat novamente.")
        return 1
    print("Tudo certo. Use iniciar.bat para começar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
