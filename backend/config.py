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

# Prédio é considerado "online" se mandou leitura nos últimos N segundos REAIS
SEGUNDOS_ONLINE = 10


def carregar_predios() -> dict[str, dict]:
    """Cadastro de prédios (dados/escolas.json — SIMULADO), indexado por id."""
    with open(RAIZ / "dados" / "escolas.json", encoding="utf-8") as f:
        return {p["id"]: p for p in json.load(f)["predios"]}
