"""
Servidor web (FastAPI + WebSocket) do GMP Tradutor.

Fluxo:
  navegador --(áudio PCM 16 kHz por WebSocket)--> segmentador (VAD) --> trabalhador
  (Whisper + tradução) --> todos os navegadores conectados recebem as falas.

O áudio é captado pelo navegador (getUserMedia), então o servidor pode rodar
na mesma máquina ou em outra (VPS). Nada sai para serviços externos.
"""

import asyncio
import json
import logging
import queue
import threading
import time
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import VERSAO, config, exportar, idiomas as tab, navegador
from .pipeline import Pipeline, Trabalhador
from .segmentador import Segmentador
from .sessao import Sessao
from .vad import VadSilero

log = logging.getLogger("gmp.app")

PASTA_WEB = config.RAIZ / "web"
PASTA_ATAS = config.RAIZ / "atas"


class Estado:
    """Tudo o que o servidor precisa compartilhar entre as rotas e as threads."""

    def __init__(self, cfg: dict, abrir_navegador: bool):
        self.cfg = cfg
        self.abrir_navegador = abrir_navegador
        self.sessao = Sessao(cfg)
        self.pipeline: Pipeline | None = None
        self.trabalhador: Trabalhador | None = None
        self.segmentador: Segmentador | None = None
        self.pronto = False
        self.mensagem = "Iniciando..."
        self.erro: str | None = None
        self.processando: str | None = None
        self.falando = False
        self.aviso: str | None = None
        self.clientes: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.fila_audio: "queue.Queue[np.ndarray | None]" = queue.Queue(maxsize=400)
        self.fonte_audio: WebSocket | None = None
        self.ultimo_audio_em = 0.0
        self.parciais_modo = str(cfg["transcricao"].get("parciais", "auto")).lower()
        self.info_modelos: dict = {}
        self.trava = threading.Lock()

    # ---------------------------------------------------------------- envio
    def enviar_todos(self, mensagem: dict) -> None:
        """Pode ser chamado de qualquer thread."""
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._enviar_todos(mensagem), self.loop)

    async def _enviar_todos(self, mensagem: dict) -> None:
        texto = json.dumps(mensagem, ensure_ascii=False)
        mortos = []
        for ws in list(self.clientes):
            try:
                await ws.send_text(texto)
            except Exception:
                mortos.append(ws)
        for ws in mortos:
            self.clientes.discard(ws)

    def estado_json(self) -> dict:
        return {
            "tipo": "estado",
            "pronto": self.pronto,
            "mensagem": self.mensagem,
            "erro": self.erro,
            "pausado": self.sessao.pausado,
            "falando": self.falando,
            "processando": self.processando,
            "aviso": self.aviso,
            "parciais": bool(self.segmentador and self.segmentador.parciais),
        }

    def enviar_estado(self) -> None:
        self.enviar_todos(self.estado_json())

    # ------------------------------------------------------------- modelos
    def carregar_modelos(self) -> None:
        """Roda em uma thread própria; a interface mostra o progresso."""
        try:
            def progresso(m: str) -> None:
                self.mensagem = m
                log.info(m)
                self.enviar_estado()

            pasta = config.pasta_modelos(self.cfg)
            self.pipeline = Pipeline(self.cfg, pasta, ao_progresso=progresso)
            self.pipeline.definir_idiomas(self.sessao.idiomas_visitante)
            progresso("Aquecendo os modelos...")
            self.pipeline.aquecer()

            self.trabalhador = Trabalhador(self.pipeline, self._ao_resultado, self._ao_estado_processamento, self._ao_erro)
            self.trabalhador.start()

            v = self.cfg["vad"]
            parciais = self.parciais_modo in ("auto", "true", "1", "sim")
            intervalo = float(self.cfg["transcricao"].get("intervalo_parcial_s", 2.0))
            if self.pipeline.transcritor.dispositivo == "cpu":
                intervalo = max(intervalo, 2.5)  # em CPU, parciais mais espaçadas
            self.segmentador = Segmentador(
                VadSilero(),
                limiar_inicio=v["limiar_inicio"], limiar_fim=v["limiar_fim"],
                silencio_fim_ms=v["silencio_fim_ms"], fala_minima_ms=v["fala_minima_ms"],
                pre_fala_ms=v["pre_fala_ms"], duracao_maxima_s=v["duracao_maxima_s"],
                corte_suave_apos_s=v["corte_suave_apos_s"], intervalo_parcial_s=intervalo,
                parciais=parciais,
                ao_iniciar=self._ao_iniciar_fala, ao_parcial=self._ao_parcial,
                ao_finalizar=self._ao_finalizar, ao_cancelar=self._ao_cancelar,
            )
            threading.Thread(target=self._consumir_audio, name="gmp-audio", daemon=True).start()

            self.info_modelos = {
                "whisper": self.pipeline.transcritor.nome,
                "dispositivo": self.pipeline.transcritor.dispositivo,
                "tipo_computo": self.pipeline.transcritor.tipo_computo,
                "traducao": self.pipeline.motor.descricao(),
            }
            self.pronto = True
            self.mensagem = "Pronto"
            log.info("Sistema pronto. Whisper '%s' em %s; tradução: %s",
                     self.info_modelos["whisper"], self.info_modelos["dispositivo"], self.info_modelos["traducao"])
            self.enviar_estado()
        except Exception as e:
            log.exception("Falha ao carregar os modelos")
            self.erro = f"Não foi possível carregar os modelos: {e}"
            self.mensagem = "Erro"
            self.enviar_estado()

    # --------------------------------------------------------------- áudio
    def receber_audio(self, dados: bytes) -> None:
        """Chamado pela rota WebSocket a cada pacote de áudio (int16, 16 kHz, mono)."""
        if not self.pronto or self.sessao.pausado:
            return
        if len(dados) % 2:
            dados = dados[:-1]  # int16 precisa de número par de bytes
        if not dados:
            return
        amostras = np.frombuffer(dados, dtype=np.int16).astype(np.float32) / 32768.0
        try:
            self.fila_audio.put_nowait(amostras)
        except queue.Full:
            log.warning("Fila de áudio cheia: o processamento não está acompanhando; descartando um pacote.")

    def _consumir_audio(self) -> None:
        while True:
            amostras = self.fila_audio.get()
            if amostras is None:
                break
            try:
                self.segmentador.alimentar(amostras)
            except Exception:
                log.exception("Erro no segmentador")

    def pausar(self, pausar: bool) -> None:
        self.sessao.pausado = pausar
        if self.segmentador:
            self.segmentador.reiniciar()
        self.falando = False
        self.enviar_estado()

    # ------------------------------------------------- eventos do segmentador
    def _ao_iniciar_fala(self, id_fala: int) -> None:
        self.falando = True
        self.enviar_estado()

    def _ao_parcial(self, id_fala: int, audio: np.ndarray) -> None:
        if self.trabalhador and not self.trabalhador.ocupado:
            self.trabalhador.enviar(id_fala, audio, parcial=True)

    def _ao_finalizar(self, id_fala: int, audio: np.ndarray) -> None:
        self.falando = bool(self.segmentador and self.segmentador.falando)
        self.enviar_estado()
        if self.trabalhador:
            self.trabalhador.enviar(id_fala, audio, parcial=False)

    def _ao_cancelar(self, id_fala: int) -> None:
        self.falando = False
        if self.trabalhador:
            self.trabalhador.cancelar(id_fala)
        self.enviar_todos({"tipo": "cancelar", "id": id_fala})
        self.enviar_estado()

    # ------------------------------------------------- eventos do trabalhador
    def _ao_resultado(self, resultado: dict) -> None:
        if resultado.get("tipo") == "fala":
            self.sessao.adicionar(resultado)
            self._ajustar_parciais()
            if resultado.get("fora_da_sessao"):
                self.aviso = f"Idioma fora da sessão detectado: {resultado['rotulo']}"
            else:
                self.aviso = None
        self.enviar_todos(resultado)

    def _ao_estado_processamento(self, estado: str | None) -> None:
        self.processando = estado
        self.enviar_estado()

    def _ao_erro(self, mensagem: str) -> None:
        self.enviar_todos({"tipo": "erro", "mensagem": mensagem})

    def _ajustar_parciais(self) -> None:
        """Em modo 'auto', desliga as parciais se a máquina não estiver dando conta."""
        if self.parciais_modo != "auto" or not self.segmentador or not self.segmentador.parciais:
            return
        tempos = list(self.pipeline.ultimos_tempos) if self.pipeline else []
        if len(tempos) >= 3 and sum(tempos[-3:]) / 3 > 2.5:
            self.segmentador.parciais = False
            log.warning("Processamento lento (média %.1f s); texto parcial desativado para priorizar a tradução final.",
                        sum(tempos[-3:]) / 3)
            self.enviar_estado()

    # ------------------------------------------------------------- sessão
    def definir_idiomas(self, codigos: list[str]) -> list[str]:
        idiomas = self.sessao.definir_idiomas(codigos)
        if self.pipeline:
            self.pipeline.definir_idiomas(idiomas)
        return idiomas


