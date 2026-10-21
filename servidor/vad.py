"""
VAD (detecção de voz) Silero em modo contínuo ("streaming").

Usa o modelo ONNX do Silero que já vem dentro do pacote faster-whisper
(faster_whisper/assets/silero_vad_v6.onnx), rodando no onnxruntime em CPU.
Se existir modelos/silero_vad.onnx (modelo combinado v5 do projeto Silero),
ele é usado no lugar.

Cada chamada a `probabilidade(bloco)` recebe 512 amostras (32 ms a 16 kHz)
e devolve a probabilidade de haver voz, mantendo o estado interno entre
chamadas, exatamente como o Silero foi treinado para funcionar.
"""

import logging
from pathlib import Path

import numpy as np

log = logging.getLogger("gmp.vad")

TAXA = 16000
TAMANHO_BLOCO = 512        # amostras por bloco (32 ms)
TAMANHO_CONTEXTO = 64      # amostras do bloco anterior que o modelo recebe junto


def _caminho_modelo_padrao() -> Path:
    from faster_whisper.utils import get_assets_path
    pasta = Path(get_assets_path())
    for nome in ("silero_vad_v6.onnx", "silero_vad_v5.onnx", "silero_vad.onnx"):
        if (pasta / nome).exists():
            return pasta / nome
    candidatos = sorted(pasta.glob("silero*.onnx"))
    if candidatos:
        return candidatos[0]
    raise FileNotFoundError(
        "Modelo de VAD do Silero não encontrado dentro do faster-whisper. "
        "Reinstale as dependências (instalar.bat)."
    )


class VadSilero:
    """Wrapper do Silero VAD com estado persistente para áudio contínuo."""

    def __init__(self, caminho: str | Path | None = None):
        import onnxruntime as ort

        self.caminho = Path(caminho) if caminho else _caminho_modelo_padrao()
        opcoes = ort.SessionOptions()
        opcoes.inter_op_num_threads = 1
        opcoes.intra_op_num_threads = 1
        opcoes.enable_cpu_mem_arena = False
        opcoes.log_severity_level = 4
        self.sessao = ort.InferenceSession(str(self.caminho), providers=["CPUExecutionProvider"], sess_options=opcoes)
        self.entradas = {e.name for e in self.sessao.get_inputs()}
        # Dois formatos conhecidos: v6 do faster-whisper ("h" e "c") e combinado v5 ("state" e "sr")
        if {"h", "c"} <= self.entradas:
            self.formato = "hc"
        elif "state" in self.entradas:
            self.formato = "state"
        else:
            raise RuntimeError(f"Formato de modelo VAD desconhecido: entradas {sorted(self.entradas)}")
        log.info("VAD Silero carregado: %s (formato %s)", self.caminho.name, self.formato)
        self.reiniciar()

    def reiniciar(self) -> None:
        """Zera o estado (chame quando o áudio for interrompido por muito tempo)."""
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._contexto = np.zeros((1, TAMANHO_CONTEXTO), dtype=np.float32)

    def probabilidade(self, bloco: np.ndarray) -> float:
        """`bloco`: 512 amostras float32 em [-1, 1]. Devolve a probabilidade de voz (0..1)."""
        if bloco.shape[0] != TAMANHO_BLOCO:
            raise ValueError(f"O bloco deve ter {TAMANHO_BLOCO} amostras, recebeu {bloco.shape[0]}")
        x = np.concatenate([self._contexto, bloco.reshape(1, -1).astype(np.float32)], axis=1)
        if self.formato == "hc":
            saida, self._h, self._c = self.sessao.run(None, {"input": x, "h": self._h, "c": self._c})
        else:
            saida, self._state = self.sessao.run(
                None, {"input": x, "state": self._state, "sr": np.array(TAXA, dtype=np.int64)}
            )
        self._contexto = x[:, -TAMANHO_CONTEXTO:]
        return float(np.squeeze(saida))
