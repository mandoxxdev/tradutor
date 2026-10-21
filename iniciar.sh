#!/usr/bin/env bash
# Sobe o servidor no Linux. Argumentos são repassados: ./iniciar.sh --sem-navegador --host 0.0.0.0
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x ".venv/bin/python" ]; then
  echo "O sistema ainda não foi instalado. Rode ./instalar.sh primeiro."
  exit 1
fi
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 PYTHONUTF8=1

# Bibliotecas CUDA instaladas via pip (só existem se houver GPU)
LIBS="$(.venv/bin/python - <<'EOF'
import os
try:
    import nvidia
    pastas = []
    for raiz in nvidia.__path__:
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            p = os.path.join(raiz, sub, "lib")
            if os.path.isdir(p):
                pastas.append(p)
    print(":".join(pastas))
except Exception:
    print("")
EOF
)"
if [ -n "$LIBS" ]; then export LD_LIBRARY_PATH="$LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"; fi

exec .venv/bin/python -m servidor "$@"
