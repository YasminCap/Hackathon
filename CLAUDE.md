# Olho d'Água — contexto do projeto para o Claude Code

Projeto do SmartCities Hackathon Londrina 2026 (13 a 15/11/2026, SENAI Londrina, tema: Transformação Digital na Gestão Pública).
Responda sempre em português. Entregue arquivos completos, comentados e prontos para rodar.

## O que é
Plataforma para a Prefeitura de Londrina monitorar em tempo real a água dos prédios municipais.
**O protótipo é focado em escolas municipais (1º ao 5º ano) e CMEIs** (decisão do time em 14/11); a visão é municipal e os demais prédios (secretarias, UBS, esporte, cultura, CRAS) ficam como fase 2, só no slide.
Detecta vazamentos, avisa a manutenção pelo Telegram, gera ordem de serviço e mostra a economia em R$.

## Decisões fixas (não mudar sem o time pedir)
- Protótipo **só de software**. A leitura é simulada, no mesmo contrato MQTT que o dispositivo real usaria. Não sugerir outro hardware.
- **Hardware da versão real (decisão do time em 14/11): ESP32-CAM fotografando o mostrador do hidrômetro que já existe no prédio, a cada 30 min.** A foto vira número (reconhecimento dos dígitos); não mexe no encanamento. Fechar a água a distância exigiria também uma válvula elétrica.
- Cliente é a prefeitura. Nada de venda B2C ou kit residencial.
- Todo dado, tarifa ou fatura de exemplo deve ser marcado como **simulado**.
- Credenciais só no `.env` (lido com python-dotenv). O `.env` nunca vai para o Git; o `.env.example` vai, sem valores.
- **Fora do protótipo, só como ideia no slide** (decisões do time em 13/11): ver a seção "Ideias futuras (só slide)". Não implementar.

## Stack
Python 3.11+, paho-mqtt 2.x (`mqtt.CallbackAPIVersion.VERSION2`), FastAPI + uvicorn, SQLite, python-telegram-bot 21+.
Painel: HTML + JS puro, Tailwind via CDN, Chart.js e Leaflet, servido pelo próprio FastAPI, atualizado por polling a cada 2 s.
Broker: HiveMQ Cloud (TLS, porta 8883) no evento; `broker.hivemq.com:1883` só para testes rápidos.

## Estrutura
```
olho-dagua/
├── backend/      main.py (FastAPI), mqtt_cliente.py, db.py, deteccao.py, telegram_bot.py
├── simulador/    simulador.py (+ endpoint ou painel simples para injetar cenários)
├── painel/       index.html, app.js
├── dados/        predios.json (simulado)
├── .env / .env.example / .gitignore / requirements.txt / README.md
```

## Contratos (usar sempre os mesmos)
Leitura — tópico `hidrometro/<id>/leitura`:
```json
{"dispositivo": "escola1", "litros": 12.5, "vazao_lpm": 3.2, "total_litros": 1534.7, "timestamp": "2026-11-14T03:12:00Z"}
```
Uma leitura a cada 30 min (uma foto). `total_litros` = número lido no mostrador; `litros` = diferença para a leitura anterior; `vazao_lpm` = média da meia hora (`litros / 30`).

Comando — tópico `hidrometro/<id>/comando`:
```json
{"acao": "fechar_registro", "autorizado_por": "telegram:<user_id>", "timestamp": "..."}
```
Ações: `fechar_registro`, `abrir_registro`. No protótipo, o simulador zera a vazão do prédio enquanto o registro estiver fechado.

Cadastro de prédios (`dados/predios.json`): `id`, `nome`, `tipo` (escola|cmei no protótipo; administrativo|saude|esporte|cultura|assistencia na fase 2), `regiao`, `lat`, `lon` (em Londrina), `ativo`, `horario_uso` (ex.: "07:00-17:30"), `dias_uso` (`uteis` = seg a sex | `todos`), `media_diaria_litros`.

## Simulador
- Só escolas e CMEIs: 6 escolas (1 desativada) e 4 CMEIs, nomes fictícios ("Escola Municipal Exemplo 1", "CMEI Exemplo 1"), consumo realista com perfil por tipo (entrada, intervalo, merenda, banho, limpeza); zero fora do horário e no fim de semana. O simulador também conhece perfis de outros tipos de prédio (para a fase 2), mas o cadastro do protótipo não os usa.
- Publica uma leitura a cada 30 min simulados, como a ESP32-CAM (internamente o consumo é calculado minuto a minuto).
- Tempo acelerado configurável (padrão: 1 min real = 1 h simulada → uma leitura a cada 30 s reais) e "modo madrugada".
- Cenários injetáveis por prédio: `descarga` (0,5–3 L/min contínuo), `boia` (vazão média contínua), `cano_rompido` (salto para vazão alta), `torneira` (5–10 L/min contínuo).
- Escuta o tópico de comando.

## Detecção
- Fora do horário de uso: consumo em leituras seguidas fora do horário (3 leituras ≈ 1 h; 2 leituras com `MODO_DEMO=1`) → vazamento.
- No horário de uso: consumo da última hora (2 leituras) > 2x a média da mesma faixa do próprio prédio → consumo excessivo.
- Leitura suspeita (total diminui ou salto impossível) é descartada: a foto pode ter sido lida errado.
- `MODO_DEMO=1` no `.env`: limites curtos para a demonstração.
- Classificação apresentada como "provável causa". Cooldown entre alertas; aviso de "resolvido" quando o fluxo zera.
- Cada alerta gera ordem de serviço (aberta, em atendimento, resolvida).

## Ordem de construção
1. Estrutura, venv, requirements, `.env.example`, teste MQTT, primeiro commit.
2. `dados/predios.json` + simulador publicando.
3. Backend recebendo e salvando no SQLite + API.
4. Painel mínimo (mapa + gráfico). **= checkpoint eliminatório de sábado 14/11 à tarde.**
5. Detecção + alerta Telegram com botões "Fechar registro" / "Reabrir registro".
6. Ordens de serviço + contador de R$ economizados.

## Ideias futuras (só slide — não implementar no protótipo)
- **Fase 2 — todos os prédios municipais:** secretarias/sede, UBS, ginásios, centros culturais e CRAS no mesmo painel.
- **Escolas Guardiãs:** ranking de redução de consumo de cada prédio contra a própria média.
- **Auditor de contas da Sanepar + laudo PDF:** comparar o m³ faturado com o m³ medido pelo nosso hidrômetro e apontar
  leitura estimada acima do medido (>10%), faturado muito acima do medido (>20%), categoria errada, prédio inativo pagando
  e matrícula duplicada; valor a mais estimado por `valor_rs / m3_faturado * (m3_faturado - m3_medido)` (simplificação:
  a tarifa real é por faixas). O laudo serviria para contestar a cobrança.
- **UPA e unidades 24h:** precisam de outra regra de vazamento (vazão mínima da madrugada), pois nunca fecham.
- **IA com dados reais:** com o histórico real dos hidrômetros, evoluir a detecção para modelos de machine learning.
- **ESP32-CAM real nos prédios**, fotografando o hidrômetro, no mesmo contrato MQTT do simulador; válvula elétrica para fechar a água a distância.

Nunca cortar: simulador → detecção → alerta no celular com "Fechar registro" → painel atualizando.
Commits pequenos e frequentes (provam que o trabalho foi feito durante o evento).
