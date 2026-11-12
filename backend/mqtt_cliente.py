"""
mqtt_cliente.py — ponte entre o broker MQTT e o banco.

  • Assina  hidrometro/+/leitura, valida cada mensagem e grava no SQLite.
  • Publica hidrometro/<id>/comando (fechar_registro / abrir_registro) e registra no banco.

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
                     MQTT_USUARIO)

ACOES_VALIDAS = ("fechar_registro", "abrir_registro")


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
            db.inserir_leitura(leitura)
            with self._trava:
                self.recebidas += 1
        except LeituraInvalida as erro:
            with self._trava:
                self.rejeitadas += 1
                primeira_vez = self.rejeitadas <= 5
            if primeira_vez:  # evita inundar o terminal se alguém spammar o broker
                print(f"[MQTT] Leitura rejeitada ({msg.topic}): {erro}")
        except Exception as erro:  # erro de banco etc. não pode derrubar a thread do MQTT
            print(f"[MQTT] Erro ao gravar leitura de {msg.topic}: {erro!r}")

    # ------------------------------------------------------------------ comandos
    def enviar_comando(self, dispositivo: str, acao: str, autorizado_por: str) -> dict:
        """Publica o comando no contrato oficial e registra no banco."""
        if acao not in ACOES_VALIDAS:
            raise ValueError(f"ação inválida: {acao}")
        if not self.conectado:
            raise ConnectionError("MQTT desconectado — comando não enviado")
        comando = {
            "acao": acao,
            "autorizado_por": autorizado_por,
            "timestamp": db.agora_utc(),
        }
        info = self.cliente.publish(f"hidrometro/{dispositivo}/comando", json.dumps(comando), qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"falha ao publicar comando (rc={info.rc})")
        comando["id"] = db.registrar_comando(dispositivo, acao, autorizado_por, comando["timestamp"])
        print(f"[CMD] {dispositivo}: {acao} (autorizado por {autorizado_por})")
        return comando