# ---------------------------------------------------------------------------
def criar_app(cfg: dict, abrir_navegador: bool = True) -> FastAPI:
    estado = Estado(cfg, abrir_navegador)
    senha = (cfg["servidor"].get("senha_acesso") or "").strip()

    def conferir_senha(token: str | None) -> None:
        if senha and (token or "") != senha:
            raise HTTPException(status_code=401, detail="Senha de acesso incorreta.")

    app = FastAPI(title="GMP Tradutor", version=VERSAO, docs_url=None, redoc_url=None)

    @app.on_event("startup")
    async def _startup() -> None:
        estado.loop = asyncio.get_running_loop()
        threading.Thread(target=estado.carregar_modelos, name="gmp-modelos", daemon=True).start()
        if estado.abrir_navegador:
            def abrir() -> None:
                time.sleep(1.5)
                s = cfg["servidor"]
                host = s["host"] if s["host"] not in ("0.0.0.0", "::") else "127.0.0.1"
                esquema = "https" if s["https"]["ativo"] else "http"
                navegador.abrir(f"{esquema}://{host}:{s['porta']}/", https_proprio=bool(s["https"]["ativo"]))
            threading.Thread(target=abrir, name="gmp-navegador", daemon=True).start()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if estado.trabalhador:
            estado.trabalhador.parar()
        estado.fila_audio.put(None)

    # ------------------------------------------------------------------ rotas
    @app.get("/", response_class=HTMLResponse)
    async def pagina() -> HTMLResponse:
        html = (PASTA_WEB / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @app.get("/logo.png")
    async def logo():
        caminho = PASTA_WEB / "logo.png"
        if not caminho.exists():
            raise HTTPException(status_code=404, detail="Sem logo. Coloque o arquivo em web/logo.png.")
        return FileResponse(str(caminho), media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    @app.get("/info")
    async def info() -> JSONResponse:
        return JSONResponse({
            "versao": VERSAO,
            "pronto": estado.pronto,
            "mensagem": estado.mensagem,
            "erro": estado.erro,
            "exige_senha": bool(senha),
            "modelos": estado.info_modelos,
            "sessao": estado.sessao.para_json(),
            "audio": cfg.get("audio", {}),
            "logo": (PASTA_WEB / "logo.png").exists() or (PASTA_WEB / "logo.svg").exists(),
        })

    @app.get("/historico")
    async def historico(token: str | None = Query(default=None)) -> JSONResponse:
        conferir_senha(token)
        return JSONResponse({"falas": estado.sessao.historico, "sessao": estado.sessao.para_json()})

    @app.get("/exportar")
    async def exportar_ata(formato: str = Query(default="docx"), token: str | None = Query(default=None)):
        conferir_senha(token)
        if not estado.sessao.historico:
            raise HTTPException(status_code=400, detail="Ainda não há falas para exportar.")
        docx_path, txt_path = await asyncio.to_thread(
            exportar.exportar, list(estado.sessao.historico), estado.sessao.idiomas_visitante,
            PASTA_ATAS, estado.sessao.iniciada_em,
        )
        if formato == "json":
            return JSONResponse({"docx": str(docx_path), "txt": str(txt_path), "pasta": str(PASTA_ATAS)})
        if formato == "txt":
            return FileResponse(str(txt_path), filename=txt_path.name, media_type="text/plain; charset=utf-8")
        return FileResponse(str(docx_path), filename=docx_path.name,
                            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # -------------------------------------------------------------- WebSocket
    @app.websocket("/ws")
    async def ws_principal(ws: WebSocket, token: str | None = Query(default=None)) -> None:
        if senha and (token or "") != senha:
            await ws.close(code=4401, reason="senha incorreta")
            return
        await ws.accept()
        estado.clientes.add(ws)
        try:
            await ws.send_text(json.dumps({
                "tipo": "ola",
                "versao": VERSAO,
                "sessao": estado.sessao.para_json(),
                "idiomas_disponiveis": tab.lista_para_interface(),
                "portugues": tab.IDIOMAS[tab.PORTUGUES].para_json(),
                "modelos": estado.info_modelos,
                "historico": estado.sessao.historico[-300:],
                "estado": estado.estado_json(),
            }, ensure_ascii=False))

            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    agora = time.monotonic()
                    # Só um navegador por vez envia o microfone (o primeiro que mandar áudio)
                    if estado.fonte_audio is not None and estado.fonte_audio is not ws \
                            and estado.fonte_audio in estado.clientes and agora - estado.ultimo_audio_em < 3.0:
                        continue
                    if estado.fonte_audio is not ws:
                        estado.fonte_audio = ws
                        log.info("Microfone agora vem do cliente %s", ws.client)
                    estado.ultimo_audio_em = agora
                    estado.receber_audio(msg["bytes"])
                    continue
                texto = msg.get("text")
                if not texto:
                    continue
                try:
                    dados = json.loads(texto)
                except json.JSONDecodeError:
                    continue
                await _tratar_comando(ws, dados)
        except WebSocketDisconnect:
            pass
        except Exception:
            log.exception("Erro na conexão WebSocket")
        finally:
            estado.clientes.discard(ws)
            if estado.fonte_audio is ws:
                estado.fonte_audio = None
                if estado.segmentador:
                    estado.segmentador.finalizar_pendente()

    async def _tratar_comando(ws: WebSocket, dados: dict) -> None:
        tipo = dados.get("tipo")
        if tipo == "iniciar" or tipo == "idiomas":
            idiomas = estado.definir_idiomas(dados.get("idiomas") or [])
            if dados.get("nova_reuniao"):
                estado.sessao.nova_reuniao()
                estado.enviar_todos({"tipo": "limpar"})
            if tipo == "iniciar" and estado.sessao.pausado:
                estado.pausar(False)
            estado.enviar_todos({"tipo": "sessao", "sessao": estado.sessao.para_json(), "idiomas": idiomas})
            await ws.send_text(json.dumps({"tipo": "historico", "falas": estado.sessao.historico[-300:]}, ensure_ascii=False))
        elif tipo == "pausar":
            estado.pausar(True)
        elif tipo == "retomar":
            estado.pausar(False)
        elif tipo == "nova_reuniao":
            estado.sessao.nova_reuniao()
            estado.enviar_todos({"tipo": "limpar"})
            estado.enviar_todos({"tipo": "sessao", "sessao": estado.sessao.para_json(),
                                 "idiomas": estado.sessao.idiomas_visitante})
        elif tipo == "fim_audio":
            if estado.segmentador:
                estado.segmentador.finalizar_pendente()
        elif tipo == "ping":
            await ws.send_text('{"tipo":"pong"}')

    app.state.estado = estado
    return app
