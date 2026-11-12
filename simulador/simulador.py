"""
simulador.py — hidrômetros SIMULADOS das escolas municipais e CMEIs (Olho d'Água).

Faz o papel que um ESP32 com sensor de vazão faria em cada prédio:
  • publica leituras em  hidrometro/<id>/leitura   (mesmo contrato do ESP32 real)
  • obedece comandos em  hidrometro/<id>/comando   (fechar_registro / abrir_registro)

Recursos:
  • Consumo realista: picos na entrada, intervalos e merenda; quase zero de madrugada
    e no fim de semana. A média diária de cada prédio bate com `media_diaria_litros`.
  • Tempo acelerado (FATOR_TEMPO, padrão 60 → 1 min real = 1 h simulada).
  • "Modo madrugada": pula o relógio para 01:00 de um dia útil (bom para demo de vazamento).
  • Cenários injetáveis por prédio: descarga, boia, cano_rompido, torneira.
  • Painel web simples em http://127.0.0.1:8001 para injetar cenários e mexer no relógio.

Como rodar (na raiz do projeto, com o .venv ativo):
    python simulador/simulador.py                 # tempo acelerado padrão
    python simulador/simulador.py --madrugada     # já começa às 01:00 de um dia útil
    python simulador/simulador.py --fator 120     # 1 min real = 2 h simuladas

Todos os dados gerados aqui são SIMULADOS.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

# Terminal do Windows: garante acentos
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# Londrina = UTC-3 (sem horário de verão desde 2019)
FUSO_LOCAL = timezone(timedelta(hours=-3), "America/Sao_Paulo")

# ---------------------------------------------------------------------------
# Configuração (via .env, com padrões seguros para teste rápido)
# ---------------------------------------------------------------------------
MQTT_BROKER = os.getenv("MQTT_BROKER") or "broker.hivemq.com"
MQTT_TLS = (os.getenv("MQTT_TLS") or "0") == "1"
MQTT_PORTA = int(os.getenv("MQTT_PORTA") or (8883 if MQTT_TLS else 1883))
MQTT_USUARIO = os.getenv("MQTT_USUARIO") or None
MQTT_SENHA = os.getenv("MQTT_SENHA") or None
FATOR_TEMPO_PADRAO = float(os.getenv("FATOR_TEMPO") or 60)

# Cenários de vazamento: faixa de vazão (L/min) sorteada na injeção
CENARIOS = {
    "descarga": (0.5, 3.0),       # válvula de descarga escorrendo
    "boia": (3.0, 6.0),           # boia da caixa d'água travada aberta
    "cano_rompido": (40.0, 80.0), # salto para vazão alta
    "torneira": (5.0, 10.0),      # torneira esquecida aberta
}

# Picos de uso ao longo do dia: (centro em minutos do dia, largura, altura).
# "inicio"/"fim" são substituídos pelo horário de uso de cada prédio.
PERFIS = {
    "escola": {
        "base": 0.35,
        "picos": [
            ("inicio+20", 15, 2.0),  # entrada da manhã (banheiros, bebedouros)
            (9 * 60 + 30, 15, 1.5),  # intervalo da manhã
            (11 * 60 + 30, 30, 2.2), # merenda / almoço (cozinha + lavagem)
            (13 * 60 + 10, 15, 1.8), # entrada da tarde
            (15 * 60 + 15, 15, 1.5), # intervalo da tarde
            ("fim-40", 25, 1.2),     # limpeza no fim do expediente
        ],
    },
    "cmei": {
        "base": 0.5,
        "picos": [
            ("inicio+30", 20, 1.2),  # chegada das crianças
            (8 * 60, 20, 1.0),       # café da manhã
            (11 * 60, 30, 2.0),      # almoço
            (13 * 60 + 30, 30, 1.5), # higiene / banho
            (15 * 60, 20, 1.0),      # lanche
            ("fim-60", 30, 1.2),     # jantar e limpeza
        ],
    },
}


DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def data_legivel(d: datetime, formato: str) -> str:
    """strftime com o dia da semana em português (o %a do Windows sai em inglês)."""
    return DIAS_SEMANA[d.weekday()] + " " + d.strftime(formato)


def hhmm_para_minutos(texto: str) -> int:
    h, m = texto.split(":")
    return int(h) * 60 + int(m)


@dataclass
class Predio:
    """Estado de um hidrômetro simulado."""

    id: str
    nome: str
    tipo: str
    inicio_min: int
    fim_min: int
    media_diaria: float
    total_litros: float
    vazao_lpm: float = 0.0
    registro_aberto: bool = True
    cenario: str | None = None
    cenario_vazao: float = 0.0
    escala: float = 0.0              # L/min por unidade de peso do perfil
    picos: list = field(default_factory=list)
    base: float = 0.0

    def preparar_perfil(self) -> None:
        """Resolve os picos e calcula a escala para a soma do dia = média diária."""
        perfil = PERFIS[self.tipo]
        self.base = perfil["base"]
        self.picos = []
        for centro, largura, altura in perfil["picos"]:
            if isinstance(centro, str):  # "inicio+20" ou "fim-40"
                ref = "inicio" if centro.startswith("inicio") else "fim"
                desloc = int(centro[len(ref):] or 0)
                centro = (self.inicio_min if ref == "inicio" else self.fim_min) + desloc
            self.picos.append((centro, largura, altura))
        soma_pesos = sum(self.peso(m) for m in range(24 * 60))
        self.escala = self.media_diaria / soma_pesos if soma_pesos else 0.0

    def peso(self, minuto_do_dia: float) -> float:
        """Peso relativo de uso naquele minuto (0 fora do horário de uso)."""
        if not (self.inicio_min <= minuto_do_dia < self.fim_min):
            return 0.0
        return self.base + sum(
            a * math.exp(-0.5 * ((minuto_do_dia - c) / s) ** 2) for c, s, a in self.picos
        )

    def vazao_esperada(self, agora: datetime) -> float:
        """Vazão média esperada (L/min) para o horário — sem ruído e sem vazamentos."""
        if agora.weekday() >= 5:  # sábado/domingo: prédio fechado
            return 0.0
        return self.peso(agora.hour * 60 + agora.minute + agora.second / 60) * self.escala

    def em_horario(self, agora: datetime) -> bool:
        m = agora.hour * 60 + agora.minute
        return agora.weekday() < 5 and self.inicio_min <= m < self.fim_min


class Simulador:
    """Relógio simulado + prédios + publicação MQTT."""

    def __init__(self, fator: float, intervalo_s: float, madrugada: bool, verboso: bool):
        self.fator = fator
        self.intervalo_s = intervalo_s
        self.verboso = verboso
        self.trava = threading.Lock()
        self.agora = datetime.now(FUSO_LOCAL).replace(microsecond=0)
        if madrugada:
            self.pular_para_madrugada()
        self.predios = self._carregar_predios()
        self.mqtt = self._criar_cliente_mqtt()
        self._ultima_hora_logada = None

    # ---------------------------------------------------------------- cadastro
    def _carregar_predios(self) -> dict[str, Predio]:
        with open(RAIZ / "dados" / "escolas.json", encoding="utf-8") as f:
            cadastro = json.load(f)["predios"]
        predios = {}
        for p in cadastro:
            if not p["ativo"]:
                continue  # prédio desativado não tem hidrômetro publicando
            ini, fim = p["horario_uso"].split("-")
            rng = random.Random(p["id"])  # leitura inicial estável por prédio
            predio = Predio(
                id=p["id"],
                nome=p["nome"],
                tipo=p["tipo"],
                inicio_min=hhmm_para_minutos(ini),
                fim_min=hhmm_para_minutos(fim),
                media_diaria=float(p["media_diaria_litros"]),
                total_litros=round(rng.uniform(100_000, 900_000), 1),
            )
            predio.preparar_perfil()
            predios[predio.id] = predio
        print(f"[OK] {len(predios)} prédios ativos carregados de dados/escolas.json")
        return predios

    # -------------------------------------------------------------------- MQTT
    def _criar_cliente_mqtt(self) -> mqtt.Client:
        cliente = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"olhodagua-simulador-{uuid.uuid4().hex[:6]}",
        )
        if MQTT_USUARIO:
            cliente.username_pw_set(MQTT_USUARIO, MQTT_SENHA)
        if MQTT_TLS:
            cliente.tls_set()
        cliente.on_connect = self._ao_conectar
        cliente.on_disconnect = self._ao_desconectar
        cliente.on_message = self._ao_receber_comando
        return cliente

    def conectar(self) -> None:
        print(f"[..] Conectando em {MQTT_BROKER}:{MQTT_PORTA} (TLS={'sim' if MQTT_TLS else 'não'})")
        # connect_async + loop_start: reconecta sozinho se a rede cair
        self.mqtt.connect_async(MQTT_BROKER, MQTT_PORTA, keepalive=30)
        self.mqtt.loop_start()

    def _ao_conectar(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[ERRO] Conexão MQTT recusada: {reason_code}")
            return
        print("[OK] MQTT conectado — escutando hidrometro/+/comando")
        client.subscribe("hidrometro/+/comando", qos=1)

    def _ao_desconectar(self, client, userdata, flags, reason_code, properties):
        print(f"[!!] MQTT desconectado ({reason_code}); tentando reconectar...")

    def _ao_receber_comando(self, client, userdata, msg):
        """Comando vindo do backend/Telegram: fecha ou reabre o registro do prédio."""
        partes = msg.topic.split("/")
        predio_id = partes[1] if len(partes) == 3 else None
        try:
            comando = json.loads(msg.payload.decode("utf-8"))
            acao = comando["acao"]
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
            print(f"[!!] Comando inválido em {msg.topic}: {msg.payload[:100]!r}")
            return
        with self.trava:
            predio = self.predios.get(predio_id)
            if predio is None:
                print(f"[!!] Comando para prédio desconhecido: {predio_id}")
                return
            if acao == "fechar_registro":
                predio.registro_aberto = False
            elif acao == "abrir_registro":
                predio.registro_aberto = True
            else:
                print(f"[!!] Ação desconhecida '{acao}' para {predio_id}")
                return
        quem = comando.get("autorizado_por", "?")
        print(f"[CMD] {predio_id}: {acao} (autorizado por {quem})")

    # ------------------------------------------------------------------ relógio
    def pular_para_madrugada(self) -> None:
        """Leva o relógio para 01:00 do próximo dia útil."""
        alvo = (self.agora + timedelta(days=1)).replace(hour=1, minute=0, second=0)
        while alvo.weekday() >= 5:
            alvo += timedelta(days=1)
        self.agora = alvo
        print(f"[RELÓGIO] Modo madrugada: {data_legivel(self.agora, '%d/%m %H:%M')}")

    # ------------------------------------------------------------------- ciclo
    def _vazao_do_predio(self, p: Predio) -> float:
        """Uso normal (com ruído) + vazamento ativo; zero se o registro estiver fechado."""
        if not p.registro_aberto:
            return 0.0
        esperada = p.vazao_esperada(self.agora)
        if esperada > 0:
            normal = esperada * random.uniform(0.6, 1.4)
        elif random.random() < 0.01:
            normal = random.uniform(2.0, 8.0)  # uso esporádico (vigia, limpeza) — 1 leitura só
        else:
            normal = 0.0
        vazamento = p.cenario_vazao * random.uniform(0.95, 1.05) if p.cenario else 0.0
        return round(normal + vazamento, 2)

    def passo(self) -> None:
        """Avança o relógio um intervalo e publica uma leitura por prédio."""
        with self.trava:
            minutos_sim = self.intervalo_s * self.fator / 60
            self.agora += timedelta(minutes=minutos_sim)
            carimbo = self.agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            mensagens = []
            for p in self.predios.values():
                p.vazao_lpm = self._vazao_do_predio(p)
                litros = round(p.vazao_lpm * minutos_sim, 2)
                p.total_litros = round(p.total_litros + litros, 2)
                mensagens.append((p.id, {
                    "dispositivo": p.id,
                    "litros": litros,
                    "vazao_lpm": p.vazao_lpm,
                    "total_litros": p.total_litros,
                    "timestamp": carimbo,
                    "simulado": True,
                }))
            total_vazao = sum(p.vazao_lpm for p in self.predios.values())
            hora = data_legivel(self.agora, "%d/%m %H:00")

        for pid, leitura in mensagens:
            self.mqtt.publish(f"hidrometro/{pid}/leitura", json.dumps(leitura), qos=0)
            if self.verboso:
                print(f"  → {pid}: {leitura['vazao_lpm']:6.2f} L/min  {leitura['litros']:7.2f} L")

        if hora != self._ultima_hora_logada:  # resumo uma vez por hora simulada
            self._ultima_hora_logada = hora
            print(f"[{hora}] vazão somada: {total_vazao:7.2f} L/min")

    def rodar_para_sempre(self) -> None:
        proximo = time.monotonic()
        while True:
            try:
                self.passo()
            except Exception as erro:  # não deixa o simulador morrer por um erro pontual
                print(f"[ERRO] no passo do simulador: {erro!r}")
            proximo += self.intervalo_s
            time.sleep(max(0.0, proximo - time.monotonic()))

    # ------------------------------------------------------------------ estado
    def estado(self) -> dict:
        with self.trava:
            return {
                "aviso": "DADOS SIMULADOS",
                "relogio": self.agora.isoformat(),
                "relogio_legivel": data_legivel(self.agora, "%d/%m/%Y %H:%M"),
                "fator_tempo": self.fator,
                "mqtt_conectado": self.mqtt.is_connected(),
                "broker": f"{MQTT_BROKER}:{MQTT_PORTA}",
                "predios": [
                    {
                        "id": p.id,
                        "nome": p.nome,
                        "tipo": p.tipo,
                        "vazao_lpm": p.vazao_lpm,
                        "total_litros": p.total_litros,
                        "registro": "aberto" if p.registro_aberto else "fechado",
                        "cenario": p.cenario,
                        "cenario_vazao": round(p.cenario_vazao, 2),
                        "em_horario": p.em_horario(self.agora),
                    }
                    for p in self.predios.values()
                ],
            }


# ---------------------------------------------------------------------------
# API + painel de controle do simulador
# ---------------------------------------------------------------------------
def criar_app(sim: Simulador) -> FastAPI:
    app = FastAPI(title="Olho d'Água — Simulador (dados simulados)")

    def _predio(pid: str) -> Predio:
        if pid not in sim.predios:
            raise HTTPException(404, f"Prédio '{pid}' não existe ou está inativo")
        return sim.predios[pid]

    @app.get("/", response_class=HTMLResponse)
    def painel():
        return (Path(__file__).parent / "painel_simulador.html").read_text(encoding="utf-8")

    @app.get("/api/estado")
    def estado():
        return sim.estado()

    @app.get("/api/cenarios")
    def cenarios():
        return {nome: {"min_lpm": a, "max_lpm": b} for nome, (a, b) in CENARIOS.items()}

    @app.post("/api/cenario/{pid}/{cenario}")
    def injetar(pid: str, cenario: str):
        """Injeta um vazamento. cenario='nenhum' = manutenção consertou."""
        with sim.trava:
            p = _predio(pid)
            if cenario == "nenhum":
                p.cenario, p.cenario_vazao = None, 0.0
            elif cenario in CENARIOS:
                p.cenario = cenario
                p.cenario_vazao = random.uniform(*CENARIOS[cenario])
            else:
                raise HTTPException(400, f"Cenário inválido. Use: {', '.join(CENARIOS)} ou nenhum")
        print(f"[CENÁRIO] {pid}: {cenario} ({p.cenario_vazao:.2f} L/min)")
        return {"ok": True, "predio": pid, "cenario": p.cenario, "vazao_lpm": round(p.cenario_vazao, 2)}

    @app.post("/api/registro/{pid}/{acao}")
    def registro(pid: str, acao: str):
        """Atalho local para abrir/fechar o registro (o caminho oficial é o tópico MQTT)."""
        if acao not in ("abrir", "fechar"):
            raise HTTPException(400, "Use abrir ou fechar")
        with sim.trava:
            _predio(pid).registro_aberto = acao == "abrir"
        print(f"[REGISTRO] {pid}: {acao} (pelo painel do simulador)")
        return {"ok": True}

    @app.post("/api/madrugada")
    def madrugada():
        with sim.trava:
            sim.pular_para_madrugada()
        return {"ok": True, "relogio": sim.agora.isoformat()}

    @app.post("/api/pular")
    def pular(horas: float = 1.0):
        with sim.trava:
            sim.agora += timedelta(hours=horas)
        return {"ok": True, "relogio": sim.agora.isoformat()}

    @app.post("/api/fator")
    def fator(valor: float):
        if not 1 <= valor <= 1440:
            raise HTTPException(400, "Fator entre 1 e 1440")
        with sim.trava:
            sim.fator = valor
        print(f"[RELÓGIO] Fator de tempo: {valor:g}x")
        return {"ok": True, "fator_tempo": valor}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de hidrômetros (dados simulados)")
    parser.add_argument("--fator", type=float, default=FATOR_TEMPO_PADRAO,
                        help="min simulados por min real (padrão 60 = 1 min real → 1 h)")
    parser.add_argument("--intervalo", type=float, default=2.0,
                        help="segundos reais entre leituras (padrão 2)")
    parser.add_argument("--madrugada", action="store_true",
                        help="começa às 01:00 de um dia útil")
    parser.add_argument("--porta", type=int, default=8001, help="porta do painel do simulador")
    parser.add_argument("--verboso", action="store_true", help="mostra cada leitura publicada")
    args = parser.parse_args()

    sim = Simulador(args.fator, args.intervalo, args.madrugada, args.verboso)
    sim.conectar()
    threading.Thread(target=sim.rodar_para_sempre, daemon=True).start()

    print(f"[OK] Simulador rodando — {args.fator:g} min simulados por min real")
    print(f"[OK] Painel do simulador: http://127.0.0.1:{args.porta}")
    try:
        uvicorn.run(criar_app(sim), host="127.0.0.1", port=args.porta, log_level="warning")
    finally:
        sim.mqtt.loop_stop()
        sim.mqtt.disconnect()
        print("[OK] Simulador encerrado")


if __name__ == "__main__":
    main()
