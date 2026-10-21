"""
Baixa os modelos uma única vez e guarda em modelos/ (dentro do projeto),
com verificação de integridade (tamanho + SHA-256 dos arquivos grandes).

Uso:
    python instalacao/baixar_modelos.py                  # whisper (auto) + NLLB
    python instalacao/baixar_modelos.py --whisper small medium large-v3-turbo
    python instalacao/baixar_modelos.py --nllb 600M 1.3B
    python instalacao/baixar_modelos.py --argos pt en it # pacotes do Argos (opcional)
    python instalacao/baixar_modelos.py --so-verificar   # só confere o que já está na pasta

Depois disso, o programa funciona sem internet (iniciar.bat liga o modo offline).
"""

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
os.environ.setdefault("PYTHONUTF8", "1")

# Repositórios públicos (Hugging Face) com os modelos já convertidos para CTranslate2.
REPOS_WHISPER = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
}
# Tamanhos do NLLB-200 (já convertidos para CTranslate2 int8): 600M (leve) e 1.3B (melhor qualidade)
REPOS_NLLB = {
    "600M": ("JustFrederik/nllb-200-distilled-600M-ct2-int8", "nllb-200-distilled-600M-int8"),
    "1.3B": ("JustFrederik/nllb-200-distilled-1.3B-ct2-int8", "nllb-200-distilled-1.3B-int8"),
}

PADROES_ARQUIVOS = ["*.json", "*.txt", "*.bin", "*.model", "*.md"]


def pasta_modelos() -> Path:
    try:
        from servidor import config
        return config.pasta_modelos()
    except Exception:
        return RAIZ / "modelos"


def pasta_whisper(nome: str) -> Path:
    return pasta_modelos() / f"whisper-{nome}"


def pasta_nllb(tamanho: str = "600M") -> Path:
    return pasta_modelos() / REPOS_NLLB[tamanho][1]


def titulo(texto: str) -> None:
    print("\n" + "=" * 70)
    print(texto)
    print("=" * 70, flush=True)


