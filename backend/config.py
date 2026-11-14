"""
config.py — configurações do backend lidas do .env (python-dotenv).

Sem .env, os padrões permitem um teste rápido no broker público.
Credenciais NUNCA ficam no código: só no .env (que não vai para o Git).
"""

import json
import os
from datetime import timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

# Londrina = UTC-3 (sem horário de verão desde 2019)
FUSO_LOCAL = timezone(timedelta(hours=-3), "America/Sao_Paulo")

# --- MQTT ---
MQTT_BROKER = os.getenv("MQTT_BROKER") or "broker.hivemq.com"
MQTT_TLS = (os.getenv("MQTT_TLS") or "0") == "1"
MQTT_PORTA = int(os.getenv("MQTT_PORTA") or (8883 if MQTT_TLS else 1883))
MQTT_USUARIO = os.getenv("MQTT_USUARIO") or None
MQTT_SENHA = os.getenv("MQTT_SENHA") or None

# --- Banco ---
DB_CAMINHO = Path(os.getenv("DB_CAMINHO") or RAIZ / "olhodagua.db")

# --- Painel ---
PASTA_PAINEL = RAIZ / "painel"

# Prédio é considerado "online" se mandou leitura nos últimos N segundos REAIS.
# Com a "câmera" fotografando a cada 30 min simulados (30 s reais no fator 60), 90 s = ~3 fotos.
SEGUNDOS_ONLINE = int(os.getenv("SEGUNDOS_ONLINE") or 90)

# --- Detecção (tempos em minutos SIMULADOS) ---
MODO_DEMO = (os.getenv("MODO_DEMO") or "0") == "1"

# Leituras vêm de fotos do hidrômetro (ESP32-CAM): uma a cada PERIODO_LEITURA_MIN simulados.
# (O detector mede o período de verdade pelas próprias leituras; este é o valor padrão.)
PERIODO_LEITURA_MIN = float(os.getenv("PERIODO_LEITURA_MIN") or 30)
# Fora do horário: consumo em N fotos seguidas → vazamento (3 fotos ≈ 1 h entre a 1ª e a 3ª)
LEITURAS_VAZAMENTO = 2 if MODO_DEMO else 3
# No horário: janela usada para comparar o consumo com a média da mesma faixa (2 fotos)
JANELA_EXCESSO_MIN = 60
# Consumo da janela acima de FATOR × média da faixa → consumo excessivo
FATOR_EXCESSO = 2.0
# E o excesso precisa ser de pelo menos isso (L/min) — evita alarme quando a média é quase zero
MIN_EXCESSO_LPM = 2.0
# Abaixo disso (× média) o consumo excessivo é considerado resolvido (histerese)
FATOR_EXCESSO_RESOLVIDO = 1.3
# Depois de resolvido, espera isso antes de abrir outro alerta no mesmo prédio
COOLDOWN_MIN = 30 if MODO_DEMO else 120
# Buraco entre leituras maior que isso quebra a sequência (ex.: relógio adiantado)
LACUNA_MAX_MIN = 15
# Leitura suspeita (foto lida errado): total menor que o anterior ou subida acima disso
SALTO_MAXIMO_LPM = 300


# --- Demonstrativo de economia ---
# Tarifa média de ÁGUA da Sanepar em 2026: R$ 7,0032/m³ (reajuste IRT 2026 da Agepar, em vigor
# desde 17/05/2026). Não inclui esgoto e a categoria poder público pode ter outro valor:
# é uma estimativa conservadora. Pode ser trocada no .env (TARIFA_RS_M3).
TARIFA_RS_M3 = float(os.getenv("TARIFA_RS_M3") or 7.0032)
# Hipótese: sem o LeakFinder, o vazamento só seria percebido na próxima conta (30 dias)
DIAS_SEM_SISTEMA = float(os.getenv("DIAS_SEM_SISTEMA") or 30)

# Litros por aluno por dia usados no cadastro (base: estudos medidos; ver CLAUDE.md)
LITROS_POR_ALUNO = {"escola": 10, "cmei": 25}

ARQUIVO_PREDIOS = RAIZ / "dados" / "predios.json"


def carregar_predios() -> dict[str, dict]:
    """Cadastro de prédios (dados/predios.json — SIMULADO), indexado por id.
    Unidades sem o campo camera_instalada são tratadas como já tendo câmera."""
    with open(ARQUIVO_PREDIOS, encoding="utf-8") as f:
        predios = {p["id"]: p for p in json.load(f)["predios"]}
    for p in predios.values():
        p.setdefault("camera_instalada", True)
    return predios
