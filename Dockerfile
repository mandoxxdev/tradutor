# GMP Tradutor - imagem para servidor (Coolify, Docker, VPS)
#
# Os modelos NÃO ficam dentro da imagem: são baixados na primeira inicialização
# para /app/modelos. Monte um volume persistente nesse caminho para não baixar
# de novo a cada deploy.
#
# CPU (padrão):  docker build -t gmp-tradutor .
# GPU NVIDIA:    docker build --build-arg GPU=1 -t gmp-tradutor .   (e rode com --gpus all)
FROM python:3.11-slim

ARG GPU=0

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    GMP_HOST=0.0.0.0 \
    GMP_PORTA=8765

# libgomp1: paralelismo do CTranslate2/onnxruntime; curl: health check do Coolify
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependências primeiro (camada reaproveitada quando só o código muda)
COPY requirements.txt requirements-cuda.txt ./
RUN pip install -r requirements.txt \
    && if [ "$GPU" = "1" ]; then pip install -r requirements-cuda.txt; fi

COPY . .
RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh \
    && mkdir -p /app/modelos /app/dados /app/atas

EXPOSE 8765

ENTRYPOINT ["/app/docker/entrypoint.sh"]
