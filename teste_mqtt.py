"""
teste_mqtt.py — teste de ida e volta no broker MQTT público (broker.hivemq.com:1883).

O que faz:
  1. Conecta no broker público (sem TLS, sem senha — só para teste rápido).
  2. Assina o tópico de leitura de um dispositivo de teste.
  3. Publica UMA leitura SIMULADA no mesmo contrato que o ESP32/simulador usará.
  4. Espera a mensagem voltar e confere o conteúdo.

Saída: código 0 se a mensagem fez a ida e volta, 1 se falhou.

Observação: o broker é público; usamos um sufixo aleatório no id do dispositivo
para não colidir com outros grupos testando ao mesmo tempo. Nenhum dado real é enviado.
"""

import json
import sys
import threading
import uuid
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

# Garante acentos e emoji no terminal do Windows (cp1252 por padrão)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BROKER = "broker.hivemq.com"
PORTA = 1883
TIMEOUT_S = 15

# Dispositivo de teste com sufixo aleatório (evita colisão no broker público)
DISPOSITIVO = f"teste-olhodagua-{uuid.uuid4().hex[:8]}"
TOPICO = f"hidrometro/{DISPOSITIVO}/leitura"

# Leitura SIMULADA no contrato oficial do projeto (ver CLAUDE.md)
LEITURA = {
    "dispositivo": DISPOSITIVO,
    "litros": 12.5,
    "vazao_lpm": 3.2,
    "total_litros": 1534.7,
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "simulado": True,
}

recebida = threading.Event()
resultado = {}


def ao_conectar(client, userdata, flags, reason_code, properties):
    """Callback de conexão (API VERSION2)."""
    if reason_code.is_failure:
        print(f"[ERRO] Falha ao conectar: {reason_code}")
        return
    print(f"[OK] Conectado em {BROKER}:{PORTA}")
    client.subscribe(TOPICO, qos=1)


def ao_assinar(client, userdata, mid, reason_codes, properties):
    """Assinatura confirmada → publica a leitura de teste."""
    print(f"[OK] Assinado em {TOPICO}")
    info = client.publish(TOPICO, json.dumps(LEITURA), qos=1)
    print(f"[..] Publicando leitura simulada (mid={info.mid})")


def ao_receber(client, userdata, msg):
    """Mensagem chegou → valida e libera o programa principal."""
    try:
        resultado["payload"] = json.loads(msg.payload.decode("utf-8"))
        resultado["topico"] = msg.topic
    except (UnicodeDecodeError, json.JSONDecodeError) as erro:
        resultado["erro"] = str(erro)
    recebida.set()


def main() -> int:
    cliente = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"olhodagua-teste-{uuid.uuid4().hex[:6]}",
    )
    cliente.on_connect = ao_conectar
    cliente.on_subscribe = ao_assinar
    cliente.on_message = ao_receber

    print(f"[..] Conectando em {BROKER}:{PORTA} ...")
    try:
        cliente.connect(BROKER, PORTA, keepalive=30)
    except OSError as erro:
        print(f"[ERRO] Não foi possível conectar: {erro}")
        return 1

    cliente.loop_start()
    chegou = recebida.wait(TIMEOUT_S)
    cliente.loop_stop()
    cliente.disconnect()

    if not chegou:
        print(f"[ERRO] Nenhuma mensagem recebida em {TIMEOUT_S} s.")
        return 1
    if "erro" in resultado:
        print(f"[ERRO] Payload inválido: {resultado['erro']}")
        return 1

    print(f"[OK] Mensagem recebida em {resultado['topico']}:")
    print(json.dumps(resultado["payload"], indent=2, ensure_ascii=False))

    if resultado["payload"] != LEITURA:
        print("[ERRO] O conteúdo recebido difere do enviado.")
        return 1

    print("\n✅ Teste MQTT OK — ida e volta funcionando.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
