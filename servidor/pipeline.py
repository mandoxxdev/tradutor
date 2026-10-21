"""
Pipeline: áudio de uma fala -> idioma -> texto -> tradução.

Também contém o `Trabalhador`, uma thread única que executa os modelos
(Whisper e NLLB não devem rodar em paralelo na mesma CPU: ficaria mais lento).
Falas finais têm prioridade sobre parciais; parciais atrasadas são descartadas.
"""

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from . import idiomas as tab
from .traducao import ErroTraducao, criar_motor
from .transcricao import Deteccao, Transcritor  # noqa: F401 (Deteccao é usado no cache)

log = logging.getLogger("gmp.pipeline")

TAXA_AQUECIMENTO = 16000


@dataclass
class Resultado:
    """Resultado de uma fala (parcial ou final), já no formato enviado à tela."""
    dados: dict


class Pipeline:
    def __init__(self, cfg: dict, pasta_modelos: Path, ao_progresso: Callable[[str], None] | None = None):
        progresso = ao_progresso or (lambda m: None)
        progresso("Carregando modelo de reconhecimento de fala (Whisper)...")
        self.transcritor = Transcritor(cfg["transcricao"], pasta_modelos)
        progresso("Carregando modelo de tradução...")
        self.motor = criar_motor(cfg["traducao"], pasta_modelos)
        self.idiomas_visitante: list[str] = []
        self._cache_idioma: dict[int, Deteccao] = {}
        self.ultimos_tempos: deque[float] = deque(maxlen=5)
        # Traduzir também o texto parcial (enquanto a pessoa fala): deixa a tela mais dinâmica.
        # "auto" = sim com GPU, não em CPU (custaria o dobro).
        tp = str(cfg["transcricao"].get("traduzir_parciais", "auto")).lower()
        self.traduzir_parciais = (self.transcritor.dispositivo == "cuda") if tp == "auto" else tp in ("true", "1", "sim")

    # ------------------------------------------------------------------
    def definir_idiomas(self, codigos: list[str]) -> None:
        self.idiomas_visitante = tab.validar_lista(codigos)
        self._cache_idioma.clear()

    def aquecer(self) -> None:
        """
        Roda uma transcrição e uma tradução curtas para "esquentar" os modelos.
        Na GPU a primeira chamada pode levar dezenas de segundos (inicialização do CUDA);
        fazendo isso na carga, a primeira fala da reunião já sai rápido.
        """
        inicio = time.perf_counter()
        try:
            silencio = np.zeros(TAXA_AQUECIMENTO * 2, dtype=np.float32)
            silencio[::200] = 0.01  # um pouco de sinal para o Whisper não pular tudo
            self.transcritor.detectar_idioma(silencio, {"pt"})
            self.transcritor.transcrever(silencio, tab.IDIOMAS[tab.PORTUGUES])
            self.motor.traduzir("Bom dia, sejam bem-vindos.", tab.IDIOMAS[tab.PORTUGUES], tab.IDIOMAS["en"])
        except Exception as e:  # aquecimento é opcional
            log.warning("Aquecimento dos modelos falhou (%s); seguindo mesmo assim.", e)
        log.info("Modelos aquecidos em %.1f s.", time.perf_counter() - inicio)

    def _candidatos_whisper(self) -> set[str]:
        c = {tab.IDIOMAS[tab.PORTUGUES].whisper}
        for cod in self.idiomas_visitante:
            c.add(tab.IDIOMAS[cod].whisper)
        return c

    def _idioma_da_deteccao_codigo(self, codigo_whisper: str) -> tab.Idioma | None:
        return tab.por_codigo_whisper(codigo_whisper, preferidos=self.idiomas_visitante)

    def _traduzir(self, texto: str, idioma: tab.Idioma) -> tuple[dict[str, str], list[str]]:
        """Português -> idioma(s) do visitante; qualquer outro -> português. Devolve (traduções, erros)."""
        if idioma.codigo == tab.PORTUGUES:
            destinos = [tab.IDIOMAS[c] for c in self.idiomas_visitante]
        else:
            destinos = [tab.IDIOMAS[tab.PORTUGUES]]
        traducoes: dict[str, str] = {}
        erros: list[str] = []
        validos: list[tab.Idioma] = []
        for destino in destinos:
            if not idioma.nllb and self.motor.nome == "nllb":
                erros.append(f"Sem tradução disponível para {idioma.nome_pt}.")
                traducoes[destino.codigo] = ""
            elif not self.motor.suporta(idioma, destino):
                erros.append(f"O motor {self.motor.nome} não traduz {idioma.nome_pt} → {destino.nome_pt}.")
                traducoes[destino.codigo] = ""
            else:
                validos.append(destino)
        if validos:
            try:
                # Todos os destinos em um único lote (mais rápido do que um por vez)
                traducoes.update(self.motor.traduzir_para_varios(texto, idioma, validos))
            except Exception as e:
                log.warning("Tradução em lote falhou (%s); tentando um idioma por vez.", e)
                for destino in validos:
                    try:
                        traducoes[destino.codigo] = self.motor.traduzir(texto, idioma, destino)
                    except ErroTraducao as e2:
                        erros.append(str(e2))
                        traducoes[destino.codigo] = ""
                    except Exception as e2:  # erro inesperado: não derruba a reunião
                        log.exception("Erro inesperado na tradução")
                        erros.append(f"Erro na tradução: {e2}")
                        traducoes[destino.codigo] = ""
        return traducoes, erros

    # ------------------------------------------------------------------
    def processar(self, audio: np.ndarray, id_fala: int, parcial: bool = False) -> dict | None:
        """
        Devolve o dicionário da fala (tipo "parcial" ou "fala") ou None se não houver texto.
        """
        inicio = time.perf_counter()
        candidatos = self._candidatos_whisper()

        # 1) idioma + transcrição em uma passada. Em uma fala final, reaproveita a detecção
        #    feita na parcial da mesma fala se ela foi confiável.
        previa = self._cache_idioma.get(id_fala)
        if previa is not None and not parcial and previa.prob < 0.6:
            previa = None
        deteccao, idioma, tr = self.transcritor.reconhecer(
            audio, candidatos, self._idioma_da_deteccao_codigo, parcial=parcial, deteccao_previa=previa
        )
        if parcial:
            self._cache_idioma[id_fala] = deteccao
        else:
            self._cache_idioma.pop(id_fala, None)  # fala encerrada: não guarda mais nada dela
        if not idioma.nllb:
            log.warning("Idioma sem tradução disponível: %s", idioma.rotulo)
        if not tr.texto:
            return None

        base = {
            "id": id_fala,
            "idioma": idioma.codigo,
            "rotulo": idioma.rotulo,
            "bcp47": idioma.bcp47 or idioma.codigo,
            "rtl": idioma.rtl,
            "fora_da_sessao": deteccao.fora_da_sessao,
            "coluna": "portugues" if idioma.codigo == tab.PORTUGUES else "visitante",
            "confianca_idioma": round(deteccao.prob, 2),
        }
        if parcial:
            resultado = {**base, "tipo": "parcial", "texto": tr.texto}
            if self.traduzir_parciais:
                try:
                    resultado["traducoes"], _ = self._traduzir(tr.texto, idioma)
                except Exception as e:  # parcial é "melhor esforço"
                    log.debug("Tradução parcial falhou: %s", e)
            return resultado

        # 3) tradução: português -> idioma(s) do visitante; qualquer outro -> português
        t0 = time.perf_counter()
        traducoes, erros = self._traduzir(tr.texto, idioma)
        t_traducao = time.perf_counter() - t0
        total = time.perf_counter() - inicio
        self.ultimos_tempos.append(total)

        agora = datetime.now()
        return {
            **base,
            "tipo": "fala",
            "data": agora.strftime("%Y-%m-%d"),
            "hora": agora.strftime("%H:%M:%S"),
            "original": tr.texto,
            "traducoes": traducoes,
            "erro": " | ".join(erros) if erros else None,
            "tempos": {
                "audio_s": round(tr.segundos_audio, 2),
                "transcricao_s": round(tr.segundos_processamento, 2),
                "traducao_s": round(t_traducao, 2),
                "total_s": round(total, 2),
            },
        }


