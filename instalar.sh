#!/usr/bin/env bash
# Instalação no Linux (VPS ou PC). Roda uma única vez, precisa de internet.
#   ./instalar.sh          -> instalação padrão (Whisper + NLLB)
#   ./instalar.sh argos    -> também instala o motor alternativo Argos (puxa o PyTorch)
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONUTF8=1 PIP_DISABLE_PIP_VERSION_CHECK=1

echo "======================================================================"
echo "  GMP Tradutor - instalação"
echo "======================================================================"

PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 a 3.12 não encontrado. No Ubuntu/Debian:  sudo apt install python3.11 python3.11-venv"
  exit 1
fi
echo "Python: $($PY --version)"

# Uma .venv copiada de outra máquina (ou do Windows) não funciona aqui: recria.
if [ -e ".venv" ] && ! .venv/bin/python -c 'import sys' >/dev/null 2>&1; then
  echo "O ambiente .venv veio de outra máquina e não funciona aqui. Recriando..."
  rm -rf .venv
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "Criando o ambiente em .venv ..."
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"
"$VPY" -m pip install --upgrade pip >/dev/null
echo "Instalando dependências..."
"$VPY" -m pip install -r requirements.txt

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU NVIDIA detectada: instalando cuBLAS/cuDNN..."
  "$VPY" -m pip install -r requirements-cuda.txt || echo "Aviso: bibliotecas CUDA não instaladas; será usada a CPU."
else
  echo "Sem GPU NVIDIA: o sistema vai rodar na CPU (modelo 'small')."
fi

if [ "${1:-}" = "argos" ]; then
  echo "Instalando o Argos Translate (opcional)..."
  "$VPY" -m pip install -r requirements-argos.txt
  "$VPY" instalacao/baixar_modelos.py --argos pt en it es de fr
else
  "$VPY" instalacao/baixar_modelos.py
fi

"$VPY" instalacao/verificar.py
chmod +x iniciar.sh 2>/dev/null || true
echo
echo "Instalação concluída. Para usar:  ./iniciar.sh"
echo "Em uma VPS (acesso de outro computador), edite config.json: host 0.0.0.0, senha_acesso e https (veja o README)."
