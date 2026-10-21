"""
Leitura e gravação do arquivo config.json.

O arquivo fica na raiz do projeto. Se alguma chave faltar, o valor padrão
abaixo é usado, para que o sistema funcione mesmo com um config.json antigo.
"""

import copy
import json
import os
from pathlib import Path

# Raiz do projeto (pasta que contém config.json, servidor/, web/ etc.)
RAIZ = Path(__file__).resolve().parent.parent

PADRAO = {
    "servidor": {
        "host": "127.0.0.1",
        "porta": 8765,
        "senha_acesso": "",
        "abrir_navegador": True,
        "https": {
            "ativo": False,
            "certificado": "certificado/cert.pem",
            "chave": "certificado/chave.pem",
        },
    },
    "transcricao": {
        "modelo": "auto",          # auto (large-v3-turbo com GPU, small sem GPU) | tiny | base | small | medium | large-v3 | large-v3-turbo
        "dispositivo": "auto",     # auto | cpu | cuda
        "tipo_computo": "auto",    # auto | int8 | int8_float16 | float16 | float32
        "threads_cpu": 0,          # 0 = detectar (núcleos físicos)
        "beam_size": "auto",       # auto (5 com GPU, 1 sem GPU) ou um número
        "parciais": "auto",        # auto | true | false  (texto parcial enquanto a pessoa fala)
        "intervalo_parcial_s": 1.5,
        "traduzir_parciais": "auto",       # auto (sim com GPU) | true | false: tradução já no texto parcial
        "permitir_fora_da_sessao": False,  # False = só os idiomas escolhidos na sessão
    },
    "audio": {
        "ganho_maximo": 4,                  # amplificação automática do microfone (1 = desligada, até 10)
        "supressao_ruido": True,            # supressão de ruído do navegador
        "ganho_automatico_navegador": True, # controle automático de ganho do navegador
    },
    "traducao": {
        "motor": "nllb",           # nllb | argos
        "modelo": "auto",          # auto (1.3B com GPU, 600M sem GPU) | 600M | 1.3B
        "dispositivo": "auto",
        "beam_size": 2,
        "threads_cpu": 0,
    },
    "vad": {
        "limiar_inicio": 0.4,
        "limiar_fim": 0.3,
        "silencio_fim_ms": 700,    # pausa que encerra a frase (maior = frases mais inteiras, resposta um pouco mais lenta)
        "fala_minima_ms": 300,
        "pre_fala_ms": 300,
        "duracao_maxima_s": 20,
        "corte_suave_apos_s": 10,  # fala longa: fecha um bloco na primeira pausa curta após este tempo
    },
    "sessao": {
        "idiomas_visitante": ["en"],
    },
    "modelos": {
        "pasta": "modelos",
    },
}


def _mesclar(base: dict, novo: dict) -> dict:
    """Mescla recursivamente `novo` por cima de `base` (sem alterar os originais)."""
    resultado = copy.deepcopy(base)
    for chave, valor in (novo or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = _mesclar(resultado[chave], valor)
        else:
            resultado[chave] = valor
    return resultado


def caminho_config() -> Path:
    """Permite apontar outro arquivo com a variável de ambiente GMP_CONFIG."""
    return Path(os.environ.get("GMP_CONFIG", RAIZ / "config.json"))


def carregar() -> dict:
    """Lê o config.json (ou devolve os padrões se ele não existir)."""
    arquivo = caminho_config()
    dados = {}
    if arquivo.exists():
        with open(arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
    cfg = _mesclar(PADRAO, dados)
    # Variáveis de ambiente úteis em VPS/contêiner (não precisam editar o arquivo)
    if os.environ.get("GMP_HOST"):
        cfg["servidor"]["host"] = os.environ["GMP_HOST"]
    if os.environ.get("GMP_PORTA"):
        cfg["servidor"]["porta"] = int(os.environ["GMP_PORTA"])
    if os.environ.get("GMP_SENHA") is not None:
        cfg["servidor"]["senha_acesso"] = os.environ["GMP_SENHA"]
    if os.environ.get("GMP_WHISPER_MODELO"):
        cfg["transcricao"]["modelo"] = os.environ["GMP_WHISPER_MODELO"]
    if os.environ.get("GMP_NLLB_MODELO"):
        cfg["traducao"]["modelo"] = os.environ["GMP_NLLB_MODELO"]
    if os.environ.get("GMP_DISPOSITIVO"):
        cfg["transcricao"]["dispositivo"] = os.environ["GMP_DISPOSITIVO"]
        cfg["traducao"]["dispositivo"] = os.environ["GMP_DISPOSITIVO"]
    return cfg


def salvar(cfg: dict) -> None:
    """Grava o config.json inteiro (formatado, com acentos preservados)."""
    arquivo = caminho_config()
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")


def salvar_idiomas_visitante(idiomas: list) -> None:
    """Guarda a escolha de idiomas do visitante para a próxima reunião."""
    cfg = carregar()
    cfg["sessao"]["idiomas_visitante"] = list(idiomas)
    salvar(cfg)


def pasta_modelos(cfg: dict | None = None) -> Path:
    cfg = cfg or carregar()
    p = Path(cfg["modelos"]["pasta"])
    return p if p.is_absolute() else RAIZ / p
