"""
Reconhecimento de fala com faster-whisper (Whisper em CTranslate2).

- Detecção automática do idioma SOMENTE entre os idiomas da sessão (português +
  idiomas do visitante): com português e italiano escolhidos, toda fala é um dos
  dois. (Opcional: "permitir_fora_da_sessao" no config.json aceita um idioma de
  fora quando o Whisper tem muita certeza dele.)
- A detecção e a transcrição são feitas em UMA passada do codificador
  (o faster-whisper reaproveita a codificação quando detecta o idioma dentro
  de `transcribe`); só repetimos quando a regra da sessão escolhe outro idioma.
- Decodificação gulosa (beam_size=1) por padrão: a mais rápida em CPU e
  suficiente para fala de reunião.
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import gpu, idiomas as tab

log = logging.getLogger("gmp.transcricao")

TAXA = 16000

# Frases que o Whisper "inventa" em silêncio/ruído (créditos de legendas etc.)
_ALUCINACOES = (
    "amara.org", "legendas pela comunidade", "sottotitoli", "subtitles by",
    "thank you for watching", "thanks for watching", "obrigado por assistir",
    "untertitelung", "sous-titres", "subtítulos realizados", "ご視聴ありがとうございました",
    "legendado por", "tradução e legendas",
)


@dataclass
class Deteccao:
    whisper: str            # código do Whisper escolhido (ex.: "it")
    prob: float             # probabilidade desse código
    global_whisper: str     # código mais provável sem restrição
    global_prob: float
    fora_da_sessao: bool    # True quando o idioma escolhido não está na sessão


@dataclass
class Transcricao:
    texto: str
    segundos_audio: float
    segundos_processamento: float


class Transcritor:
    def __init__(self, cfg: dict, pasta_modelos: Path):
        from faster_whisper import WhisperModel

        gpu.preparar_bibliotecas_cuda()
        nome = (cfg.get("modelo") or "auto").lower()
        dispositivo, tipo = gpu.escolher_dispositivo(cfg.get("dispositivo", "auto"), cfg.get("tipo_computo", "auto"))
        if nome == "auto":
            if dispositivo == "cuda":
                # large-v3-turbo: bem mais preciso que o medium, com o mesmo tamanho em disco
                turbo = pasta_modelos / "whisper-large-v3-turbo" / "model.bin"
                nome = "large-v3-turbo" if turbo.exists() else "medium"
            else:
                nome = "small"
        caminho = self._resolver_caminho(pasta_modelos, nome)
        # Acima de ~8 threads não há ganho (medido); deixa núcleos livres para o resto do sistema
        threads = int(cfg.get("threads_cpu") or 0) or min(8, gpu.nucleos_fisicos())
        beam = cfg.get("beam_size", "auto")
        if str(beam).lower() == "auto":
            beam = 5 if dispositivo == "cuda" else 1  # busca em feixe melhora a precisão; na CPU custa caro
        self.beam_size = max(1, int(beam))
        self.nome = caminho.name.replace("whisper-", "")
        self.dispositivo = dispositivo
        self.tipo_computo = tipo
        self._uma_passada = True  # detecção + transcrição com uma única codificação
        # Por padrão o idioma é escolhido só entre os da sessão (sem "idioma de fora")
        self.permitir_fora_da_sessao = bool(cfg.get("permitir_fora_da_sessao", False))

        log.info("Carregando Whisper '%s' em %s (%s, %d threads)...", self.nome, dispositivo, tipo, threads)
        inicio = time.perf_counter()
        try:
            self.modelo = WhisperModel(str(caminho), device=dispositivo, compute_type=tipo,
                                       cpu_threads=threads, num_workers=1)
        except Exception as e:
            if dispositivo == "cuda":
                log.warning("Falha ao usar a GPU (%s). Tentando em CPU...", e)
                self.dispositivo, self.tipo_computo = "cpu", "int8"
                self.modelo = WhisperModel(str(caminho), device="cpu", compute_type="int8",
                                           cpu_threads=threads, num_workers=1)
            else:
                raise
        log.info("Whisper pronto em %.1f s.", time.perf_counter() - inicio)

    @staticmethod
    def _resolver_caminho(pasta_modelos: Path, nome: str) -> Path:
        caminho = pasta_modelos / f"whisper-{nome}"
        if (caminho / "model.bin").exists():
            return caminho
        # Se o tamanho pedido não foi baixado, usa o que existir (avisando)
        existentes = [p for p in pasta_modelos.glob("whisper-*") if (p / "model.bin").exists()]
        if existentes:
            ordem = ["large-v3-turbo", "large-v3", "medium", "small", "base", "tiny"]
            existentes.sort(key=lambda p: ordem.index(p.name.replace("whisper-", ""))
                            if p.name.replace("whisper-", "") in ordem else 99)
            log.warning("Modelo Whisper '%s' não encontrado em %s; usando '%s'.", nome, pasta_modelos, existentes[0].name)
            return existentes[0]
        raise FileNotFoundError(
            f"Nenhum modelo Whisper encontrado em {pasta_modelos}. "
            "Rode instalar.bat (ou: python instalacao/baixar_modelos.py)."
        )

    # ------------------------------------------------------------------
    def escolher_idioma(self, global_codigo: str, global_prob: float, probs: dict[str, float],
                        candidatos: set[str]) -> Deteccao:
        """
        Escolhe o idioma SOMENTE entre os da sessão (português + idiomas do visitante):
        o que tiver maior probabilidade entre eles vence. Assim, com português e italiano
        selecionados, toda fala é tratada como um dos dois.

        Se `permitir_fora_da_sessao` estiver ligado no config.json, um idioma de fora só
        é aceito quando for bem mais provável que o melhor da sessão.
        """
        melhor_sessao = max(candidatos, key=lambda c: probs.get(c, 0.0))
        prob_sessao = probs.get(melhor_sessao, 0.0)
        if global_codigo in candidatos:
            return Deteccao(global_codigo, global_prob, global_codigo, global_prob, False)
        if not self.permitir_fora_da_sessao or prob_sessao >= 0.25 or global_prob < 0.5:
            return Deteccao(melhor_sessao, prob_sessao, global_codigo, global_prob, False)
        return Deteccao(global_codigo, global_prob, global_codigo, global_prob, True)

    def detectar_idioma(self, audio: np.ndarray, candidatos: set[str]) -> Deteccao:
        """Só detecção (usada no aquecimento e em diagnósticos)."""
        _, _, todas = self.modelo.detect_language(audio=audio[: 30 * TAXA])
        probs = {c: float(p) for c, p in todas}
        return self.escolher_idioma(todas[0][0], float(todas[0][1]), probs, candidatos)

    def _opcoes(self, parcial: bool) -> dict:
        return dict(
            task="transcribe",
            beam_size=1 if parcial else self.beam_size,
            best_of=1,
            temperature=0.0,                 # sem "fallback" de temperatura: mais rápido e previsível
            condition_on_previous_text=False,
            vad_filter=False,                # o segmentador já cortou a fala
            without_timestamps=True,
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )

    def _coletar(self, segmentos) -> str:
        partes = []
        for s in segmentos:
            t = s.text.strip()
            if not t:
                continue
            baixo = t.lower()
            if any(a in baixo for a in _ALUCINACOES):
                log.info("Descartando provável alucinação: %r", t)
                continue
            if s.no_speech_prob > 0.85 and s.avg_logprob < -0.9:
                continue
            partes.append(t)
        return " ".join(partes).strip()

    def reconhecer(
        self,
        audio: np.ndarray,
        candidatos: set[str],
        resolver_idioma: Callable[[str], tab.Idioma | None],
        parcial: bool = False,
        deteccao_previa: Deteccao | None = None,
    ) -> tuple[Deteccao, tab.Idioma, Transcricao]:
        """
        Detecta o idioma (ou usa `deteccao_previa`) e transcreve.
        `resolver_idioma` converte o código do Whisper no Idioma da tabela (resolve "zh").
        """
        inicio = time.perf_counter()
        opcoes = self._opcoes(parcial)

        def idioma_de(codigo: str) -> tab.Idioma:
            i = resolver_idioma(codigo)
            if i is None:
                nome = tab.nome_para_aviso(codigo)
                i = tab.Idioma(codigo, codigo, nome.split(" · ")[0].title(), nome, "", None, None, False, None)
            return i

        segmentos = None
        if self._uma_passada:
            try:
                deteccao, idioma, segmentos = self._reconhecer_uma_passada(audio, candidatos, idioma_de, parcial, deteccao_previa)
            except Exception as e:  # mudança interna do faster-whisper: usa o caminho padrão
                log.warning("Passada única indisponível (%s); usando o caminho padrão do faster-whisper.", e)
                self._uma_passada = False
                segmentos = None

        if segmentos is None:
            if deteccao_previa is not None:
                deteccao = deteccao_previa
                idioma = idioma_de(deteccao.whisper)
                segmentos, _ = self.modelo.transcribe(audio, language=idioma.whisper, initial_prompt=idioma.prompt, **opcoes)
            else:
                segmentos, info = self.modelo.transcribe(audio, language=None, **opcoes)
                probs = {c: float(p) for c, p in (info.all_language_probs or [])}
                deteccao = self.escolher_idioma(info.language, float(info.language_probability), probs, candidatos)
                idioma = idioma_de(deteccao.whisper)
                if deteccao.whisper != info.language or idioma.prompt:
                    # A regra da sessão escolheu outro idioma (ou o idioma pede um prompt): repete fixando-o
                    segmentos, _ = self.modelo.transcribe(audio, language=idioma.whisper, initial_prompt=idioma.prompt, **opcoes)

        texto = self._coletar(segmentos)
        return deteccao, idioma, Transcricao(texto, audio.shape[0] / TAXA, time.perf_counter() - inicio)

    def _reconhecer_uma_passada(self, audio, candidatos, idioma_de, parcial, deteccao_previa):
        """
        Codifica o áudio UMA vez e usa a mesma codificação para detectar o idioma e
        para transcrever. Usa funções internas do faster-whisper (versão fixada no
        requirements.txt); se a biblioteca mudar, `reconhecer` volta ao caminho padrão.
        """
        from faster_whisper.audio import pad_or_trim
        from faster_whisper.tokenizer import Tokenizer
        from faster_whisper.transcribe import TranscriptionOptions, get_suppressed_tokens

        m = self.modelo
        features = m.feature_extractor(audio)
        janela = pad_or_trim(features[..., : m.feature_extractor.nb_max_frames])
        codificado = m.encode(janela)

        if deteccao_previa is None:
            resultados = m.model.detect_language(codificado)[0]  # [(token, prob), ...] em ordem decrescente
            probs = {tok[2:-2]: float(p) for tok, p in resultados}
            deteccao = self.escolher_idioma(resultados[0][0][2:-2], float(resultados[0][1]), probs, candidatos)
        else:
            deteccao = deteccao_previa
        idioma = idioma_de(deteccao.whisper)

        tokenizer = Tokenizer(m.hf_tokenizer, m.model.is_multilingual, task="transcribe", language=idioma.whisper)
        opcoes = TranscriptionOptions(
            beam_size=1 if parcial else self.beam_size, best_of=1, patience=1.0, length_penalty=1.0,
            repetition_penalty=1.0, no_repeat_ngram_size=0, log_prob_threshold=-1.0, no_speech_threshold=0.6,
            compression_ratio_threshold=2.4, condition_on_previous_text=False, prompt_reset_on_temperature=0.5,
            temperatures=[0.0], initial_prompt=idioma.prompt, prefix=None, suppress_blank=True,
            suppress_tokens=get_suppressed_tokens(tokenizer, [-1]), without_timestamps=True,
            max_initial_timestamp=1.0, word_timestamps=False,
            prepend_punctuations="\"'“¿([{-", append_punctuations="\"'.。,，!！?？:：”)]}、",
            multilingual=False, max_new_tokens=None, clip_timestamps="0",
            hallucination_silence_threshold=None, hotwords=None,
        )
        segmentos = m.generate_segments(features, tokenizer, opcoes, False, codificado)
        return deteccao, idioma, segmentos

    def transcrever(self, audio: np.ndarray, idioma: tab.Idioma, parcial: bool = False) -> Transcricao:
        """Transcrição com idioma fixo (aquecimento e testes)."""
        inicio = time.perf_counter()
        segmentos, _ = self.modelo.transcribe(audio, language=idioma.whisper, initial_prompt=idioma.prompt,
                                              **self._opcoes(parcial))
        return Transcricao(self._coletar(segmentos), audio.shape[0] / TAXA, time.perf_counter() - inicio)
