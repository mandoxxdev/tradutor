"""
Abre o Chrome ou o Edge em modo "aplicativo" (sem barra de endereço), maximizado,
com um perfil próprio em dados/perfil_navegador para não interferir no navegador
do dia a dia e para a permissão de microfone ficar guardada.

A tela cheia de verdade é pedida pela própria página quando o operador clica
em "Iniciar reunião" (os navegadores exigem um clique para isso), e Esc sai dela.
"""

import logging
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import config

log = logging.getLogger("gmp.navegador")


def _candidatos() -> list[str]:
    if sys.platform == "win32":
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        return [
            rf"{pf}\Google\Chrome\Application\chrome.exe",
            rf"{pf86}\Google\Chrome\Application\chrome.exe",
            rf"{local}\Google\Chrome\Application\chrome.exe",
            rf"{pf86}\Microsoft\Edge\Application\msedge.exe",
            rf"{pf}\Microsoft\Edge\Application\msedge.exe",
        ]
    if sys.platform == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    return [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium",
                                             "chromium-browser", "microsoft-edge", "microsoft-edge-stable")]


def abrir(url: str, https_proprio: bool = False) -> bool:
    """Abre a interface. Devolve True se conseguiu usar Chrome/Edge em modo aplicativo."""
    # Perfil fora da pasta do projeto (o Chrome grava centenas de arquivos nele; evita sincronizar no OneDrive)
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        perfil = Path(os.environ["LOCALAPPDATA"]) / "GMPTradutor" / "perfil_navegador"
    else:
        perfil = Path.home() / ".cache" / "gmp-tradutor" / "perfil_navegador"
    try:
        perfil.mkdir(parents=True, exist_ok=True)
    except Exception:
        perfil = config.RAIZ / "dados" / "perfil_navegador"
        perfil.mkdir(parents=True, exist_ok=True)
    args_comuns = [
        f"--app={url}",
        "--start-maximized",
        f"--user-data-dir={perfil}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--disable-features=Translate,TranslateUI",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream",   # aceita a permissão do microfone sem perguntar
    ]
    if https_proprio:
        args_comuns.append("--ignore-certificate-errors")  # certificado autoassinado gerado pelo projeto
    for exe in _candidatos():
        if exe and Path(exe).exists():
            try:
                flags = 0
                if sys.platform == "win32":
                    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                subprocess.Popen([exe] + args_comuns, creationflags=flags,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log.info("Navegador aberto: %s", exe)
                return True
            except Exception as e:
                log.warning("Falha ao abrir %s: %s", exe, e)
    log.warning("Chrome/Edge não encontrados; abrindo no navegador padrão.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return False
