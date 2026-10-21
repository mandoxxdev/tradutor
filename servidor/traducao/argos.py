"""
Motor de tradução alternativo: Argos Translate (OpenNMT/CTranslate2).

Mais leve em disco por par de idiomas, mas cobre menos idiomas e traduz
passando pelo inglês. Instalação opcional: instalar.bat argos
Os pacotes ficam em modelos/argos/instalados (variável ARGOS_PACKAGES_DIR).
"""

import logging
import os
from pathlib import Path

from .. import idiomas as tab
from .base import ErroTraducao, MotorTraducao

log = logging.getLogger("gmp.argos")


class MotorArgos(MotorTraducao):
    nome = "argos"

    def __init__(self, cfg: dict, pasta_modelos: Path):
        pasta = pasta_modelos / "argos" / "instalados"
        pasta.mkdir(parents=True, exist_ok=True)
        os.environ["ARGOS_PACKAGES_DIR"] = str(pasta)
        try:
            import argostranslate.translate as tr
        except ImportError as e:
            raise ErroTraducao(
                "O Argos Translate não está instalado. Rode 'instalar.bat argos' ou troque "
                "\"motor\" para \"nllb\" no config.json."
            ) from e
        self.tr = tr
        self.instalados = {l.code: l for l in tr.get_installed_languages()}
        if not self.instalados:
            log.warning("Nenhum pacote do Argos instalado em %s. Rode: python instalacao/baixar_modelos.py --argos pt en it", pasta)
        log.info("Argos pronto com idiomas: %s", ", ".join(sorted(self.instalados)) or "(nenhum)")

    def descricao(self) -> str:
        return f"Argos Translate ({len(self.instalados)} idiomas instalados)"

    def suporta(self, origem: tab.Idioma, destino: tab.Idioma) -> bool:
        if not origem.argos or not destino.argos:
            return False
        a, b = self.instalados.get(origem.argos), self.instalados.get(destino.argos)
        return bool(a and b and a.get_translation(b))

    def traduzir(self, texto: str, origem: tab.Idioma, destino: tab.Idioma) -> str:
        if not self.suporta(origem, destino):
            raise ErroTraducao(
                f"O Argos não tem pacote para {origem.nome_pt} → {destino.nome_pt}. "
                f"Instale com: python instalacao/baixar_modelos.py --argos {origem.codigo} {destino.codigo}"
            )
        return self.tr.translate(texto, origem.argos, destino.argos)
