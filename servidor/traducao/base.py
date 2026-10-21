"""
Interface comum dos motores de tradução (NLLB e Argos).

Qualquer motor novo precisa implementar `traduzir_lote` (ou `traduzir`) e
`suporta`. O pipeline só conversa com esta interface.
"""

import re

from .. import idiomas as tab

# Fim de frase: pontuação ocidental seguida de espaço/fim, ou pontuação CJK/árabe.
_RE_FRASES = re.compile(r"(?<=[.!?…])\s+|(?<=[。！？؟])")


def dividir_frases(texto: str) -> list[str]:
    """Divide um texto em frases (os modelos traduzem melhor frase a frase)."""
    partes = [p.strip() for p in _RE_FRASES.split(texto) if p and p.strip()]
    return partes or ([texto.strip()] if texto.strip() else [])


class ErroTraducao(RuntimeError):
    """Erro de tradução com mensagem em português, pronta para a tela."""


class MotorTraducao:
    nome = "base"

    def suporta(self, origem: tab.Idioma, destino: tab.Idioma) -> bool:
        return True

    def traduzir(self, texto: str, origem: tab.Idioma, destino: tab.Idioma) -> str:
        return self.traduzir_lote([texto], origem, destino)[0]

    def traduzir_lote(self, textos: list[str], origem: tab.Idioma, destino: tab.Idioma) -> list[str]:
        return [self.traduzir(t, origem, destino) for t in textos]

    def traduzir_para_varios(self, texto: str, origem: tab.Idioma, destinos: list[tab.Idioma]) -> dict[str, str]:
        """Traduz um texto para vários idiomas; devolve {codigo_destino: texto}."""
        return {d.codigo: self.traduzir(texto, origem, d) for d in destinos}

    def descricao(self) -> str:
        return self.nome
