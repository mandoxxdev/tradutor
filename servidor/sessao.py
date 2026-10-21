"""
Estado da reunião: idiomas do visitante, histórico de falas e pausa.

O histórico é gravado linha a linha em dados/historico_atual.jsonl, para
que uma queda do programa no meio da reunião não perca a ata. "Nova reunião"
arquiva esse arquivo com data e hora e começa outro.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

from . import config, idiomas as tab

log = logging.getLogger("gmp.sessao")


class Sessao:
    def __init__(self, cfg: dict):
        self.pasta_dados = config.RAIZ / "dados"
        self.pasta_dados.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta_dados / "historico_atual.jsonl"
        self.idiomas_visitante: list[str] = tab.validar_lista(cfg["sessao"].get("idiomas_visitante", []))
        self.historico: list[dict] = []
        self.pausado = False
        self.iniciada_em = datetime.now()
        self._trava = threading.Lock()
        self._carregar()

    def _carregar(self) -> None:
        if not self.arquivo.exists():
            return
        try:
            with open(self.arquivo, "r", encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if linha:
                        self.historico.append(json.loads(linha))
            if self.historico:
                primeiro = self.historico[0]
                self.iniciada_em = datetime.strptime(f"{primeiro['data']} {primeiro['hora']}", "%Y-%m-%d %H:%M:%S")
                log.info("Histórico anterior recuperado: %d falas.", len(self.historico))
        except Exception as e:
            log.warning("Não foi possível ler o histórico anterior (%s). Começando vazio.", e)
            self.historico = []

    def definir_idiomas(self, codigos: list[str]) -> list[str]:
        self.idiomas_visitante = tab.validar_lista(codigos)
        try:
            config.salvar_idiomas_visitante(self.idiomas_visitante)
        except Exception as e:
            log.warning("Não foi possível salvar os idiomas no config.json: %s", e)
        return self.idiomas_visitante

    def adicionar(self, fala: dict) -> None:
        with self._trava:
            self.historico.append(fala)
            try:
                with open(self.arquivo, "a", encoding="utf-8") as f:
                    f.write(json.dumps(fala, ensure_ascii=False) + "\n")
            except Exception as e:
                log.warning("Falha ao gravar o histórico em disco: %s", e)

    def nova_reuniao(self) -> None:
        with self._trava:
            if self.arquivo.exists() and self.historico:
                carimbo = self.iniciada_em.strftime("%Y-%m-%d_%H-%M")
                destino = self.pasta_dados / f"historico_{carimbo}.jsonl"
                try:
                    self.arquivo.replace(destino)
                except Exception:
                    pass
            elif self.arquivo.exists():
                self.arquivo.unlink(missing_ok=True)
            self.historico = []
            self.iniciada_em = datetime.now()

    def para_json(self) -> dict:
        return {
            "idiomas_visitante": self.idiomas_visitante,
            "pausado": self.pausado,
            "total_falas": len(self.historico),
            "iniciada_em": self.iniciada_em.strftime("%Y-%m-%d %H:%M"),
        }
