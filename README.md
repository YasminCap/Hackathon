# Olho d'Água

Monitoramento em tempo real da água das escolas municipais e CMEIs de Londrina.
Projeto do SmartCities Hackathon Londrina 2026 — tema: Transformação Digital na Gestão Pública.

> Protótipo de software: o hidrômetro é **simulado**, no mesmo contrato MQTT que um ESP32 real usaria.
> Todos os dados, tarifas e faturas de exemplo são **simulados**.

## Como rodar (Windows)

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # e preencha os valores
python teste_mqtt.py     # teste de ida e volta no broker público
```

## Simulador de hidrômetros

```bash
.venv\Scripts\python.exe simulador\simulador.py              # 1 min real = 1 h simulada
.venv\Scripts\python.exe simulador\simulador.py --madrugada  # começa às 01:00 de um dia útil
```

- Publica `hidrometro/<id>/leitura` a cada 2 s para os prédios ativos de `dados/escolas.json`.
- Obedece `hidrometro/<id>/comando` (`fechar_registro` / `abrir_registro`).
- Painel de controle em http://127.0.0.1:8001: injetar vazamento (descarga, boia, torneira,
  cano rompido), consertar, abrir/fechar registro, ir para a madrugada, adiantar o relógio.
- Sem `.env`, usa o broker público `broker.hivemq.com:1883`.

## Backend (API + gravação no SQLite)

Em outro terminal, com o simulador rodando:

```bash
.venv\Scripts\python.exe -m backend.main
```

- Recebe `hidrometro/+/leitura`, valida (só prédios do cadastro, contrato oficial) e grava em `olhodagua.db`.
- API em http://127.0.0.1:8000 — documentação interativa em http://127.0.0.1:8000/docs.
- `POST /api/predios/<id>/comando` com `{"acao": "fechar_registro"}` fecha o registro pelo MQTT.

## Estrutura

```
backend/    API FastAPI, cliente MQTT, banco, detecção, auditor, bot Telegram, laudo
simulador/  simulador dos hidrômetros + injeção de cenários
painel/     painel web (HTML + JS)
dados/      escolas.json e faturas.json (simulados)
```
