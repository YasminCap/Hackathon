"""
mqtt_cliente.py — ponte entre o broker MQTT e o banco.

  • Assina  hidrometro/+/leitura, valida cada mensagem e grava no SQLite.

Validação importa: no broker público qualquer um pode publicar nesses tópicos.
Só aceitamos prédios do cadastro e mensagens no contrato oficial.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from . import db
from .config import (FUSO_LOCAL, MQTT_BROKER, MQTT_PORTA, MQTT_SENHA, MQTT_TLS,
                     MQTT_USUARIO, SALTO_MAXIMO_LPM)


def conferir_com_anterior(leitura: dict, anterior: dict | None) -> None:
    """A leitura vem de uma FOTO do hidrômetro: a câmera pode ler um dígito errado.
    O mostrador só anda para a frente e não dá saltos impossíveis; se der, a leitura
    é descartada (a próxima foto corrige, porque traz o total certo)."""
    if not anterior:
        return
    if leitura["total_litros"] < anterior["total_litros"] - 0.5:
        raise LeituraInvalida(
            f"leitura suspeita: total diminuiu ({anterior['total_litros']:.1f} → "
            f"{leitura['total_litros']:.1f} L) — provável erro na leitura da foto")
    t_ant = datetime.strptime(anterior["ts_local"], "%Y-%m-%d %H:%M:%S")
    t_nova = datetime.strptime(leitura["ts_local"], "%Y-%m-%d %H:%M:%S")
    minutos = (t_nova - t_ant).total_seconds() / 60
    salto = leitura["total_litros"] - anterior["total_litros"]
    if minutos > 0 and salto / minutos > SALTO_MAXIMO_LPM:
        raise LeituraInvalida(
            f"leitura suspeita: salto de {salto:.0f} L em {minutos:.0f} min — "
            "provável erro na leitura da foto")



class LeituraInvalida(ValueError):
    pass


def validar_leitura(topico: str, payload: bytes, ids_validos: set[str]) -> dict:
    """Confere o contrato da leitura e devolve um dict pronto para o banco."""
    partes = topico.split("/")
    if len(partes) != 3:
        raise LeituraInvalida(f"tópico inesperado: {topico}")
    id_topico = partes[1]
    if id_topico not in ids_validos:
        raise LeituraInvalida(f"prédio fora do cadastro ou inativo: {id_topico}")

    try:
        d = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        raise LeituraInvalida(f"JSON inválido: {erro}") from erro
    if not isinstance(d, dict):
        raise LeituraInvalida("payload não é um objeto JSON")

    if d.get("dispositivo") != id_topico:
        raise LeituraInvalida(f"dispositivo '{d.get('dispositivo')}' difere do tópico '{id_topico}'")

    numeros = {}
    for campo in ("litros", "vazao_lpm", "total_litros"):
        valor = d.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0:
            raise LeituraInvalida(f"campo '{campo}' ausente ou inválido: {valor!r}")
        numeros[campo] = float(valor)

    try:
        instante = datetime.fromisoformat(str(d["timestamp"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as erro:
        raise LeituraInvalida(f"timestamp inválido: {d.get('timestamp')!r}") from erro
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)  # contrato: UTC

    return {
        "dispositivo": id_topico,
        "timestamp": instante.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ts_local": instante.astimezone(FUSO_LOCAL).strftime("%Y-%m-%d %H:%M:%S"),
        "simulado": bool(d.get("simulado", True)),
        **numeros,
    }


class ClienteMQTT:
    def __init__(self, ids_validos: set[str]):
        self.ids_validos = ids_validos
        self.recebidas = 0
        self.rejeitadas = 0
        self._trava = threading.Lock()
        self.cliente = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"olhodagua-backend-{uuid.uuid4().hex[:6]}",
        )
        if MQTT_USUARIO:
            self.cliente.username_pw_set(MQTT_USUARIO, MQTT_SENHA)
        if MQTT_TLS:
            self.cliente.tls_set()
        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_disconnect = self._ao_desconectar
        self.cliente.on_message = self._ao_receber

    # ------------------------------------------------------------- ciclo de vida
    def iniciar(self) -> None:
        print(f"[MQTT] Conectando em {MQTT_BROKER}:{MQTT_PORTA} (TLS={'sim' if MQTT_TLS else 'não'})")
        self.cliente.connect_async(MQTT_BROKER, MQTT_PORTA, keepalive=30)
        self.cliente.loop_start()  # thread própria; reconecta sozinho

    def parar(self) -> None:
        self.cliente.loop_stop()
        self.cliente.disconnect()

    @property
    def conectado(self) -> bool:
        return self.cliente.is_connected()

    # ----------------------------------------------------------------- callbacks
    def _ao_conectar(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[MQTT] Conexão recusada: {reason_code}")
            return
        print("[MQTT] Conectado — assinando hidrometro/+/leitura")
        client.subscribe("hidrometro/+/leitura", qos=0)

    def _ao_desconectar(self, client, userdata, flags, reason_code, properties):
        print(f"[MQTT] Desconectado ({reason_code}); reconectando...")

    def _ao_receber(self, client, userdata, msg):
        try:
            leitura = validar_leitura(msg.topic, msg.payload, self.ids_validos)
            conferir_com_anterior(leitura, db.ultima_leitura(leitura["dispositivo"]))
            db.inserir_leitura(leitura)
            with self._trava:
                self.recebidas += 1
        except LeituraInvalida as erro:
            with self._trava:
                self.rejeitadas += 1
                primeira_vez = self.rejeitadas <= 5
            # leitura suspeita (foto lida errado) sempre aparece; lixo de terceiros só as 5 primeiras
            if primeira_vez or "suspeita" in str(erro):
                print(f"[MQTT] Leitura rejeitada ({msg.topic}): {erro}")
        except Exception as erro:  # erro de banco etc. não pode derrubar a thread do MQTT
            print(f"[MQTT] Erro ao gravar leitura de {msg.topic}: {erro!r}")
