"""
Teste do pipeline completo com três áudios curtos: português, italiano e inglês.

Para cada arquivo em testes/audio/ o teste:
  1. passa o áudio pelo segmentador (VAD Silero), como se viesse do microfone;
  2. detecta o idioma, transcreve e traduz (mesmo código usado na reunião);
  3. confere que o idioma detectado é o esperado, que a tradução foi para a
     coluna certa (português -> visitante, estrangeiro -> português) e que o
     texto traduzido está mesmo no idioma de destino (heurística de palavras
     frequentes, sem nenhum serviço externo);
  4. mede o tempo de transcrição + tradução por frase.

Uso:
    .venv\Scripts\python.exe testes\teste_pipeline.py            # configuração do config.json
    .venv\Scripts\python.exe testes\teste_pipeline.py --cpu       # força CPU
    .venv\Scripts\python.exe testes\teste_pipeline.py --modelo small
"""

import argparse
import itertools
import json
import os
import re
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("PYTHONUTF8", "1")

import numpy as np  # noqa: E402

from servidor import config, idiomas as tab  # noqa: E402
from servidor.pipeline import Pipeline  # noqa: E402
from servidor.segmentador import Segmentador  # noqa: E402
from servidor.vad import VadSilero  # noqa: E402

PASTA_AUDIO = RAIZ / "testes" / "audio"
IDIOMAS_SESSAO = ["it", "en"]  # visitantes italiano e inglês; a casa fala português

# arquivo -> (idioma esperado, coluna esperada do ORIGINAL, idiomas de destino esperados)
CASOS = {
    "pt.wav": ("pt", "portugues", ["it", "en"]),
    "it.wav": ("it", "visitante", ["pt"]),
    "en.wav": ("en", "visitante", ["pt"]),
}

# Palavras muito frequentes em cada idioma (para conferir o idioma da tradução sem internet)
_FREQUENTES = {
    "pt": {"de", "que", "o", "os", "as", "não", "para", "com", "uma", "um", "do", "da", "em", "nós", "nossa",
           "nosso", "é", "dos", "das", "vamos", "hoje", "muito", "entrega", "prazo", "garantia", "máquinas",
           "gostaríamos", "saber", "condições", "equipamentos", "obrigado", "bem-vindos", "todos", "estamos"},
    "it": {"di", "che", "il", "la", "non", "per", "con", "una", "un", "è", "i", "le", "della", "del", "molto",
           "vorremmo", "grazie", "siamo", "alla", "dei", "tempi", "consegna", "oggi", "nostra", "benvenuti",
           "tutti", "presenteremo", "linea", "macchine", "discutere", "programma", "attrezzature", "nuova"},
    "en": {"the", "and", "is", "to", "of", "in", "that", "we", "our", "you", "for", "would", "like", "know",
           "time", "new", "delivery", "good", "afternoon", "everyone", "welcome", "today", "will", "schedule",
           "equipment", "line", "mills", "discuss", "factory", "morning", "everybody", "present"},
}


def idioma_do_texto(texto: str) -> str:
    """Devolve o idioma (pt/it/en) com mais palavras frequentes no texto."""
    palavras = re.findall(r"[\w'-]+", texto.lower())
    pontos = {cod: sum(1 for p in palavras if p in conj) for cod, conj in _FREQUENTES.items()}
    return max(pontos, key=pontos.get) if any(pontos.values()) else "?"