def sha256_arquivo(caminho: Path, tamanho_bloco: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while True:
            bloco = f.read(tamanho_bloco)
            if not bloco:
                break
            h.update(bloco)
    return h.hexdigest()


def tem_gpu() -> bool:
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return shutil.which("nvidia-smi") is not None


def modelo_whisper_automatico() -> str:
    """Com GPU NVIDIA: 'large-v3-turbo' (mais preciso, mesmo tamanho do medium); só CPU: 'small'."""
    return "large-v3-turbo" if tem_gpu() else "small"


def modelo_nllb_automatico() -> str:
    """Com GPU: NLLB 1.3B (tradução bem melhor); só CPU: 600M (mais rápido)."""
    return "1.3B" if tem_gpu() else "600M"


# ----------------------------------------------------------------------------
# Download + verificação
# ----------------------------------------------------------------------------
def _metadados_repo(repo: str) -> dict:
    """Tamanhos e SHA-256 (dos arquivos LFS) direto da Hugging Face."""
    from huggingface_hub import HfApi
    info = HfApi().model_info(repo, files_metadata=True)
    arquivos = {}
    for s in info.siblings or []:
        sha = getattr(getattr(s, "lfs", None), "sha256", None)
        arquivos[s.rfilename] = {"tamanho": s.size, "sha256": sha}
    return {"repo": repo, "commit": info.sha, "arquivos": arquivos}


def _baixar_repo(repo: str, destino: Path, tentativas: int = 3) -> None:
    from huggingface_hub import snapshot_download
    destino.mkdir(parents=True, exist_ok=True)
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            snapshot_download(
                repo_id=repo,
                local_dir=str(destino),
                allow_patterns=PADROES_ARQUIVOS,
                max_workers=4,
            )
            return
        except Exception as e:  # rede instável: tenta de novo (o download é retomável)
            ultimo_erro = e
            print(f"  Falha na tentativa {tentativa}/{tentativas}: {e}")
            time.sleep(3)
    raise RuntimeError(f"Não foi possível baixar {repo}: {ultimo_erro}")


def _verificar_pasta(destino: Path, meta: dict, completo: bool = True) -> list[str]:
    """Devolve a lista de problemas encontrados (vazia = tudo certo)."""
    problemas = []
    for nome, dados in meta["arquivos"].items():
        if nome in (".gitattributes",) or nome.endswith(".md"):
            continue
        caminho = destino / nome
        if not caminho.exists():
            problemas.append(f"arquivo ausente: {nome}")
            continue
        tamanho = caminho.stat().st_size
        if dados.get("tamanho") and tamanho != dados["tamanho"]:
            problemas.append(f"tamanho errado: {nome} ({tamanho} em vez de {dados['tamanho']} bytes)")
            continue
        if completo and dados.get("sha256"):
            print(f"  Conferindo SHA-256 de {nome} ({tamanho / 1e6:.0f} MB)...", flush=True)
            if sha256_arquivo(caminho) != dados["sha256"]:
                problemas.append(f"SHA-256 não confere: {nome}")
    return problemas


def _gravar_manifesto(destino: Path, meta: dict) -> None:
    meta = dict(meta)
    meta["verificado_em"] = datetime.now().isoformat(timespec="seconds")
    with open(destino / "manifesto.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def baixar_e_verificar(repo: str, destino: Path, rotulo: str, forcar: bool = False) -> None:
    titulo(f"{rotulo}  ->  {destino}")
    manifesto = destino / "manifesto.json"
    if manifesto.exists() and not forcar:
        with open(manifesto, "r", encoding="utf-8") as f:
            meta = json.load(f)
        problemas = _verificar_pasta(destino, meta, completo=False)
        if not problemas:
            print("  Já instalado e íntegro (tamanhos conferidos). Pulando download.")
            return
        print("  Instalação anterior incompleta:", "; ".join(problemas))

    print(f"  Baixando de https://huggingface.co/{repo} (uma única vez)...", flush=True)
    meta = _metadados_repo(repo)
    total = sum((d["tamanho"] or 0) for d in meta["arquivos"].values())
    print(f"  Tamanho total: {total / 1e6:.0f} MB", flush=True)
    _baixar_repo(repo, destino)

    print("  Verificando integridade...", flush=True)
    problemas = _verificar_pasta(destino, meta, completo=True)
    if problemas:
        for p in problemas:
            print("  ERRO:", p)
        raise RuntimeError(f"Verificação falhou para {rotulo}. Rode novamente o instalador.")
    _gravar_manifesto(destino, meta)
    print("  OK: modelo baixado e verificado.")


# ----------------------------------------------------------------------------
# Argos Translate (opcional)
# ----------------------------------------------------------------------------
def baixar_argos(codigos: list[str]) -> None:
    titulo("Argos Translate (motor alternativo) - pacotes de idioma")
    try:
        os.environ["ARGOS_PACKAGES_DIR"] = str(pasta_modelos() / "argos" / "instalados")
        (pasta_modelos() / "argos" / "instalados").mkdir(parents=True, exist_ok=True)
        import argostranslate.package as pacote
    except ImportError:
        print("  O pacote 'argostranslate' não está instalado. Rode: instalar.bat argos")
        return

    from servidor import idiomas as tab
    desejados = set()
    for c in codigos:
        i = tab.obter(c)
        if not i or not i.argos:
            print(f"  Aviso: '{c}' não tem pacote no Argos; use o NLLB para esse idioma.")
            continue
        desejados.add(i.argos)
    desejados.add("pt")
    desejados.add("en")  # o Argos traduz passando pelo inglês

    print("  Atualizando índice de pacotes...", flush=True)
    pacote.update_package_index()
    disponiveis = pacote.get_available_packages()
    pares = set()
    for a in desejados:
        for b in desejados:
            if a != b and (a == "en" or b == "en"):
                pares.add((a, b))
    for de, para in sorted(pares):
        p = next((x for x in disponiveis if x.from_code == de and x.to_code == para), None)
        if not p:
            print(f"  Sem pacote {de}->{para} no índice do Argos.")
            continue
        print(f"  Baixando/instalando {de}->{para}...", flush=True)
        caminho = p.download()
        pacote.install_from_path(caminho)
    print("  OK: pacotes do Argos instalados em modelos/argos/instalados")


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Baixa e verifica os modelos do GMP Tradutor.")
    ap.add_argument("--whisper", nargs="*", default=None,
                    help="tamanhos do Whisper (tiny base small medium large-v3 large-v3-turbo). Padrão: auto")
    ap.add_argument("--nllb", nargs="*", default=None,
                    help="tamanhos do NLLB (600M 1.3B). Padrão: auto (1.3B com GPU, 600M sem GPU)")
    ap.add_argument("--sem-nllb", action="store_true", help="não baixar o NLLB")
    ap.add_argument("--argos", nargs="*", default=None, help="códigos de idioma para o Argos (ex.: pt en it)")
    ap.add_argument("--forcar", action="store_true", help="baixa de novo mesmo se já estiver instalado")
    ap.add_argument("--so-verificar", action="store_true", help="só verifica (SHA-256) o que já está na pasta")
    args = ap.parse_args()

    pasta_modelos().mkdir(parents=True, exist_ok=True)

    if args.so_verificar:
        ok = True
        for sub in sorted(pasta_modelos().iterdir()):
            m = sub / "manifesto.json"
            if m.exists():
                with open(m, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                problemas = _verificar_pasta(sub, meta, completo=True)
                print(f"{sub.name}: {'OK' if not problemas else 'PROBLEMAS: ' + '; '.join(problemas)}")
                ok = ok and not problemas
        return 0 if ok else 1

    try:
        from servidor import config
        cfg = config.carregar()
        cfg_whisper = str(cfg["transcricao"]["modelo"]).lower()
        cfg_nllb = str(cfg["traducao"].get("modelo", "auto"))
    except Exception:
        cfg_whisper, cfg_nllb = "auto", "auto"

    tamanhos = args.whisper
    if tamanhos is None or tamanhos == []:
        tamanhos = [modelo_whisper_automatico() if cfg_whisper == "auto" else cfg_whisper]
    for t in tamanhos:
        if t not in REPOS_WHISPER:
            print(f"Tamanho de Whisper desconhecido: {t}. Opções: {', '.join(REPOS_WHISPER)}")
            return 2
        baixar_e_verificar(REPOS_WHISPER[t], pasta_whisper(t), f"Whisper '{t}' (reconhecimento de fala)", args.forcar)

    if not args.sem_nllb:
        tamanhos_nllb = args.nllb
        if tamanhos_nllb is None or tamanhos_nllb == []:
            tamanhos_nllb = [modelo_nllb_automatico() if cfg_nllb.lower() == "auto" else cfg_nllb]
        for t in tamanhos_nllb:
            chave = next((k for k in REPOS_NLLB if k.lower() == t.lower()), None)
            if not chave:
                print(f"Tamanho de NLLB desconhecido: {t}. Opções: {', '.join(REPOS_NLLB)}")
                return 2
            repo, _ = REPOS_NLLB[chave]
            baixar_e_verificar(repo, pasta_nllb(chave), f"NLLB-200 distilled {chave} int8 (tradução)", args.forcar)

    if args.argos:
        baixar_argos(args.argos)

    titulo("Modelos prontos. A partir de agora o sistema funciona sem internet.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nCancelado.")
        sys.exit(130)
    except Exception as e:
        print(f"\nERRO: {e}")
        sys.exit(1)
