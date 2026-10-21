#!/bin/sh
# Início do container: baixa os modelos (só na primeira vez) e sobe o servidor.
#
# Variáveis de ambiente úteis (configure no Coolify):
#   GMP_SENHA            senha pedida na tela (recomendado em servidor público)
#   GMP_WHISPER_MODELO   auto | tiny | base | small | medium | large-v3-turbo
#   GMP_NLLB_MODELO      auto | 600M | 1.3B
#   GMP_DISPOSITIVO      auto | cpu | cuda
set -e
cd /app

# Bibliotecas CUDA instaladas via pip (só existem na imagem com GPU=1)
LIBS="$(python - <<'EOF'
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
if [ -n "$LIBS" ]; then
  export LD_LIBRARY_PATH="$LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

echo "== GMP Tradutor: conferindo os modelos em /app/modelos (o primeiro download leva alguns minutos) =="
python instalacao/baixar_modelos.py

echo "== GMP Tradutor: iniciando o servidor na porta ${GMP_PORTA:-8765} =="
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
exec python -m servidor --sem-navegador "$@"
