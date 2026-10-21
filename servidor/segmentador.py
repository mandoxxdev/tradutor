"""
Segmentador de falas: recebe o áudio contínuo do microfone (16 kHz, mono),
passa pelo VAD e decide onde cada frase começa e termina.

Eventos (callbacks, chamados na thread que alimenta o segmentador):
  ao_iniciar(id)                 - começou uma fala
  ao_parcial(id, audio)          - a pessoa continua falando; `audio` é tudo até agora
  ao_finalizar(id, audio)        - a frase terminou (silêncio) ou atingiu o tamanho máximo
  ao_cancelar(id)                - era só um ruído curto, descarta

Toda a contagem de tempo é feita por amostras, e não pelo relógio, para que
o comportamento seja idêntico com microfone ao vivo ou com arquivo de áudio.
"""

import logging
from collections import deque
from typing import Callable

import numpy as np

from .vad import TAMANHO_BLOCO, TAXA, VadSilero

log = logging.getLogger("gmp.segmentador")

MS_POR_BLOCO = TAMANHO_BLOCO * 1000 / TAXA  # 32 ms


class Segmentador:
    def __init__(
        self,
        vad: VadSilero,
        limiar_inicio: float = 0.5,
        limiar_fim: float = 0.35,
        silencio_fim_ms: int = 600,
        fala_minima_ms: int = 300,
        pre_fala_ms: int = 300,
        duracao_maxima_s: float = 20.0,
        corte_suave_apos_s: float = 12.0,
        intervalo_parcial_s: float = 2.0,
        parciais: bool = True,
        ao_iniciar: Callable[[int], None] | None = None,
        ao_parcial: Callable[[int, np.ndarray], None] | None = None,
        ao_finalizar: Callable[[int, np.ndarray], None] | None = None,
        ao_cancelar: Callable[[int], None] | None = None,
    ):
        self.vad = vad
        self.limiar_inicio = limiar_inicio
        self.limiar_fim = limiar_fim
        self.silencio_fim_ms = silencio_fim_ms
        self.fala_minima_ms = fala_minima_ms
        self.duracao_maxima = int(duracao_maxima_s * TAXA)
        self.corte_suave_apos = int(corte_suave_apos_s * TAXA)
        self.intervalo_parcial = int(intervalo_parcial_s * TAXA)
        self.parciais = parciais
        self.ao_iniciar = ao_iniciar or (lambda i: None)
        self.ao_parcial = ao_parcial or (lambda i, a: None)
        self.ao_finalizar = ao_finalizar or (lambda i, a: None)
        self.ao_cancelar = ao_cancelar or (lambda i: None)

        n_pre = max(1, int(pre_fala_ms / MS_POR_BLOCO))
        self._pre_fala: deque[np.ndarray] = deque(maxlen=n_pre)  # blocos antes da fala (para não cortar o início)
        self._resto = np.zeros(0, dtype=np.float32)              # amostras que ainda não fecharam um bloco
        self._em_fala = False
        self._buffer: list[np.ndarray] = []
        self._amostras_buffer = 0
        self._silencio_ms = 0.0
        self._fala_ms = 0.0
        self._desde_parcial = 0
        self._id = 0
        self.falando = False  # exposto para a interface ("ouvindo...")

    # ------------------------------------------------------------------
    def reiniciar(self) -> None:
        """Descarta a fala em andamento (ex.: ao pausar o microfone)."""
        if self._em_fala:
            self.ao_cancelar(self._id)
        self._em_fala = False
        self.falando = False
        self._buffer = []
        self._amostras_buffer = 0
        self._resto = np.zeros(0, dtype=np.float32)
        self._pre_fala.clear()
        self.vad.reiniciar()

    def alimentar(self, amostras: np.ndarray) -> None:
        """Recebe amostras float32 (qualquer quantidade) a 16 kHz."""
        if amostras.dtype != np.float32:
            amostras = amostras.astype(np.float32)
        dados = np.concatenate([self._resto, amostras]) if self._resto.size else amostras
        n_blocos = dados.shape[0] // TAMANHO_BLOCO
        for i in range(n_blocos):
            self._processar_bloco(dados[i * TAMANHO_BLOCO:(i + 1) * TAMANHO_BLOCO])
        self._resto = dados[n_blocos * TAMANHO_BLOCO:].copy()

    def finalizar_pendente(self) -> None:
        """Fecha a fala em andamento (fim do arquivo de áudio / fim da reunião)."""
        if self._em_fala:
            self._fechar(forcado=True)

    # ------------------------------------------------------------------
    def _processar_bloco(self, bloco: np.ndarray) -> None:
        prob = self.vad.probabilidade(bloco)

        if not self._em_fala:
            if prob >= self.limiar_inicio:
                self._id += 1
                self._em_fala = True
                self.falando = True
                self._buffer = list(self._pre_fala) + [bloco.copy()]
                self._amostras_buffer = sum(b.shape[0] for b in self._buffer)
                self._silencio_ms = 0.0
                self._fala_ms = MS_POR_BLOCO
                self._desde_parcial = 0
                self.ao_iniciar(self._id)
            else:
                self._pre_fala.append(bloco.copy())
            return

        # em fala
        self._buffer.append(bloco.copy())
        self._amostras_buffer += bloco.shape[0]
        self._desde_parcial += bloco.shape[0]
        if prob >= self.limiar_fim:
            self._silencio_ms = 0.0
            self._fala_ms += MS_POR_BLOCO
        else:
            self._silencio_ms += MS_POR_BLOCO

        # 1) silêncio suficiente: frase terminou
        if self._silencio_ms >= self.silencio_fim_ms:
            self._fechar(forcado=False)
            return

        # 2) frase longa com uma pausa curta: corta aqui para não atrasar a tradução
        if self._amostras_buffer >= self.corte_suave_apos and self._silencio_ms >= 250:
            self._fechar(forcado=True, continuar=True)
            return

        # 3) limite duro de duração
        if self._amostras_buffer >= self.duracao_maxima:
            self._fechar(forcado=True, continuar=True)
            return

        # 4) parcial periódica (só depois de 1 s de fala, para o idioma ser detectável)
        if self.parciais and self._desde_parcial >= self.intervalo_parcial and self._fala_ms >= 1000:
            self._desde_parcial = 0
            self.ao_parcial(self._id, self._audio_atual())

    def _audio_atual(self) -> np.ndarray:
        return np.concatenate(self._buffer) if self._buffer else np.zeros(0, dtype=np.float32)

    def _fechar(self, forcado: bool, continuar: bool = False) -> None:
        audio = self._audio_atual()
        id_atual = self._id
        # Remove o excesso de silêncio do final (deixa ~200 ms)
        if not forcado and self._silencio_ms > 200:
            sobra = int((self._silencio_ms - 200) / 1000 * TAXA)
            if 0 < sobra < audio.shape[0]:
                audio = audio[:-sobra]

        self._buffer = []
        self._amostras_buffer = 0
        self._desde_parcial = 0
        if continuar:
            # A pessoa continua falando: abre imediatamente uma nova fala
            self._id += 1
            self._silencio_ms = 0.0
            self._fala_ms = 0.0
            self.ao_iniciar(self._id)
        else:
            self._em_fala = False
            self.falando = False
            self._pre_fala.clear()

        if self._fala_ms_total(audio) < self.fala_minima_ms and not forcado:
            self.ao_cancelar(id_atual)
            return
        if audio.shape[0] < int(0.2 * TAXA):
            self.ao_cancelar(id_atual)
            return
        self.ao_finalizar(id_atual, audio)
        if not continuar:
            self._fala_ms = 0.0

    def _fala_ms_total(self, audio: np.ndarray) -> float:
        return self._fala_ms
