# Olho d'Água

Monitoramento em tempo real da água dos prédios municipais de Londrina: escolas, CMEIs,
secretarias, UBS, esporte, cultura e assistência social.
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

- Publica `hidrometro/<id>/leitura` a cada 2 s para os prédios ativos de `dados/predios.json`.
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

## Detecção e alertas no Telegram

O backend avalia as leituras a cada 2 s (no relógio simulado):

- **Vazamento** — fora do horário de uso, fluxo contínuo > 0 por mais de 30 min (10 com `MODO_DEMO=1`).
- **Consumo excessivo** — no horário de uso, litros da última hora > 2× a média da mesma faixa
  de horário do próprio prédio (janela de 20 min com `MODO_DEMO=1`).
- Causa apresentada como **provável** (pela vazão), 1 alerta ativo por prédio, aviso de
  **resolvido** quando o fluxo zera e cooldown antes de um novo alerta.

A média por faixa de horário vem de um histórico **simulado** de 4 semanas. Gere uma vez:

```bash
.venv\Scripts\python.exe simulador\gerar_historico.py
```

### Configurar o bot do Telegram

1. No Telegram, fale com **@BotFather** → `/newbot` → copie o token.
2. Copie `.env.example` para `.env` e cole o token em `TELEGRAM_TOKEN=`.
3. Suba o backend e mande `/start` para o seu bot: ele responde com o **id do chat**.
   (Para um grupo da manutenção, adicione o bot ao grupo e mande `/start` lá.)
4. Coloque esse número em `TELEGRAM_CHAT_ID=` e reinicie o backend.

Os alertas chegam com os botões **🔒 Fechar registro** / **🔓 Reabrir registro**, que publicam
o comando MQTT com `autorizado_por: telegram:<user_id>`. Só o chat configurado pode usar os
botões. `/status` lista os alertas ativos. Sem token, os alertas aparecem no painel e no terminal.

## Painel da prefeitura

Com simulador e backend rodando, abra **http://127.0.0.1:8000**:
mapa dos prédios (cor = situação, tamanho = vazão), lista lateral, gráfico de vazão
das últimas 6 h simuladas, consumo por hora e botão "Fechar/Reabrir registro".
Atualiza sozinho a cada 2 s.

## Estrutura

```
backend/    API FastAPI, cliente MQTT, banco, detecção, auditor, bot Telegram, laudo
simulador/  simulador dos hidrômetros + injeção de cenários
painel/     painel web (HTML + JS)
dados/      predios.json e faturas.json (simulados)
```
