# LeakFinder Londrina

Monitoramento da água das **escolas municipais e CMEIs** de Londrina, para achar vazamentos
cedo (protótipo; a visão é estender a todos os prédios municipais).
Projeto do SmartCities Hackathon Londrina 2026 — tema: Transformação Digital na Gestão Pública.

> Protótipo de software: a leitura é **simulada**, no mesmo contrato MQTT que a ESP32-CAM real usaria
> (uma foto do mostrador do hidrômetro a cada 30 min, com bateria e painel solar — sem tomada).
> Todos os dados e tarifas de exemplo são **simulados**.

## Acesso às plataformas

Com o simulador e o backend rodando (ver [Como rodar](#como-rodar-windows)), abra no navegador:

| Plataforma | Endereço | Para quê |
|---|---|---|
| 💧 **Painel do gestor** | <http://127.0.0.1:8000> | Mapa, alertas com o campo de operação, gráficos de consumo |
| 🎛️ **Controle da demonstração** | <http://127.0.0.1:8001> | Escolher a unidade e iniciar um vazamento (tipo sorteado) |
| 📄 **Documentação da API** | <http://127.0.0.1:8000/docs> | Rotas do backend, para testar direto no navegador |

> Os endereços `127.0.0.1` só funcionam **no computador que está rodando os programas**.
> Se o simulador estiver num notebook e o painel em outro, cada um abre o seu endereço
> (veja o [guia de dois computadores](documentos/GUIA_DOIS_COMPUTADORES.md)).
> Se aparecer uma tela antiga, aperte **Ctrl+Shift+R**.

**Outros links do projeto**

- Código no GitHub: <https://github.com/YasminCap/Hackathon>
- Apresentação técnica (slides): <https://claude.ai/artifact/TjFKiYPJRyHW2vbP9EgxL6>
  — privada; só abre para quem a dona compartilhar pelo menu *Share* da apresentação.
- **Documentação completa na pasta [documentos/](documentos/README.md):** decisões do projeto e perguntas da banca, benefícios sociais, BMC e guia de dois computadores.

## Como rodar (Windows)

```bash
git clone https://github.com/YasminCap/Hackathon.git leakfinder
cd leakfinder
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # e preencha os valores (opcional)
python testes/teste_mqtt.py   # teste de ida e volta no broker público
```

> **Simulador num notebook e painel do gestor em outro?** Veja o
> [guia de dois computadores](documentos/GUIA_DOIS_COMPUTADORES.md).

## Simulador de hidrômetros

```bash
.venv\Scripts\python.exe simulador\simulador.py              # 1 min real = 1 h simulada
.venv\Scripts\python.exe simulador\simulador.py --madrugada  # começa às 01:00 de um dia útil
```

- Faz o papel da ESP32-CAM: publica `hidrometro/<id>/leitura` **a cada 30 min simulados** (30 s reais)
  para as unidades ativas de `dados/predios.json`, com o total do hidrômetro e o consumo desde a foto anterior.
- Guarda o total de cada hidrômetro em `dados/totais_hidrometros.json` (um hidrômetro real não volta a zero).
- Controle da demonstração em http://127.0.0.1:8001: escolher a unidade e **iniciar vazamento**
  (o tipo é sorteado — quem descobre a provável causa é o LeakFinder), consertar, ir para a madrugada.
- Sem `.env`, usa o broker público `broker.hivemq.com:1883`.

## Backend (API + gravação no SQLite)

Em outro terminal, com o simulador rodando:

```bash
.venv\Scripts\python.exe -m backend.main
```

- Recebe `hidrometro/+/leitura`, valida (só unidades do cadastro, contrato oficial) e grava em `dados/olhodagua.db`.
- API em http://127.0.0.1:8000 — documentação interativa em http://127.0.0.1:8000/docs.
- `POST /api/alertas/<id>/operacao` com `{"operacao": "informado"}` preenche o campo de operação.

## Detecção de vazamentos

O backend avalia cada nova leitura (foto) assim que ela chega, no relógio simulado:

- **Vazamento** — fora do horário de uso, consumo em 3 fotos seguidas (2 com `MODO_DEMO=1`).
- **Consumo excessivo** — no horário de uso, litros da última hora > 2× a média da mesma faixa
  de horário da própria unidade (2 fotos).
- **Leitura suspeita** — total que diminui ou dá um salto impossível (foto lida errado) é descartado.
- Causa apresentada como **provável** (pela vazão), 1 alerta ativo por unidade, aviso de
  **resolvido** quando o consumo zera e cooldown antes de um novo alerta.
- Os alertas aparecem no painel do gestor e no terminal do backend.

A média por faixa de horário vem de um histórico **simulado** de 4 semanas. Gere uma vez:

```bash
.venv\Scripts\python.exe simulador\gerar_historico.py
```

## Painel do gestor

Com simulador e backend rodando, abra **http://127.0.0.1:8000**:
mapa das unidades (cor = situação, tamanho = consumo), alertas, lista de unidades, gráfico do
consumo médio de cada foto (últimas 24 h) e consumo por hora. Atualiza sozinho a cada 2 s.

O painel tem três abas:

- **Visão geral** — unidades online, alertas, *Aguardando ação*, **demonstrativo de economia**
  (água que não foi desperdiçada e valor poupado na conta — simulado), mapa, alertas em andamento e o
  detalhe de cada unidade com o **histórico semanal** e a **média semanal** de acompanhamento.
- **Cadastrar unidade** — inclui uma escola ou CMEI (nome, tipo, região, horário e **endereço**; o botão
  *Localizar no mapa* encontra o ponto pelo OpenStreetMap). Não se informa número de alunos nem consumo:
  a média é **medida pelo consumo semanal registrado**. A unidade aparece como **aguardando câmera** até a
  ESP32-CAM ser instalada.
- **Finalizados** — alertas cuja operação foi marcada como **Consertado**, com a economia de cada um.

**Campo de operação:** cada alerta tem a caixa *Operação* — **Pendente** → **Informado à manutenção**
→ **Consertado**. Ao marcar *Consertado*, o alerta vai para a aba Finalizados.

**Como a economia é calculada:** sem o LeakFinder, o vazamento duraria 30 dias (até a próxima conta);
água não desperdiçada = vazão × 30 dias − o que vazou até o conserto; valor = m³ × R$ 7,00
(tarifa média de água da Sanepar 2026, sem esgoto). Ajustável no `.env` (`DIAS_SEM_SISTEMA`, `TARIFA_RS_M3`).

## Estrutura

```
backend/         API FastAPI, cliente MQTT, banco, detecção, avisos no terminal
simulador/       simulador dos hidrômetros + controle da demonstração
painel/          painel do gestor (HTML + JS)
dados/           predios.json (simulado) + arquivos gerados ao rodar (banco olhodagua.db, totais dos hidrômetros)
testes/          teste_mqtt.py (confere se a conexão com o broker funciona)
documentos/      decisões, perguntas da banca, benefícios sociais, BMC, guia de dois computadores
```
