"""
Ponto de entrada:  python -m servidor [--host H] [--porta P] [--sem-navegador]

Sobe o servidor web, carrega os modelos em segundo plano e (por padrão)
abre o Chrome/Edge em modo aplicativo apontando para a interface.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Modo offline: nada de consultar a Hugging Face em tempo de execução
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from servidor import VERSAO, config  # noqa: E402


def configurar_log() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("faster_whisper").setLevel(logging.WARNING)


def verificar_modelos(cfg: dict) -> bool:
    pasta = config.pasta_modelos(cfg)
    tem_whisper = any((p / "model.bin").exists() for p in pasta.glob("whisper-*"))
    motor = cfg["traducao"]["motor"]
    tem_traducao = any((p / "model.bin").exists() for p in pasta.glob("nllb-*")) if motor == "nllb" else True
    if not tem_whisper or not tem_traducao:
        print("\nERRO: os modelos ainda não foram baixados.")
        print(f"      Pasta esperada: {pasta}")
        print("      Rode instalar.bat (Windows) ou ./instalar.sh (Linux) e aguarde o download.\n")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="GMP Tradutor - servidor")
    ap.add_argument("--host", default=None, help="endereço para escutar (padrão: config.json)")
    ap.add_argument("--porta", type=int, default=None, help="porta (padrão: config.json)")
    ap.add_argument("--sem-navegador", action="store_true", help="não abrir o navegador automaticamente")
    ap.add_argument("--config", default=None, help="caminho de outro config.json")
    args = ap.parse_args()

    if args.config:
        os.environ["GMP_CONFIG"] = args.config
    configurar_log()
    cfg = config.carregar()
    if args.host:
        cfg["servidor"]["host"] = args.host
    if args.porta:
        cfg["servidor"]["porta"] = args.porta
    if not verificar_modelos(cfg):
        return 1

    import uvicorn
    from servidor.app import criar_app

    s = cfg["servidor"]
    abrir = bool(s.get("abrir_navegador", True)) and not args.sem_navegador
    app = criar_app(cfg, abrir_navegador=abrir)

    ssl = {}
    if s["https"]["ativo"]:
        cert = config.RAIZ / s["https"]["certificado"]
        chave = config.RAIZ / s["https"]["chave"]
        if not cert.exists() or not chave.exists():
            print("\nERRO: HTTPS ativado no config.json, mas o certificado não existe.")
            print("      Gere com:  python instalacao/gerar_certificado.py\n")
            return 1
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(chave)}

    esquema = "https" if ssl else "http"
    print("\n" + "=" * 64)
    print(f"  GMP Tradutor v{VERSAO}")
    print(f"  Interface: {esquema}://{'127.0.0.1' if s['host'] in ('0.0.0.0', '::') else s['host']}:{s['porta']}/")
    if s["host"] in ("0.0.0.0", "::"):
        print("  (escutando em todas as interfaces de rede)")
    print("  Para encerrar: feche esta janela ou pressione Ctrl+C")
    print("=" * 64 + "\n", flush=True)

    uvicorn.run(app, host=s["host"], port=int(s["porta"]), log_level="info",
                ws_max_size=4 * 1024 * 1024, ws_ping_interval=20, ws_ping_timeout=20, **ssl)
    return 0


if __name__ == "__main__":
    sys.exit(main())