def carregar_audio(caminho: Path) -> np.ndarray:
    from faster_whisper import decode_audio
    return decode_audio(str(caminho), sampling_rate=16000)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cpu", action="store_true", help="força o uso de CPU")
    ap.add_argument("--modelo", default=None, help="tamanho do Whisper (small, medium...)")
    ap.add_argument("--motor", default=None, help="motor de tradução (nllb ou argos)")
    args = ap.parse_args()

    cfg = config.carregar()
    if args.cpu:
        cfg["transcricao"]["dispositivo"] = "cpu"
        cfg["traducao"]["dispositivo"] = "cpu"
    if args.modelo:
        cfg["transcricao"]["modelo"] = args.modelo
    if args.motor:
        cfg["traducao"]["motor"] = args.motor

    print("Carregando modelos...", flush=True)
    t0 = time.perf_counter()
    pipeline = Pipeline(cfg, config.pasta_modelos(cfg))
    pipeline.definir_idiomas(IDIOMAS_SESSAO)
    print(f"Modelos carregados em {time.perf_counter() - t0:.1f} s. "
          f"Whisper '{pipeline.transcritor.nome}' em {pipeline.transcritor.dispositivo} "
          f"({pipeline.transcritor.tipo_computo}); tradução: {pipeline.motor.descricao()}")
    print(f"Idiomas da sessão: PORTUGUÊS + {', '.join(tab.IDIOMAS[c].rotulo for c in IDIOMAS_SESSAO)}")
    print("Aquecendo os modelos (a primeira chamada na GPU é lenta e não entra na média)...", flush=True)
    pipeline.aquecer()
    print()

    vad = VadSilero()
    contador_id = itertools.count(1)  # ids únicos para todas as falas do teste
    v = cfg["vad"]
    falhas = []
    tempos = []
    relatorio = []

    for arquivo, (idioma_esp, coluna_esp, destinos_esp) in CASOS.items():
        caminho = PASTA_AUDIO / arquivo
        if not caminho.exists():
            falhas.append(f"{arquivo}: arquivo de áudio não encontrado em {PASTA_AUDIO}")
            continue
        audio = carregar_audio(caminho)

        # 1) segmentação por VAD, igual ao microfone ao vivo
        finais: list[np.ndarray] = []
        seg = Segmentador(vad, limiar_inicio=v["limiar_inicio"], limiar_fim=v["limiar_fim"],
                          silencio_fim_ms=v["silencio_fim_ms"], fala_minima_ms=v["fala_minima_ms"],
                          pre_fala_ms=v["pre_fala_ms"], duracao_maxima_s=v["duracao_maxima_s"],
                          corte_suave_apos_s=v["corte_suave_apos_s"], parciais=False,
                          ao_finalizar=lambda i, a: finais.append(a))
        seg.reiniciar()
        # alimenta em pedaços de 80 ms, como o navegador faz
        for i in range(0, audio.shape[0], 1280):
            seg.alimentar(audio[i:i + 1280])
        seg.finalizar_pendente()
        if not finais:
            falhas.append(f"{arquivo}: o VAD não encontrou fala no áudio")
            continue

        # 2) pipeline em cada fala detectada (normalmente uma só)
        resultados = []
        for trecho in finais:
            r = pipeline.processar(trecho, id_fala=next(contador_id), parcial=False)
            if r:
                resultados.append(r)
        if not resultados:
            falhas.append(f"{arquivo}: nenhuma transcrição produzida")
            continue

        original = " ".join(r["original"] for r in resultados)
        idioma = resultados[0]["idioma"]
        coluna = resultados[0]["coluna"]
        destinos = list(resultados[0]["traducoes"].keys())
        traducoes = {d: " ".join(r["traducoes"].get(d, "") for r in resultados) for d in destinos}
        total = sum(r["tempos"]["total_s"] for r in resultados)
        tempos.append(total)

        print(f"--- {arquivo} ({audio.shape[0] / 16000:.1f} s de áudio, {len(finais)} fala(s) pelo VAD)")
        print(f"    idioma detectado: {tab.IDIOMAS[idioma].rotulo}  (confiança {resultados[0]['confianca_idioma']})")
        print(f"    original  : {original}")
        for d, t in traducoes.items():
            print(f"    -> {tab.IDIOMAS[d].rotulo}: {t}")
        print(f"    tempos    : idioma + transcrição {sum(r['tempos']['transcricao_s'] for r in resultados):.2f} s"
              f" + tradução {sum(r['tempos']['traducao_s'] for r in resultados):.2f} s = {total:.2f} s")

        # 3) verificações
        if idioma != idioma_esp:
            falhas.append(f"{arquivo}: idioma detectado '{idioma}', esperado '{idioma_esp}'")
        if coluna != coluna_esp:
            falhas.append(f"{arquivo}: original foi para a coluna '{coluna}', esperado '{coluna_esp}'")
        if sorted(destinos) != sorted(destinos_esp):
            falhas.append(f"{arquivo}: traduzido para {destinos}, esperado {destinos_esp}")
        for d, t in traducoes.items():
            if not t.strip():
                falhas.append(f"{arquivo}: tradução para '{d}' veio vazia")
                continue
            lid = idioma_do_texto(t)
            if lid != d:
                falhas.append(f"{arquivo}: a tradução para '{d}' parece estar em '{lid}': {t!r}")
        relatorio.append({"arquivo": arquivo, "idioma": idioma, "original": original,
                          "traducoes": traducoes, "tempos": [r["tempos"] for r in resultados]})

    print("\n" + "=" * 70)
    if tempos:
        media = sum(tempos) / len(tempos)
        print(f"Tempo médio de transcrição + tradução por frase: {media:.2f} s "
              f"(Whisper '{pipeline.transcritor.nome}' em {pipeline.transcritor.dispositivo}, "
              f"tradução em {getattr(pipeline.motor, 'dispositivo', 'cpu')})")
    if falhas:
        print("FALHAS:")
        for f in falhas:
            print("  -", f)
    else:
        print("TODOS OS TESTES PASSARAM: idiomas, colunas e traduções corretos.")

    saida = RAIZ / "testes" / "resultado_ultimo_teste.json"
    with open(saida, "w", encoding="utf-8") as f:
        json.dump({
            "whisper": pipeline.transcritor.nome,
            "dispositivo": pipeline.transcritor.dispositivo,
            "tipo_computo": pipeline.transcritor.tipo_computo,
            "traducao": pipeline.motor.descricao(),
            "tempo_medio_s": round(sum(tempos) / len(tempos), 3) if tempos else None,
            "falhas": falhas,
            "casos": relatorio,
        }, f, ensure_ascii=False, indent=2)
    print(f"Relatório gravado em {saida}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
