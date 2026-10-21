"""
Simula o microfone: envia arquivos de áudio ao servidor pelo WebSocket, em
tempo real, exatamente como o navegador faz (PCM 16 kHz, pacotes de 80 ms).

Serve para testar o sistema inteiro (servidor + tela) sem falar no microfone,
por exemplo em uma VPS. Abra a interface no navegador, inicie a reunião com
italiano e inglês e rode:

    .venv\Scripts\python.exe testes\simular_microfone.py
    .venv\Scripts\python.exe testes\simular_microfone.py --url ws://127.0.0.1:8765/ws --senha 1234 audio\pt.wav
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402

PASTA_AUDIO = RAIZ / "testes" / "audio"


async def enviar(url: str, senha: str, arquivos: list[Path], pausa_s: float, idiomas: list[str]) -> None:
    import websockets
    from faster_whisper import decode_audio

    uri = f"{url}?token={senha}"
    async with websockets.connect(uri, max_size=None) as ws:
        print(f"Conectado a {url}")
        await ws.send('{"tipo":"iniciar","idiomas":' + str(idiomas).replace("'", '"') + "}")

        async def ouvir() -> None:
            import json
            try:
                async for msg in ws:
                    if not isinstance(msg, str):
                        continue
                    f = json.loads(msg)
                    if f.get("tipo") == "parcial":
                        trad = " | ".join(f"{c}: {t}" for c, t in (f.get("traducoes") or {}).items())
                        print(f"\n  (parcial) {f['texto']}" + (f"  =>  {trad}" if trad else ""))
                    elif f.get("tipo") == "fala":
                        print(f"\n  [{f['hora']}] {f['rotulo']}: {f['original']}")
                        for cod, t in f["traducoes"].items():
                            print(f"      -> {cod}: {t}")
                        print(f"      (tempo total {f['tempos']['total_s']} s)")
                    elif f.get("tipo") == "erro":
                        print("\n  ERRO do servidor:", f.get("mensagem"))
            except Exception:
                pass

        tarefa = asyncio.create_task(ouvir())
        for arq in arquivos:
            audio = decode_audio(str(arq), sampling_rate=16000)
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            print(f"Enviando {arq.name} ({len(pcm) / 16000:.1f} s)...", end="", flush=True)
            inicio = time.perf_counter()
            for i in range(0, len(pcm), 1280):
                await ws.send(pcm[i:i + 1280].tobytes())
                # mantém o ritmo de tempo real (80 ms por pacote)
                alvo = inicio + (i + 1280) / 16000
                atraso = alvo - time.perf_counter()
                if atraso > 0:
                    await asyncio.sleep(atraso)
            # silêncio de 1 s para o VAD fechar a frase
            silencio = np.zeros(1280, dtype=np.int16).tobytes()
            for _ in range(int(1.0 / 0.08)):
                await ws.send(silencio)
                await asyncio.sleep(0.08)
            print(" enviado.")
            await asyncio.sleep(pausa_s)
        await asyncio.sleep(6)
        tarefa.cancel()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivos", nargs="*", help="arquivos de áudio (padrão: pt.wav it.wav en.wav)")
    ap.add_argument("--url", default="ws://127.0.0.1:8765/ws")
    ap.add_argument("--senha", default="")
    ap.add_argument("--pausa", type=float, default=2.0, help="segundos entre os arquivos")
    ap.add_argument("--idiomas", default="it,en", help="idiomas do visitante, separados por vírgula")
    args = ap.parse_args()
    arquivos = [Path(a) if Path(a).exists() else PASTA_AUDIO / a for a in args.arquivos] or \
               [PASTA_AUDIO / n for n in ("pt.wav", "it.wav", "en.wav")]
    try:
        asyncio.run(enviar(args.url, args.senha, arquivos, args.pausa, args.idiomas.split(",")))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