# ----------------------------------------------------------------------------
@dataclass(order=True)
class _Tarefa:
    prioridade: int
    seq: int
    id_fala: int = field(compare=False)
    parcial: bool = field(compare=False)
    audio: np.ndarray = field(compare=False, repr=False)
    criada_em: float = field(compare=False)


class Trabalhador(threading.Thread):
    """Thread única que executa o pipeline. Finais primeiro; parciais velhas são puladas."""

    def __init__(self, pipeline: Pipeline, ao_resultado: Callable[[dict], None],
                 ao_estado: Callable[[str | None], None], ao_erro: Callable[[str], None]):
        super().__init__(name="gmp-trabalhador", daemon=True)
        self.pipeline = pipeline
        self.ao_resultado = ao_resultado
        self.ao_estado = ao_estado
        self.ao_erro = ao_erro
        self._fila: queue.PriorityQueue[_Tarefa] = queue.PriorityQueue()
        self._seq = 0
        self._ultima_parcial_por_id: dict[int, int] = {}
        self._finalizadas: set[int] = set()
        self._parar = threading.Event()
        self.ocupado = False

    def enviar(self, id_fala: int, audio: np.ndarray, parcial: bool) -> None:
        self._seq += 1
        if parcial:
            # Se o trabalhador está ocupado, uma parcial nova só substitui a anterior (não acumula)
            self._ultima_parcial_por_id[id_fala] = self._seq
        self._fila.put(_Tarefa(1 if parcial else 0, self._seq, id_fala, parcial, audio, time.monotonic()))

    def cancelar(self, id_fala: int) -> None:
        self._finalizadas.add(id_fala)

    def parar(self) -> None:
        self._parar.set()

    def run(self) -> None:
        while not self._parar.is_set():
            try:
                tarefa = self._fila.get(timeout=0.2)
            except queue.Empty:
                continue
            if tarefa.parcial:
                if tarefa.id_fala in self._finalizadas:
                    continue
                if self._ultima_parcial_por_id.get(tarefa.id_fala) != tarefa.seq:
                    continue  # existe parcial mais nova da mesma fala
                if time.monotonic() - tarefa.criada_em > 4.0:
                    continue  # ficou velha na fila (CPU ocupada)
            else:
                self._finalizadas.add(tarefa.id_fala)
                self._ultima_parcial_por_id.pop(tarefa.id_fala, None)

            self.ocupado = True
            try:
                self.ao_estado("transcrevendo" if tarefa.parcial else "traduzindo")
                resultado = self.pipeline.processar(tarefa.audio, tarefa.id_fala, parcial=tarefa.parcial)
                if resultado is None:
                    self.ao_resultado({"tipo": "cancelar", "id": tarefa.id_fala})
                else:
                    self.ao_resultado(resultado)
            except Exception as e:
                log.exception("Erro ao processar fala %s", tarefa.id_fala)
                self.ao_resultado({"tipo": "cancelar", "id": tarefa.id_fala})
                self.ao_erro(f"Erro ao processar a fala: {e}")
            finally:
                self.ocupado = False
                self.ao_estado(None)
            # Limpa memória de ids antigos
            if len(self._finalizadas) > 500:
                self._finalizadas = set(sorted(self._finalizadas)[-200:])
