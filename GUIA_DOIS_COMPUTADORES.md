# Guia: simulador num notebook, painel do gestor em outro

Um integrante cuida do **simulador** (provoca os vazamentos) e outro usa o **painel do gestor**,
cada um no seu notebook. Os dois **não precisam estar na mesma rede**: as mensagens passam por
um "correio" na internet (o broker MQTT), como seria na vida real.

```
 Notebook 1 — SIMULADOR                  internet                 Notebook 2 — GESTOR
 provoca o vazamento  ──────►  correio MQTT (HiveMQ)  ──────►  vê o alerta no painel
 a água para          ◄──────                          ◄──────  clica "Fechar registro"
```

> Todos os dados são **simulados**.

---

## Parte 1 — Preparar o notebook do colega (uma vez só, antes do evento)

### 1. Instalar o Python e o Git

1. Baixe o **Python 3.12** em <https://www.python.org/downloads/>.
   Na instalação, **marque a caixa "Add python.exe to PATH"** antes de clicar em *Install Now*.
2. Baixe o **Git** em <https://git-scm.com/download/win> e instale com as opções padrão
   (é só ir clicando em *Next*).

### 2. Baixar o projeto do GitHub

O projeto está em **<https://github.com/YasminCap/Hackathon>**.
Se o repositório for **privado**, a dona precisa antes convidar o colega em
*Settings → Collaborators* no GitHub, e ele precisa aceitar o convite que chega por e-mail.

Abra o **Prompt de Comando** (ou o terminal do VS Code) e rode, um de cada vez:

```bash
cd C:\
```
```bash
git clone https://github.com/YasminCap/Hackathon.git olho-dagua
```

Isso cria a pasta `C:\olho-dagua` com o projeto. (Se pedir login do GitHub, entre com a conta
de quem foi convidado.) O `.env` com senhas **não** vem junto — de propósito.

### 3. Instalar as dependências

No VS Code: **Arquivo → Abrir pasta** → escolha `C:\olho-dagua` → **Terminal → Novo terminal**.
Rode, um de cada vez:

```bash
py -3.12 -m venv .venv
```
```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> Se aparecer "py não é reconhecido", troque o primeiro comando por `python -m venv .venv`.

### 4. Testar a internet / correio

```bash
.venv\Scripts\python.exe teste_mqtt.py
```

Tem que terminar com **✅ Teste MQTT OK**. Faça esse teste **nos dois notebooks**.

### 5. Arquivo `.env` (só se vocês configurarem o HiveMQ Cloud)

Sem `.env`, os dois notebooks usam automaticamente o mesmo correio público de teste — não precisa
fazer nada. Se o grupo configurar o **HiveMQ Cloud** (privado), os **dois notebooks precisam do
mesmo `.env`**. Passe esse arquivo em particular (nunca num grupo aberto e nunca pelo Git).

---

## Parte 2 — No dia da apresentação

### Primeiro: pegar a versão mais nova (nos dois notebooks)

O projeto continua mudando durante o evento. Antes de ligar qualquer coisa, na pasta do projeto:

```bash
git pull
```

> Se alguma dependência nova tiver entrado, rode de novo
> `.venv\Scripts\python.exe -m pip install -r requirements.txt`.

### Notebook 1 — quem cuida do SIMULADOR

```bash
.venv\Scripts\python.exe simulador\simulador.py
```

Abra no navegador: **http://127.0.0.1:8001**
Confira no topo da tela: **🟢 enviando dados**.

### Notebook 2 — quem usa o PAINEL DO GESTOR

Só na **primeira vez** nesse notebook (cria o histórico simulado de consumo):

```bash
.venv\Scripts\python.exe simulador\gerar_historico.py
```

Depois, sempre:

```bash
.venv\Scripts\python.exe -m backend.main
```

Abra no navegador: **http://127.0.0.1:8000**
Confira: **"Unidades online: 12 de 12"** — isso prova que as leituras do notebook 1 estão chegando.

---

## Parte 3 — Ensaio a dois (faça antes de apresentar)

| Passo | Quem | O que fazer | O que deve acontecer |
|---|---|---|---|
| 1 | Simulador | Clicar **▶ Simular vazamento** | A Escola Municipal Exemplo 1 fica "Torneira aberta" |
| 2 | Gestor | Esperar **1 a 2 minutos** (a “câmera” fotografa a cada 30 s reais) | Aparece **🚨 Vazamento provável** e o ponto vermelho no mapa |
| 3 | Gestor | Clicar **🔒 Fechar registro** no alerta | Em até ~1 minuto (próximas fotos) o alerta vira **✅ Resolvido** |
| 4 | Simulador | Olhar a lista "Como estão os prédios agora" | A Escola 1 aparece como **Água cortada** |
| 5 | Simulador | Clicar **🔧 Consertar tudo e recomeçar** | Tudo volta ao normal para a próxima rodada |

---

## Regras importantes

- **Só UM simulador ligado no grupo inteiro.** Dois simuladores ao mesmo tempo mandam leituras
  em dobro e os gráficos ficam malucos.
- **Só UM painel do gestor (backend)** ligado. Outras pessoas podem olhar a tela de quem está com ele.
- **Quem manda no relógio é o simulador.** O horário que aparece no painel vem dele.
- Para desligar qualquer um: clique no terminal e aperte **Ctrl+C**.

---

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| Simulador mostra **🔴 sem conexão (MQTT)** | Confira a internet e rode `teste_mqtt.py`. Wi-Fi de evento às vezes bloqueia esse tipo de conexão: use o **roteador do celular** de alguém. |
| Painel mostra **0 de 12 unidades online** | O simulador está desligado ou sem internet no notebook 1. Se usam `.env`, confira se é **o mesmo** nos dois. |
| O alerta não aparece | Tem que ser **madrugada na simulação** (o botão "Simular vazamento" já cuida disso) e esperar 1 a 2 minutos. |
| O painel mostra a tela antiga | Aperte **Ctrl+Shift+R** no navegador. |
| "py" ou "python" não é reconhecido | Reinstale o Python marcando **"Add python.exe to PATH"**. |
| "git" não é reconhecido | Instale o Git (<https://git-scm.com/download/win>) e abra um terminal novo. |
| `git clone` diz "Repository not found" | O repositório é privado e o colega ainda não foi convidado (ou não aceitou o convite). |
| As telas não têm as mudanças mais novas | Rode `git pull` na pasta do projeto e reinicie o simulador e o backend. |
| Prédios "piscando" ou números estranhos | Outro grupo pode estar usando os mesmos nomes no correio público. Configurem o **HiveMQ Cloud** (privado) e usem o mesmo `.env` nos dois notebooks. |
