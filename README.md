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

## Estrutura

```
backend/    API FastAPI, cliente MQTT, banco, detecção, auditor, bot Telegram, laudo
simulador/  simulador dos hidrômetros + injeção de cenários
painel/     painel web (HTML + JS)
dados/      escolas.json e faturas.json (simulados)
```
