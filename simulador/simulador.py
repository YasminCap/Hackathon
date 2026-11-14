"""
simulador.py — hidrômetros SIMULADOS das escolas municipais e CMEIs (LeakFinder Londrina).
Também traz perfis de outros prédios da prefeitura (secretarias, UBS, esporte, cultura,
CRAS) para a fase 2; o cadastro do protótipo (dados/predios.json) usa só escolas e CMEIs.

Faz o papel da ESP32-CAM que, em cada prédio, fotografa o mostrador do hidrômetro:
  • publica UMA leitura a cada 30 min simulados em hidrometro/<id>/leitura
    (mesmo contrato da câmera real: total lido no mostrador + litros e média desde a foto anterior)

Recursos:
  • Consumo realista por tipo de prédio (picos de entrada, almoço, limpeza, banhos...);
    zero fora do horário de uso. Prédios com dias_uso="uteis" ficam fechados no fim de
    semana; "todos" (ginásio, centro cultural) abrem todo dia.
    A média diária de cada prédio bate com `media_diaria_litros`.
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
# De quantos em quantos minutos SIMULADOS a "câmera" fotografa o hidrômetro
PERIODO_LEITURA_MIN = float(os.getenv("PERIODO_LEITURA_MIN") or 30)
# Onde o simulador guarda o total de cada hidrômetro (um hidrômetro real nunca volta a zero;
# sem isso, ao reiniciar o simulador o backend veria o total "diminuir" e descartaria as leituras)
ARQUIVO_TOTAIS = Path(__file__).resolve().parent / "totais_hidrometros.json"

# Cenários de vazamento: faixa de vazão (L/min) sorteada na injeção
CENARIOS = {
    "descarga": (0.5, 3.0),       # válvula de descarga escorrendo
    "boia": (3.0, 4.8),           # boia travada aberta (abaixo de 5 L/min: não se confunde com torneira)
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
    "administrativo": {              # secretarias, sede
        "base": 0.5,
        "picos": [
            ("inicio+30", 20, 1.0),  # chegada dos servidores
            (12 * 60, 30, 1.2),      # almoço / copa
            (15 * 60, 20, 0.6),      # café da tarde
            ("fim-30", 20, 1.0),     # limpeza
        ],
    },
    "saude": {                       # UBS: pias, esterilização, limpeza frequente
        "base": 0.7,
        "picos": [
            ("inicio+30", 20, 1.2),  # abertura e triagem
            (10 * 60, 40, 0.6),      # atendimentos da manhã
            (13 * 60, 30, 0.8),      # turno da tarde
            ("fim-30", 25, 1.2),     # limpeza e desinfecção
        ],
    },
    "esporte": {                     # ginásio: vestiários e chuveiros
        "base": 0.3,
        "picos": [
            (9 * 60, 60, 0.8),       # treinos da manhã
            (19 * 60, 60, 2.0),      # treinos da noite (chuveiros)
            (21 * 60, 30, 1.2),      # fim dos treinos
            ("fim-20", 15, 1.0),     # limpeza
        ],
    },
    "cultura": {                     # centro cultural, biblioteca
        "base": 0.4,
        "picos": [
            (12 * 60, 30, 0.8),      # almoço
            (15 * 60, 30, 0.6),      # eventos da tarde
            ("fim-30", 20, 1.0),     # limpeza
        ],
    },
    "assistencia": {                 # CRAS, centros de convivência
        "base": 0.4,
        "picos": [
            ("inicio+30", 20, 0.8),  # abertura
            (12 * 60, 30, 1.0),      # almoço / lanche
            ("fim-30", 20, 0.8),     # limpeza
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
    todos_os_dias: bool = False      # dias_uso == "todos" (abre no fim de semana)
    vazao_lpm: float = 0.0           # vazão real neste instante (só o simulador sabe)
    litros_periodo: float = 0.0      # litros desde a última "foto"
    minutos_periodo: float = 0.0     # minutos simulados desde a última "foto"
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
        if agora.weekday() >= 5 and not self.todos_os_dias:  # fim de semana: fechado
            return 0.0
        return self.peso(agora.hour * 60 + agora.minute + agora.second / 60) * self.escala

    def em_horario(self, agora: datetime) -> bool:
        m = agora.hour * 60 + agora.minute
        return (self.todos_os_dias or agora.weekday() < 5) and self.inicio_min <= m < self.fim_min


def predio_do_cadastro(p: dict, total_litros: float = 0.0) -> Predio:
    """Cria o Predio simulado a partir de um item de dados/predios.json."""
    ini, fim = p["horario_uso"].split("-")
    predio = Predio(
        id=p["id"],
        nome=p["nome"],
        tipo=p["tipo"],
        inicio_min=hhmm_para_minutos(ini),
        fim_min=hhmm_para_minutos(fim),
        media_diaria=float(p["media_diaria_litros"]),
        total_litros=total_litros,
        todos_os_dias=p.get("dias_uso", "uteis") == "todos",
    )
    predio.preparar_perfil()
    return predio


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
        self._ultima_foto = None  # número da última janela de PERIODO_LEITURA_MIN fotografada

    # ---------------------------------------------------------------- cadastro
    def _carregar_predios(self) -> dict[str, Predio]:
        with open(RAIZ / "dados" / "predios.json", encoding="utf-8") as f:
            cadastro = json.load(f)["predios"]
        try:
            totais_salvos = json.loads(ARQUIVO_TOTAIS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            totais_salvos = {}
        predios = {}
        for p in cadastro:
            if not p["ativo"] or not p.get("camera_instalada", True):
                continue  # desativado ou ainda sem câmera: não há leituras
            rng = random.Random(p["id"])  # leitura inicial estável por prédio
            total = totais_salvos.get(p["id"], round(rng.uniform(100_000, 900_000), 1))
            predio = predio_do_cadastro(p, total)
            predios[predio.id] = predio
        print(f"[OK] {len(predios)} prédios ativos carregados de dados/predios.json")
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
        print("[OK] MQTT conectado — publicando as fotos dos hidrômetros")

    def _ao_desconectar(self, client, userdata, flags, reason_code, properties):
        print(f"[!!] MQTT desconectado ({reason_code}); tentando reconectar...")

    # ------------------------------------------------------------------ relógio
    def pular_para_madrugada(self) -> None:
        """Leva o relógio para 01:00 do próximo dia útil."""
        alvo = (self.agora + timedelta(days=1)).replace(hour=1, minute=0, second=0)
        while alvo.weekday() >= 5:
            alvo += timedelta(days=1)
        self.agora = alvo
        print(f"[RELÓGIO] Modo madrugada: {data_legivel(self.agora, '%d/%m %H:%M')}")

    # ------------------------------------------------------------------- ciclo
    def _vazao_do_predio(self, p: Predio, instante: datetime) -> float:
        """Uso normal (com ruído) + vazamento ativo."""
        esperada = p.vazao_esperada(instante)
        if esperada > 0:
            normal = esperada * random.uniform(0.6, 1.4)
        elif random.random() < 0.0005:
            normal = random.uniform(2.0, 8.0)  # uso esporádico raro (vigia, limpeza) — 2 min só
        else:
            normal = 0.0
        vazamento = p.cenario_vazao * random.uniform(0.95, 1.05) if p.cenario else 0.0
        return round(normal + vazamento, 2)

    def passo(self, minutos_sim: float | None = None) -> None:
        """Avança o relógio um intervalo. A água corre minuto a minuto (o hidrômetro gira),
        mas só a cada PERIODO_LEITURA_MIN simulados a "câmera" fotografa e publica.
        Sem argumento, o intervalo é o do tempo acelerado (intervalo_s × fator)."""
        with self.trava:
            if minutos_sim is None:
                minutos_sim = self.intervalo_s * self.fator / 60
            self.agora += timedelta(minutes=minutos_sim)
            # o consumo do intervalo usa a vazão do MEIO dele
            # (medir no fim jogaria uso para antes da abertura do prédio)
            meio_do_intervalo = self.agora - timedelta(minutes=minutos_sim / 2)
            for p in self.predios.values():
                p.vazao_lpm = self._vazao_do_predio(p, meio_do_intervalo)
                litros = p.vazao_lpm * minutos_sim
                p.total_litros += litros
                p.litros_periodo += litros
                p.minutos_periodo += minutos_sim

            # Hora da foto? (uma por janela de PERIODO_LEITURA_MIN: 00:00, 00:30, 01:00...)
            janela = int(self.agora.timestamp() // 60 // PERIODO_LEITURA_MIN)
            mensagens = []
            if janela != self._ultima_foto:
                self._ultima_foto = janela
                carimbo = self.agora.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                for p in self.predios.values():
                    minutos = max(p.minutos_periodo, minutos_sim)
                    mensagens.append((p.id, {
                        "dispositivo": p.id,
                        "total_litros": round(p.total_litros, 1),   # o que a foto mostra
                        "litros": round(p.litros_periodo, 1),       # desde a foto anterior
                        "vazao_lpm": round(p.litros_periodo / minutos, 2),  # média do período
                        "timestamp": carimbo,
                        "simulado": True,
                    }))
                    p.litros_periodo = 0.0
                    p.minutos_periodo = 0.0
                self._salvar_totais()
            total_vazao = sum(p.vazao_lpm for p in self.predios.values())
            hora = data_legivel(self.agora, "%d/%m %H:00")

        for pid, leitura in mensagens:
            self.mqtt.publish(f"hidrometro/{pid}/leitura", json.dumps(leitura), qos=0)
            if self.verboso:
                print(f"  → {pid}: {leitura['litros']:8.1f} L na meia hora  (média {leitura['vazao_lpm']:6.2f} L/min)")

        if hora != self._ultima_hora_logada:  # resumo uma vez por hora simulada
            self._ultima_hora_logada = hora
            print(f"[{hora}] vazão somada: {total_vazao:7.2f} L/min")

    def adiantar(self, horas: float) -> None:
        """Avança o relógio SIMULANDO o tempo do meio, em passos de 2 min: a água corre,
        o vazamento soma litros e a "câmera" tira todas as fotos do período.
        (Pular direto deixaria um buraco sem fotos, e o detector não juntaria a sequência.)"""
        for _ in range(int(horas * 60 / 2)):
            self.passo(2.0)

    def _salvar_totais(self) -> None:
        """Guarda o número de cada hidrômetro para continuar dele na próxima execução."""
        try:
            ARQUIVO_TOTAIS.write_text(
                json.dumps({p.id: round(p.total_litros, 1) for p in self.predios.values()}),
                encoding="utf-8")
        except OSError as erro:
            print(f"[!!] Não foi possível salvar os totais: {erro}")

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
    app = FastAPI(title="LeakFinder Londrina — Simulador (dados simulados)")

    def _predio(pid: str) -> Predio:
        if pid not in sim.predios:
            raise HTTPException(404, f"Prédio '{pid}' não existe ou está inativo")
        return sim.predios[pid]

    @app.get("/", response_class=HTMLResponse)
    def painel():
        html = (Path(__file__).parent / "painel_simulador.html").read_text(encoding="utf-8")
        # no-cache: o navegador sempre pega a versão mais nova da tela
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    @app.get("/api/estado")
    def estado():
        return sim.estado()

    @app.get("/api/cenarios")
    def cenarios():
        return {nome: {"min_lpm": a, "max_lpm": b} for nome, (a, b) in CENARIOS.items()}

    @app.post("/api/cenario/{pid}/{cenario}")
    def injetar(pid: str, cenario: str):
        """Injeta um vazamento. cenario='aleatorio' sorteia o tipo (é o que a tela usa:
        a demonstração não diz qual é — quem descobre a provável causa é o sistema).
        cenario='nenhum' = manutenção consertou."""
        if cenario == "aleatorio":
            cenario = random.choice(list(CENARIOS))
        with sim.trava:
            p = _predio(pid)
            if cenario == "nenhum":
                p.cenario, p.cenario_vazao = None, 0.0
            elif cenario in CENARIOS:
                p.cenario = cenario
                p.cenario_vazao = random.uniform(*CENARIOS[cenario])
            else:
                raise HTTPException(400, f"Cenário inválido. Use: aleatorio, {', '.join(CENARIOS)} ou nenhum")
        print(f"[CENÁRIO] {pid}: {cenario} ({p.cenario_vazao:.2f} L/min)")
        return {"ok": True, "predio": pid, "cenario": p.cenario, "vazao_lpm": round(p.cenario_vazao, 2)}

    @app.post("/api/madrugada")
    def madrugada():
        with sim.trava:
            sim.pular_para_madrugada()
        return {"ok": True, "relogio": sim.agora.isoformat()}

    @app.post("/api/pular")
    def pular(horas: float = 1.0):
        """Adianta o relógio simulando o período (com todas as fotos), não pulando direto."""
        if not 0 < horas <= 12:
            raise HTTPException(400, "Use de 0 a 12 horas")
        sim.adiantar(horas)
        print(f"[RELÓGIO] Adiantado {horas:g} h (com as fotos do período)")
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
