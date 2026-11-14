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
> (veja o [GUIA_DOIS_COMPUTADORES.md](GUIA_DOIS_COMPUTADORES.md)).
> Se aparecer uma tela antiga, aperte **Ctrl+Shift+R**.

**Outros links do projeto**

- Código no GitHub: <https://github.com/YasminCap/Hackathon>
- Apresentação técnica (slides): <https://claude.ai/artifact/TjFKiYPJRyHW2vbP9EgxL6>
  — privada; só abre para quem a dona compartilhar pelo menu *Share* da apresentação.
- Material de apoio ao pitch: [materiais-pitch/BENEFICIOS_SOCIAIS.md](materiais-pitch/BENEFICIOS_SOCIAIS.md)

## Como rodar (Windows)

```bash
git clone https://github.com/YasminCap/Hackathon.git leakfinder
cd leakfinder
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # e preencha os valores (opcional)
python teste_mqtt.py     # teste de ida e volta no broker público
```

> **Simulador num notebook e painel do gestor em outro?** Veja o
> [GUIA_DOIS_COMPUTADORES.md](GUIA_DOIS_COMPUTADORES.md).

## Simulador de hidrômetros

```bash
.venv\Scripts\python.exe simulador\simulador.py              # 1 min real = 1 h simulada
.venv\Scripts\python.exe simulador\simulador.py --madrugada  # começa às 01:00 de um dia útil
```

- Faz o papel da ESP32-CAM: publica `hidrometro/<id>/leitura` **a cada 30 min simulados** (30 s reais)
  para as unidades ativas de `dados/predios.json`, com o total do hidrômetro e o consumo desde a foto anterior.
- Guarda o total de cada hidrômetro em `simulador/totais_hidrometros.json` (um hidrômetro real não volta a zero).
- Controle da demonstração em http://127.0.0.1:8001: escolher a unidade e **iniciar vazamento**
  (o tipo é sorteado — quem descobre a provável causa é o LeakFinder), consertar, ir para a madrugada.
- Sem `.env`, usa o broker público `broker.hivemq.com:1883`.

## Backend (API + gravação no SQLite)

Em outro terminal, com o simulador rodando:

```bash
.venv\Scripts\python.exe -m backend.main
```

- Recebe `hidrometro/+/leitura`, valida (só unidades do cadastro, contrato oficial) e grava em `olhodagua.db`.
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

**Campo de operação:** cada alerta tem a caixa *Operação* para o gestor registrar o andamento —
**Pendente** → **Informado à manutenção** → **Consertado**. O cartão *Aguardando ação* mostra
quantas ocorrências ainda não foram informadas.

## Estrutura

```
backend/         API FastAPI, cliente MQTT, banco, detecção, avisos no terminal
simulador/       simulador dos hidrômetros + controle da demonstração
painel/          painel do gestor (HTML + JS)
dados/           predios.json (simulado)
materiais-pitch/ material de apoio para a apresentação
```
