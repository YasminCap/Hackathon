"""
main.py — API do Olho d'Água (FastAPI).

Ao subir:
  1. cria/abre o banco SQLite;
  2. conecta no MQTT e começa a gravar as leituras dos hidrômetros;
  3. liga a detecção (a cada 2 s) e o bot do Telegram (se houver TELEGRAM_TOKEN);
  4. expõe a API JSON abaixo e serve o painel (pasta painel/) em http://127.0.0.1:8000

Rotas:
  GET  /api/saude                         — MQTT conectado? quantas leituras?
  GET  /api/resumo                        — números gerais para o topo do painel
  GET  /api/predios                       — cadastro + última leitura de cada prédio
  GET  /api/predios/{id}/leituras?limite= — série recente (gráfico de vazão)
  GET  /api/predios/{id}/consumo_horario?horas= — litros por hora (horário de Londrina)
  POST /api/predios/{id}/comando          — fechar/abrir registro via MQTT
  GET  /api/alertas                       — alertas de vazamento/consumo excessivo
  GET  /api/comandos                      — últimos comandos enviados
  Documentação interativa: http://127.0.0.1:8000/docs

Como rodar (na raiz do projeto):
    .venv\\Scripts\\python.exe -m backend.main
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .config import MODO_DEMO, PASTA_PAINEL, SEGUNDOS_ONLINE, carregar_predios
from .deteccao import Detector
from .mqtt_cliente import ClienteMQTT
from .telegram_bot import NotificadorTelegram

# Terminal do Windows: garante acentos nos logs
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PREDIOS = carregar_predios()  # cadastro SIMULADO (dados/escolas.json)
IDS_ATIVOS = {pid for pid, p in PREDIOS.items() if p["ativo"]}

mqtt_cliente = ClienteMQTT(IDS_ATIVOS)
detector = Detector(PREDIOS)
notificador = NotificadorTelegram(PREDIOS, mqtt_cliente.enviar_comando)

INTERVALO_DETECCAO_S = 2


async def laco_deteccao() -> None:
    """A cada 2 s: avalia as regras (numa thread, por causa do SQLite) e avisa no Telegram."""
    while True:
        try:
            eventos = await asyncio.to_thread(detector.avaliar)
            for evento in eventos:
                await notificador.notificar(evento)
        except Exception as erro:  # o laço não pode morrer
            print(f"[DETECÇÃO] Erro: {erro!r}")
        await asyncio.sleep(INTERVALO_DETECCAO_S)


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    db.inicializar()
    if not db.media_por_faixa(next(iter(IDS_ATIVOS))):
        print("[AVISO] Sem histórico de consumo: a regra de consumo excessivo fica desligada. "
              "Rode: .venv\\Scripts\\python.exe simulador\\gerar_historico.py")
    mqtt_cliente.iniciar()
    await notificador.iniciar()
    tarefa = asyncio.create_task(laco_deteccao())
    print(f"[DETECÇÃO] Ligada{' (MODO_DEMO: limites curtos)' if MODO_DEMO else ''}")
    print("[API] Pronta em http://127.0.0.1:8000  (docs em /docs)")
    yield
    tarefa.cancel()
    await notificador.parar()
    mqtt_cliente.parar()


app = FastAPI(
    title="Olho d'Água — API",
    description="Monitoramento de água das escolas municipais e CMEIs de Londrina. "
                "Protótipo: todos os dados são SIMULADOS.",
    lifespan=ciclo_de_vida,
)


# --------------------------------------------------------------------- apoio
def _segundos_desde(utc_iso: str) -> float:
    instante = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - instante).total_seconds()


def _predio_ou_404(pid: str) -> dict:
    if pid not in PREDIOS:
        raise HTTPException(404, f"Prédio '{pid}' não cadastrado")
    return PREDIOS[pid]


# ---------------------------------------------------------------------- rotas
@app.get("/api/saude")
def saude():
    return {
        "mqtt_conectado": mqtt_cliente.conectado,
        "mensagens_aceitas": mqtt_cliente.recebidas,
        "mensagens_rejeitadas": mqtt_cliente.rejeitadas,
        "leituras_no_banco": db.contar_leituras(),
    }


@app.get("/api/predios")
def listar_predios():
    ultimas = db.ultimas_leituras()
    registros = db.estado_registros()
    alertas = {a["dispositivo"]: a for a in db.alertas_recentes(50) if a["status"] == "ativo"}
    resposta = []
    for pid, p in PREDIOS.items():
        u = ultimas.get(pid)
        online = bool(u) and _segundos_desde(u["recebido_em"]) <= SEGUNDOS_ONLINE
        resposta.append({
            **p,
            "online": online,
            # inativo não tem hidrômetro nem registro controlável
            "registro": registros.get(pid, "aberto") if p["ativo"] else None,
            "vazao_lpm": u["vazao_lpm"] if online else None,
            "total_litros": u["total_litros"] if u else None,
            "ultima_leitura": u["ts_local"] if u else None,  # horário de Londrina (simulado)
            "alerta": alertas.get(pid),                       # alerta ativo ou None
        })
    return {"aviso": "DADOS SIMULADOS", "predios": resposta}


@app.get("/api/resumo")
def resumo():
    predios = listar_predios()["predios"]
    online = [p for p in predios if p["online"]]
    horarios = [p["ultima_leitura"] for p in predios if p["ultima_leitura"]]
    return {
        "aviso": "DADOS SIMULADOS",
        "predios_cadastrados": len(predios),
        "predios_ativos": len(IDS_ATIVOS),
        "predios_online": len(online),
        "vazao_total_lpm": round(sum(p["vazao_lpm"] or 0 for p in online), 2),
        "registros_fechados": sum(1 for p in predios if p["registro"] == "fechado"),
        "alertas_ativos": sum(1 for p in predios if p["alerta"]),
        "telegram_ativo": notificador.ativo,
        "relogio_simulado": max(horarios) if horarios else None,
        "mqtt_conectado": mqtt_cliente.conectado,
    }


@app.get("/api/predios/{pid}/leituras")
def leituras(pid: str, limite: int = Query(180, ge=1, le=5000)):
    """Padrão 180 leituras = 6 min reais = 6 h simuladas (fator 60, 1 leitura a cada 2 s)."""
    _predio_ou_404(pid)
    return {"predio": pid, "leituras": db.leituras_recentes(pid, limite)}


@app.get("/api/predios/{pid}/consumo_horario")
def consumo_horario(pid: str, horas: int = Query(24, ge=1, le=24 * 31)):
    _predio_ou_404(pid)
    return {"predio": pid, "horas": db.consumo_por_hora(pid, horas)}


class Comando(BaseModel):
    acao: Literal["fechar_registro", "abrir_registro"]
    autorizado_por: str = Field("painel", min_length=1, max_length=80)


@app.post("/api/predios/{pid}/comando")
def enviar_comando(pid: str, comando: Comando):
    predio = _predio_ou_404(pid)
    if not predio["ativo"]:
        raise HTTPException(409, "Prédio inativo não tem hidrômetro")
    try:
        return mqtt_cliente.enviar_comando(pid, comando.acao, comando.autorizado_por)
    except ConnectionError as erro:
        raise HTTPException(503, str(erro)) from erro


@app.get("/api/alertas")
def listar_alertas(limite: int = Query(30, ge=1, le=200)):
    """Alertas ativos primeiro, depois os mais recentes."""
    alertas = db.alertas_recentes(limite)
    for a in alertas:
        a["nome"] = PREDIOS.get(a["dispositivo"], {}).get("nome", a["dispositivo"])
    return {"aviso": "DADOS SIMULADOS", "alertas": alertas}


@app.get("/api/comandos")
def comandos(limite: int = Query(20, ge=1, le=200)):
    return {"comandos": db.comandos_recentes(limite)}


# --------------------------------------------------------------------- painel
@app.get("/", include_in_schema=False)
def pagina_inicial():
    indice = PASTA_PAINEL / "index.html"
    if indice.exists():
        return FileResponse(indice)
    return HTMLResponse(
        "<h1>Olho d'Água — API no ar</h1>"
        "<p>O painel (painel/index.html) ainda não foi criado. "
        "Veja a API em <a href='/docs'>/docs</a>.</p>"
    )


# Demais arquivos do painel (app.js, guardias.html...) — montado por último
app.mount("/", StaticFiles(directory=PASTA_PAINEL, html=True), name="painel")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
