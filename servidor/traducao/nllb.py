"""
Motor de tradução NLLB-200 (distilled 600M) em CTranslate2 com quantização int8.

O tokenizador é o SentencePiece do próprio NLLB; o formato de entrada é
    [código_do_idioma_origem] peças... </s>
e a saída começa com o código do idioma de destino (passado como prefixo).
"""

import logging
import time
from pathlib import Path

from .. import gpu, idiomas as tab
from .base import ErroTraducao, MotorTraducao, dividir_frases

log = logging.getLogger("gmp.nllb")

PASTAS = {
    "600m": "nllb-200-distilled-600M-int8",   # leve: padrão em CPU
    "1.3b": "nllb-200-distilled-1.3B-int8",   # melhor qualidade: padrão com GPU
}


class MotorNLLB(MotorTraducao):
    nome = "nllb"

    def __init__(self, cfg: dict, pasta_modelos: Path):
        import ctranslate2
        import sentencepiece as spm

        gpu.preparar_bibliotecas_cuda()
        dispositivo, tipo = gpu.escolher_dispositivo(cfg.get("dispositivo", "auto"))
        caminho = self._resolver_caminho(pasta_modelos, str(cfg.get("modelo", "auto")), dispositivo)
        self.tamanho = "1.3B" if "1.3B" in caminho.name else "600M"
        threads = int(cfg.get("threads_cpu") or 0) or min(8, gpu.nucleos_fisicos())
        self.beam_size = max(1, int(cfg.get("beam_size", 2)))
        self.dispositivo = dispositivo
        log.info("Carregando NLLB-200 em %s (%s)...", dispositivo, tipo)
        inicio = time.perf_counter()
        try:
            self.tradutor = ctranslate2.Translator(str(caminho), device=dispositivo, compute_type=tipo,
                                                   inter_threads=1, intra_threads=threads)
        except Exception as e:
            if dispositivo == "cuda":
                log.warning("Falha ao usar a GPU para o NLLB (%s). Tentando em CPU...", e)
                self.dispositivo = "cpu"
                self.tradutor = ctranslate2.Translator(str(caminho), device="cpu", compute_type="int8",
                                                       inter_threads=1, intra_threads=threads)
            else:
                raise
        # Carrega pelos bytes (e não pelo caminho): no Windows, o SentencePiece não abre
        # caminhos com acento, como "TRADUÇÃO".
        with open(caminho / "sentencepiece.bpe.model", "rb") as f:
            self.sp = spm.SentencePieceProcessor(model_proto=f.read())
        log.info("NLLB pronto em %.1f s.", time.perf_counter() - inicio)

    @staticmethod
    def _resolver_caminho(pasta_modelos: Path, nome: str, dispositivo: str) -> Path:
        """auto = 1.3B com GPU (se baixado), 600M sem GPU; aceita '600M' ou '1.3B' explícitos."""
        nome = nome.lower()
        if nome == "auto":
            ordem = ["1.3b", "600m"] if dispositivo == "cuda" else ["600m", "1.3b"]
        elif nome in PASTAS:
            ordem = [nome] + [k for k in PASTAS if k != nome]
        else:
            raise FileNotFoundError(f"Tamanho de NLLB desconhecido no config.json: '{nome}' (use auto, 600M ou 1.3B).")
        for chave in ordem:
            caminho = pasta_modelos / PASTAS[chave]
            if (caminho / "model.bin").exists():
                if chave != ordem[0]:
                    log.warning("NLLB '%s' não encontrado; usando '%s'.", PASTAS[ordem[0]], caminho.name)
                return caminho
        raise FileNotFoundError(
            f"Nenhum modelo NLLB encontrado em {pasta_modelos}. Rode instalar.bat (ou python instalacao/baixar_modelos.py)."
        )

    def descricao(self) -> str:
        return f"NLLB-200 distilled {self.tamanho} int8 ({self.dispositivo})"

    def suporta(self, origem: tab.Idioma, destino: tab.Idioma) -> bool:
        return bool(origem.nllb and destino.nllb)

    def _traduzir_pares(self, pares: list[tuple[str, str, str]]) -> list[str]:
        """
        Traduz uma lista de (frase, nllb_origem, nllb_destino) em um único lote do CTranslate2.
        Cada item pode ter origem/destino diferentes.
        """
        if not pares:
            return []
        entradas = [[o] + self.sp.encode(f, out_type=str) + ["</s>"] for f, o, _ in pares]
        prefixos = [[d] for _, _, d in pares]
        try:
            resultados = self.tradutor.translate_batch(
                entradas,
                target_prefix=prefixos,
                beam_size=self.beam_size,
                max_decoding_length=512,
                repetition_penalty=1.1,
                max_batch_size=16,
            )
        except Exception as e:
            raise ErroTraducao(f"Falha na tradução: {e}") from e
        saidas = []
        for (_, _, d), r in zip(pares, resultados):
            pecas = [p for p in r.hypotheses[0] if p not in (d, "</s>", "<s>", "<pad>")]
            saidas.append(self.sp.decode(pecas).strip())
        return saidas

    def traduzir_lote(self, textos: list[str], origem: tab.Idioma, destino: tab.Idioma) -> list[str]:
        if origem.nllb == destino.nllb:
            return list(textos)
        # Divide cada texto em frases, traduz tudo em um único lote e remonta.
        pares: list[tuple[str, str, str]] = []
        mapa: list[int] = []
        for i, t in enumerate(textos):
            for f in dividir_frases(t):
                pares.append((f, origem.nllb, destino.nllb))
                mapa.append(i)
        saidas = ["" for _ in textos]
        for idx, trecho in zip(mapa, self._traduzir_pares(pares)):
            saidas[idx] = (saidas[idx] + " " + trecho).strip() if saidas[idx] else trecho
        return saidas

    def traduzir_para_varios(self, texto: str, origem: tab.Idioma, destinos: list[tab.Idioma]) -> dict[str, str]:
        """Um texto para vários idiomas em um único lote (todas as frases x todos os destinos)."""
        frases = dividir_frases(texto)
        pares: list[tuple[str, str, str]] = []
        mapa: list[str] = []
        for d in destinos:
            for f in frases:
                pares.append((f, origem.nllb, d.nllb))
                mapa.append(d.codigo)
        saidas = {d.codigo: "" for d in destinos}
        for cod, trecho in zip(mapa, self._traduzir_pares(pares)):
            saidas[cod] = (saidas[cod] + " " + trecho).strip() if saidas[cod] else trecho
        return saidas
