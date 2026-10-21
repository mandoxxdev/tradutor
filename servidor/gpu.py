"""
Detecção de GPU NVIDIA e escolha de dispositivo/precisão.

No Windows, as bibliotecas CUDA (cuBLAS e cuDNN) vêm dos pacotes pip
`nvidia-cublas-cu12` e `nvidia-cudnn-cu12`; é preciso registrar as pastas
das DLLs antes de o CTranslate2 ser importado. No Linux, o iniciar.sh
exporta LD_LIBRARY_PATH; aqui fazemos um pré-carregamento como reforço.
"""

import ctypes
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger("gmp.gpu")

_preparado = False


def preparar_bibliotecas_cuda() -> None:
    """Deixa as DLLs/.so da NVIDIA (instaladas via pip) visíveis ao CTranslate2."""
    global _preparado
    if _preparado:
        return
    _preparado = True
    try:
        import nvidia  # pacote "namespace" criado pelos wheels da NVIDIA
    except ImportError:
        return
    for raiz in getattr(nvidia, "__path__", []):
        raiz = Path(raiz)
        if sys.platform == "win32":
            for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
                pasta = raiz / sub / "bin"
                if pasta.is_dir():
                    try:
                        os.add_dll_directory(str(pasta))
                    except Exception:
                        pass
                    os.environ["PATH"] = str(pasta) + os.pathsep + os.environ.get("PATH", "")
        else:
            for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
                pasta = raiz / sub / "lib"
                if pasta.is_dir():
                    for nome in sorted(pasta.glob("lib*.so*")):
                        try:
                            ctypes.CDLL(str(nome), mode=ctypes.RTLD_GLOBAL)
                        except OSError:
                            pass


def cuda_disponivel() -> bool:
    preparar_bibliotecas_cuda()
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception as e:
        log.debug("CUDA indisponível: %s", e)
        return False


def nome_gpu() -> str | None:
    """Nome da GPU (só para exibir), via nvidia-smi se existir."""
    import shutil
    import subprocess
    if not shutil.which("nvidia-smi"):
        return None
    try:
        saida = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().splitlines()
        return saida[0].strip() if saida else None
    except Exception:
        return None


def nucleos_fisicos() -> int:
    """Número de núcleos físicos (aproximação: metade dos lógicos quando há hyper-threading)."""
    logicos = os.cpu_count() or 4
    try:
        if sys.platform == "win32":
            import subprocess
            saida = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfCores -Sum).Sum"],
                capture_output=True, text=True, timeout=8,
            ).stdout.strip()
            if saida.isdigit() and int(saida) > 0:
                return int(saida)
        elif sys.platform.startswith("linux"):
            nucleos = set()
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                fis, core = None, None
                for linha in f:
                    if linha.startswith("physical id"):
                        fis = linha.split(":")[1].strip()
                    elif linha.startswith("core id"):
                        core = linha.split(":")[1].strip()
                    elif linha.strip() == "" and fis is not None and core is not None:
                        nucleos.add((fis, core))
                        fis, core = None, None
            if nucleos:
                return len(nucleos)
    except Exception:
        pass
    return max(1, logicos // 2)


def escolher_dispositivo(preferencia: str, tipo_computo: str = "auto") -> tuple[str, str]:
    """
    Devolve (dispositivo, tipo_computo) para o CTranslate2.
      - GPU: int8_float16 (rápido e leve em VRAM)
      - CPU: int8
    """
    preferencia = (preferencia or "auto").lower()
    usar_cuda = preferencia == "cuda" or (preferencia == "auto" and cuda_disponivel())
    if preferencia == "cuda" and not cuda_disponivel():
        log.warning("CUDA pedido na configuração, mas nenhuma GPU NVIDIA utilizável foi encontrada. Usando CPU.")
        usar_cuda = False
    dispositivo = "cuda" if usar_cuda else "cpu"
    if tipo_computo and tipo_computo != "auto":
        return dispositivo, tipo_computo
    return dispositivo, ("int8_float16" if usar_cuda else "int8")
