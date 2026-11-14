"""
main.py — API do LeakFinder Londrina (FastAPI).

Ao subir:
  1. cria/abre o banco SQLite;
  2. conecta no MQTT e começa a gravar as leituras (fotos dos hidrômetros);
  3. liga a detecção (a cada 2 s, avalia as leituras novas);
  4. expõe a API JSON abaixo e serve o painel (pasta painel/) em http://127.0.0.1:8000

Rotas:
  GET  /api/saude                          — MQTT conectado? quantas leituras?
  GET  /api/resumo                         — números gerais para o topo do painel
  GET  /api/predios                        — cadastro + última leitura de cada unidade
  GET  /api/predios/{id}/leituras?limite=  — série recente (gráfico)
  GET  /api/predios/{id}/consumo_horario?horas= — litros por hora (horário de Londrina)
  GET  /api/predios/{id}/semanal           — consumo por semana + média semanal de acompanhamento
  POST /api/predios                        — incluir unidade (fica "aguardando câmera")
  GET  /api/geocodificar?endereco=         — endereço em Londrina → ponto no mapa (OpenStreetMap)
  GET  /api/alertas?finalizados=           — alertas em andamento (padrão) ou finalizados (consertados)
  POST /api/alertas/{id}/operacao          — campo de operação: pendente | informado | consertado
  DELETE /api/alertas                      — limpar o histórico de vazamentos (zera a economia)
  GET  /api/economia                       — água não desperdiçada e valor poupado na conta
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
from pydantic import BaseModel

from . import avisos, db
from .cadastro import CadastroInvalido, incluir_unidade
from .config import MODO_DEMO, PASTA_PAINEL, SEGUNDOS_ONLINE, carregar_predios
from .economia import demonstrativo, economia_do_alerta
from .geocodificacao import EnderecoNaoEncontrado, localizar
from .deteccao import Detector
from .mqtt_cliente import ClienteMQTT

# Terminal do Windows: garante acentos nos logs
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PREDIOS = carregar_predios()  # cadastro SIMULADO (dados/predios.json)
IDS_ATIVOS = {pid for pid, p in PREDIOS.items() if p["ativo"]}

mqtt_cliente = ClienteMQTT(IDS_ATIVOS)
detector = Detector(PREDIOS)

INTERVALO_DETECCAO_S = 2


async def laco_deteccao() -> None:
    """A cada 2 s: avalia as regras (numa thread, por causa do SQLite) e mostra os alertas."""
    while True:
        try:
            for evento in await asyncio.to_thread(detector.avaliar):
                avisos.mostrar(evento)
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
    tarefa = asyncio.create_task(laco_deteccao())
    print(f"[DETECÇÃO] Ligada{' (MODO_DEMO: limites curtos)' if MODO_DEMO else ''}")
    print("[API] LeakFinder Londrina pronto em http://127.0.0.1:8000  (docs em /docs)")
    yield
    tarefa.cancel()
    mqtt_cliente.parar()


app = FastAPI(
    title="LeakFinder Londrina — API",
    description="Monitoramento de água das escolas municipais e CMEIs de Londrina. "
                "Protótipo: todos os dados são SIMULADOS.",
    lifespan=ciclo_de_vida,
)


@app.middleware("http")
async def sem_cache(request, call_next):
    """Faz o navegador sempre conferir se há versão nova do painel e da API
    (sem isso, depois de uma atualização ele pode continuar mostrando a tela antiga)."""
    resposta = await call_next(request)
    resposta.headers["Cache-Control"] = "no-cache"
    return resposta


# --------------------------------------------------------------------- apoio
def _segundos_desde(utc_iso: str) -> float:
    instante = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - instante).total_seconds()


def _predio_ou_404(pid: str) -> dict:
    if pid not in PREDIOS:
        raise HTTPException(404, f"Unidade '{pid}' não cadastrada")
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
    alertas = {a["dispositivo"]: a for a in db.alertas_recentes(50) if a["status"] == "ativo"}
    resposta = []
    for pid, p in PREDIOS.items():
        u = ultimas.get(pid)
        online = p.get("camera_instalada", True) and bool(u) and _segundos_desde(u["recebido_em"]) <= SEGUNDOS_ONLINE
        resposta.append({
            **p,
            "online": online,
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
    alertas = db.alertas_recentes(200)
    return {
        "aviso": "DADOS SIMULADOS",
        "predios_cadastrados": len(predios),
        "predios_ativos": len(IDS_ATIVOS),
        "predios_com_camera": sum(1 for p in predios if p["ativo"] and p.get("camera_instalada", True)),
        "predios_online": len(online),
        "vazao_total_lpm": round(sum(p["vazao_lpm"] or 0 for p in online), 2),
        "alertas_ativos": sum(1 for p in predios if p["alerta"]),
        # campo de operação: ocorrências que ninguém informou ainda à manutenção
        "aguardando_acao": sum(1 for a in alertas if a["operacao"] == "pendente"),
        "consertados": sum(1 for a in alertas if a["operacao"] == "consertado"),
        "finalizados": len(db.alertas_por_operacao(finalizados=True, limite=1000)),
        "relogio_simulado": max(horarios) if horarios else None,
        "mqtt_conectado": mqtt_cliente.conectado,
    }


@app.get("/api/predios/{pid}/leituras")
def leituras(pid: str, limite: int = Query(48, ge=1, le=5000)):
    """Padrão 48 leituras = 24 h simuladas (uma foto a cada 30 min)."""
    _predio_ou_404(pid)
    return {"predio": pid, "leituras": db.leituras_recentes(pid, limite)}


@app.get("/api/predios/{pid}/consumo_horario")
def consumo_horario(pid: str, horas: int = Query(24, ge=1, le=24 * 31)):
    _predio_ou_404(pid)
    return {"predio": pid, "horas": db.consumo_por_hora(pid, horas)}


@app.get("/api/predios/{pid}/semanal")
def consumo_semanal(pid: str, semanas: int = Query(8, ge=1, le=52)):
    """Histórico semanal (segunda a domingo) e a média semanal de acompanhamento.
    A média usa só semanas COMPLETAS (7 dias com registro) e anteriores à semana atual."""
    _predio_ou_404(pid)
    lista = db.consumo_semanal(pid, semanas)
    for s in lista:
        s["completa"] = s["dias"] >= 7
    anteriores = [s for s in lista[:-1] if s["completa"]]
    media = round(sum(s["litros"] for s in anteriores) / len(anteriores), 1) if anteriores else None
    atual = lista[-1] if lista else None
    variacao = None
    # média por dia derivada do consumo REGISTRADO (não de um valor informado no cadastro)
    media_diaria = round(media / 7) if media else None
    if atual and media and atual["completa"]:
        variacao = round((atual["litros"] - media) / media * 100, 1)
    return {"aviso": "DADOS SIMULADOS", "predio": pid, "semanas": lista,
            "media_semanal": media, "media_diaria": media_diaria, "semanas_na_media": len(anteriores),
            "semana_atual": atual, "variacao_pct": variacao}


class NovaUnidade(BaseModel):
    nome: str
    tipo: Literal["escola", "cmei"]
    endereco: str
    regiao: str = ""
    lat: float
    lon: float
    horario_uso: str
    dias_uso: Literal["uteis", "todos"] = "uteis"


@app.get("/api/geocodificar")
def geocodificar(endereco: str):
    """Procura o endereço em Londrina e devolve o ponto no mapa (para o cadastro)."""
    try:
        return localizar(endereco)
    except EnderecoNaoEncontrado as erro:
        raise HTTPException(404, str(erro)) from erro


@app.post("/api/predios", status_code=201)
def cadastrar_unidade(corpo: NovaUnidade):
    """Inclui uma escola ou CMEI. Fica 'aguardando câmera' até a ESP32-CAM ser instalada."""
    try:
        unidade = incluir_unidade(corpo.model_dump(), PREDIOS)
    except CadastroInvalido as erro:
        raise HTTPException(400, str(erro)) from erro
    IDS_ATIVOS.add(unidade["id"])            # leituras dela passam a ser aceitas
    detector.predios[unidade["id"]] = unidade
    print(f"[CADASTRO] Nova unidade {unidade['id']}: {unidade['nome']} (aguardando câmera)")
    return unidade


@app.get("/api/alertas")
def listar_alertas(finalizados: bool = False, limite: int = Query(30, ge=1, le=200)):
    """finalizados=false (padrão): alertas em andamento, ativos primeiro.
    finalizados=true: aba Finalizados — operação marcada como 'consertado'."""
    alertas = db.alertas_por_operacao(finalizados, limite)
    for a in alertas:
        a["nome"] = PREDIOS.get(a["dispositivo"], {}).get("nome", a["dispositivo"])
        a["economia"] = economia_do_alerta(a)
    return {"aviso": "DADOS SIMULADOS", "alertas": alertas}


@app.delete("/api/alertas")
def limpar_historico():
    """Botão "Limpar histórico de vazamentos": apaga todos os alertas (em andamento e
    finalizados) e, com eles, o demonstrativo de economia. Leituras e médias continuam."""
    apagados = db.limpar_alertas()
    print(f"[HISTÓRICO] {apagados} alerta(s) apagado(s) pelo painel")
    return {"ok": True, "apagados": apagados}


@app.get("/api/economia")
def economia():
    """Demonstrativo da água que não foi desperdiçada e do valor poupado na conta (simulado)."""
    return demonstrativo(db.todos_alertas())


class Operacao(BaseModel):
    operacao: Literal["pendente", "informado", "consertado"]


@app.post("/api/alertas/{alerta_id}/operacao")
def definir_operacao(alerta_id: int, corpo: Operacao):
    """Campo de operação preenchido pelo gestor: a manutenção já foi informada? Já consertou?"""
    alerta = db.definir_operacao(alerta_id, corpo.operacao)
    if not alerta:
        raise HTTPException(404, f"Alerta {alerta_id} não existe")
    print(f"[OPERAÇÃO] Alerta {alerta_id} ({alerta['dispositivo']}): {corpo.operacao}")
    return alerta


# --------------------------------------------------------------------- painel
@app.get("/", include_in_schema=False)
def pagina_inicial():
    indice = PASTA_PAINEL / "index.html"
    if indice.exists():
        return FileResponse(indice)
    return HTMLResponse(
        "<h1>LeakFinder Londrina — API no ar</h1>"
        "<p>O painel (painel/index.html) ainda não foi criado. "
        "Veja a API em <a href='/docs'>/docs</a>.</p>"
    )


# Demais arquivos do painel (app.js...) — montado por último
app.mount("/", StaticFiles(directory=PASTA_PAINEL, html=True), name="painel")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
