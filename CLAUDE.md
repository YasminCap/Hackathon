# Olho d'Água — contexto do projeto para o Claude Code

Projeto do SmartCities Hackathon Londrina 2026 (13 a 15/11/2026, SENAI Londrina, tema: Transformação Digital na Gestão Pública).
Responda sempre em português. Entregue arquivos completos, comentados e prontos para rodar.

## O que é
Plataforma para a Prefeitura de Londrina monitorar em tempo real a água dos prédios municipais: escolas (1º ao 5º ano), CMEIs, secretarias/sede, UBS, esporte e cultura (ginásio, centro cultural) e assistência social (CRAS).
Detecta vazamentos, avisa a manutenção pelo Telegram, gera ordem de serviço, audita faturas da Sanepar e mostra a economia em R$.

## Decisões fixas (não mudar sem o time pedir)
- Protótipo **só de software**. O hidrômetro é simulado, no mesmo contrato MQTT que um ESP32 real usaria. Não sugerir hardware.
- Cliente é a prefeitura. Nada de venda B2C ou kit residencial.
- Todo dado, tarifa ou fatura de exemplo deve ser marcado como **simulado**.
- Credenciais só no `.env` (lido com python-dotenv). O `.env` nunca vai para o Git; o `.env.example` vai, sem valores.
- **Escolas Guardiãs fica fora do protótipo** (decisão do time em 13/11): aparece só como feature futura no slide da apresentação.

## Stack
Python 3.11+, paho-mqtt 2.x (`mqtt.CallbackAPIVersion.VERSION2`), FastAPI + uvicorn, SQLite, python-telegram-bot 21+, reportlab (laudo PDF).
Painel: HTML + JS puro, Tailwind via CDN, Chart.js e Leaflet, servido pelo próprio FastAPI, atualizado por polling a cada 2 s.
Broker: HiveMQ Cloud (TLS, porta 8883) no evento; `broker.hivemq.com:1883` só para testes rápidos.

## Estrutura
```
olho-dagua/
├── backend/      main.py (FastAPI), mqtt_cliente.py, db.py, deteccao.py, auditor.py, telegram_bot.py, laudo.py
├── simulador/    simulador.py (+ endpoint ou painel simples para injetar cenários)
├── painel/       index.html, app.js
├── dados/        predios.json, faturas.json (simulados)
├── .env / .env.example / .gitignore / requirements.txt / README.md
```

## Contratos (usar sempre os mesmos)
Leitura — tópico `hidrometro/<id>/leitura`:
```json
{"dispositivo": "escola1", "litros": 12.5, "vazao_lpm": 3.2, "total_litros": 1534.7, "timestamp": "2026-11-14T03:12:00Z"}
```
`litros` = volume desde a última mensagem; `vazao_lpm` = vazão atual; `total_litros` = acumulado.

Comando — tópico `hidrometro/<id>/comando`:
```json
{"acao": "fechar_registro", "autorizado_por": "telegram:<user_id>", "timestamp": "..."}
```
Ações: `fechar_registro`, `abrir_registro`. No protótipo, o simulador zera a vazão do prédio enquanto o registro estiver fechado.

Fatura simulada:
```json
{"predio": "escola1", "matricula": "123456", "mes": "2026-10", "m3_faturado": 48, "m3_medido": 31, "tipo_leitura": "estimada", "categoria": "publica", "valor_rs": 612.40}
```

Cadastro de prédios (`dados/predios.json`): `id`, `nome`, `tipo` (escola|cmei|administrativo|saude|esporte|cultura|assistencia), `regiao`, `lat`, `lon` (em Londrina), `ativo`, `horario_uso` (ex.: "07:00-17:30"), `dias_uso` (`uteis` = seg a sex | `todos`), `media_diaria_litros`.

## Simulador
- 9 a 15 prédios, quantidades parecidas entre os tipos, nomes fictícios ("Escola Municipal Exemplo 1", "UBS Exemplo 1"), consumo realista com perfil por tipo (entrada, merenda, almoço, banhos, limpeza); zero fora do horário e nos dias sem funcionamento.
- Tempo acelerado configurável (padrão: 1 min real = 1 h simulada) e "modo madrugada".
- Cenários injetáveis por prédio: `descarga` (0,5–3 L/min contínuo), `boia` (vazão média contínua), `cano_rompido` (salto para vazão alta), `torneira` (5–10 L/min contínuo).
- Escuta o tópico de comando.

## Detecção
- Fora do horário de uso: fluxo contínuo > 0 por mais de 30 min simulados → vazamento.
- No horário de uso: consumo da hora > 2x a média da mesma faixa do próprio prédio → consumo excessivo.
- `MODO_DEMO=1` no `.env`: limites curtos para a demonstração.
- Classificação apresentada como "provável causa". Cooldown entre alertas; aviso de "resolvido" quando o fluxo zera.
- Cada alerta gera ordem de serviço (aberta, em atendimento, resolvida).

## Auditor de contas
- Estimada acima do medido: `tipo_leitura == "estimada"` e `m3_faturado > m3_medido * 1.10`.
- Faturado muito acima do medido (qualquer leitura): tolerância 20%.
- Categoria errada; imóvel inativo pagando; duas matrículas no mesmo prédio e mês.
- Valor a mais (simplificação explícita): `valor_rs / m3_faturado * (m3_faturado - m3_medido)`.

## Ordem de construção
1. Estrutura, venv, requirements, `.env.example`, teste MQTT, primeiro commit.
2. `dados/predios.json` + simulador publicando.
3. Backend recebendo e salvando no SQLite + API.
4. Painel mínimo (mapa + gráfico). **= checkpoint eliminatório de sábado 14/11 à tarde.**
5. Detecção + alerta Telegram com botões "Fechar registro" / "Reabrir registro".
6. Ordens de serviço + contador de R$ economizados.
7. Auditor de contas + laudo PDF.

(Escolas Guardiãs saiu do protótipo — só slide de feature futura.)

Nunca cortar: simulador → detecção → alerta no celular com "Fechar registro" → painel atualizando.
Commits pequenos e frequentes (provam que o trabalho foi feito durante o evento).
