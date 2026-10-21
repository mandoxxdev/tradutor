"""Fábrica do motor de tradução: escolhe NLLB ou Argos conforme o config.json."""

from pathlib import Path

from .base import ErroTraducao, MotorTraducao, dividir_frases  # noqa: F401


def criar_motor(cfg_traducao: dict, pasta_modelos: Path) -> MotorTraducao:
    motor = (cfg_traducao.get("motor") or "nllb").lower()
    if motor == "nllb":
        from .nllb import MotorNLLB
        return MotorNLLB(cfg_traducao, pasta_modelos)
    if motor == "argos":
        from .argos import MotorArgos
        return MotorArgos(cfg_traducao, pasta_modelos)
    raise ErroTraducao(f"Motor de tradução desconhecido no config.json: '{motor}' (use 'nllb' ou 'argos').")
