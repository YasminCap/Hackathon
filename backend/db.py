"""
db.py — persistência em SQLite.

Tabelas:
  leituras           — cada leitura (foto do hidrômetro) recebida em hidrometro/<id>/leitura
  consumo_historico  — histórico SIMULADO por faixa de 15 min (a "média normal" de cada unidade)
  alertas            — vazamentos detectados + campo de operação (pendente/informado/consertado)
  consumo_diario     — litros por unidade e por dia (histórico guardado; a visão semanal sai daqui)

Cada operação abre sua própria conexão: o cliente MQTT grava numa thread e a API lê
em outras, e o SQLite em modo WAL lida bem com isso no volume do protótipo
(~8 prédios × 1 leitura a cada 2 s).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_CAMINHO

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leituras (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo   TEXT    NOT NULL,
    timestamp     TEXT    NOT NULL,  -- UTC, como veio do hidrômetro (ISO 8601 com Z)
    ts_local      TEXT    NOT NULL,  -- mesmo instante em Londrina: 'AAAA-MM-DD HH:MM:SS'
    litros        REAL    NOT NULL,  -- volume desde a leitura anterior
    vazao_lpm     REAL    NOT NULL,  -- vazão no momento
    total_litros  REAL    NOT NULL,  -- acumulado do hidrômetro
    simulado      INTEGER NOT NULL DEFAULT 1,
    recebido_em   TEXT    NOT NULL   -- relógio REAL do servidor (UTC)
);
CREATE INDEX IF NOT EXISTS ix_leituras_disp_ts ON leituras (dispositivo, ts_local);

-- Consumo em faixas de 15 min de semanas anteriores (SIMULADO, gerado por
-- simulador/gerar_historico.py). É a "média da mesma faixa do próprio prédio" usada na
-- regra de consumo excessivo. Faixas de 15 min (e não de 1 h) acompanham bem a abertura
-- e o fechamento do prédio — com hora cheia, a janela perto desses horários dava falso alarme.
CREATE TABLE IF NOT EXISTS consumo_historico (
    dispositivo  TEXT    NOT NULL,
    data         TEXT    NOT NULL,   -- AAAA-MM-DD (horário de Londrina)
    minuto       INTEGER NOT NULL,   -- início da faixa em minutos do dia: 0, 15, 30 ... 1425
    dia_util     INTEGER NOT NULL,   -- 1 = seg a sex
    litros       REAL    NOT NULL,
    PRIMARY KEY (dispositivo, data, minuto)
);

CREATE TABLE IF NOT EXISTS alertas (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo        TEXT NOT NULL,
    tipo               TEXT NOT NULL,   -- vazamento | consumo_excessivo
    provavel_causa     TEXT NOT NULL,
    vazao_estimada     REAL NOT NULL,   -- L/min atribuídos ao problema
    detalhe            TEXT NOT NULL,   -- frase explicando a regra que disparou
    inicio_sim         TEXT NOT NULL,   -- quando o problema começou (horário simulado de Londrina)
    detectado_sim      TEXT NOT NULL,
    detectado_real     TEXT NOT NULL,   -- UTC real
    status             TEXT NOT NULL DEFAULT 'ativo',  -- ativo | resolvido
    resolvido_sim      TEXT,
    motivo_resolucao   TEXT,
    litros_perdidos    REAL,            -- estimativa: vazao_estimada × duração
    -- Campo de operação, preenchido pelo gestor no painel:
    operacao           TEXT NOT NULL DEFAULT 'pendente',  -- pendente | informado | consertado
    operacao_em        TEXT             -- quando a operação mudou pela última vez (UTC real)
);
CREATE INDEX IF NOT EXISTS ix_alertas_disp ON alertas (dispositivo, id);

-- Consumo de cada unidade por dia (horário de Londrina). Alimentado pelo histórico simulado e
-- por cada foto recebida; é a base do histórico semanal e da média semanal de acompanhamento.
CREATE TABLE IF NOT EXISTS consumo_diario (
    dispositivo  TEXT NOT NULL,
    data         TEXT NOT NULL,   -- AAAA-MM-DD
    litros       REAL NOT NULL,
    PRIMARY KEY (dispositivo, data)
);
"""


@contextmanager
def conexao():
    """Abre uma conexão, faz commit no fim e sempre fecha."""
    con = sqlite3.connect(DB_CAMINHO, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def agora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def inicializar() -> None:
    DB_CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    with conexao() as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(ESQUEMA)
        # Banco criado por uma versão antiga: acrescenta as colunas do campo de operação
        colunas = {r["name"] for r in con.execute("PRAGMA table_info(alertas)")}
        if "operacao" not in colunas:
            con.execute("ALTER TABLE alertas ADD COLUMN operacao TEXT NOT NULL DEFAULT 'pendente'")
        if "operacao_em" not in colunas:
            con.execute("ALTER TABLE alertas ADD COLUMN operacao_em TEXT")


# ------------------------------------------------------------------ leituras
def inserir_leitura(leitura: dict) -> None:
    """`leitura` já validada pelo mqtt_cliente (inclui ts_local)."""
    with conexao() as con:
        con.execute(
            """INSERT INTO leituras
               (dispositivo, timestamp, ts_local, litros, vazao_lpm, total_litros, simulado, recebido_em)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                leitura["dispositivo"], leitura["timestamp"], leitura["ts_local"],
                leitura["litros"], leitura["vazao_lpm"], leitura["total_litros"],
                1 if leitura.get("simulado", True) else 0, agora_utc(),
            ),
        )
        # soma no dia: a foto das 00:00 mostra o que passou até meia-noite (dia anterior)
        con.execute(
            """INSERT INTO consumo_diario (dispositivo, data, litros)
               VALUES (?, date(datetime(?, '-1 minute')), ?)
               ON CONFLICT(dispositivo, data) DO UPDATE SET litros = litros + excluded.litros""",
            (leitura["dispositivo"], leitura["ts_local"], leitura["litros"]),
        )


def ultimas_leituras() -> dict[str, dict]:
    """Leitura mais recente de cada prédio."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT l.* FROM leituras l
               JOIN (SELECT dispositivo, MAX(id) AS id FROM leituras GROUP BY dispositivo) u
                 ON u.id = l.id"""
        ).fetchall()
    return {r["dispositivo"]: dict(r) for r in linhas}


def leituras_recentes(dispositivo: str, limite: int) -> list[dict]:
    """Últimas `limite` leituras do prédio, em ordem cronológica (para o gráfico)."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT timestamp, ts_local, litros, vazao_lpm, total_litros
               FROM leituras WHERE dispositivo = ? ORDER BY id DESC LIMIT ?""",
            (dispositivo, limite),
        ).fetchall()
    return [dict(r) for r in reversed(linhas)]


def consumo_por_hora(dispositivo: str, horas: int) -> list[dict]:
    """Litros somados por hora (horário de Londrina) nas `horas` horas simuladas que
    terminam na leitura MAIS RECENTE do prédio. Usar a mais recente (e não a maior data)
    evita misturar dias antigos quando o simulador é reiniciado com o relógio em outra data."""
    with conexao() as con:
        ultima = con.execute(
            "SELECT ts_local FROM leituras WHERE dispositivo = ? ORDER BY id DESC LIMIT 1",
            (dispositivo,),
        ).fetchone()
        if not ultima:
            return []
        linhas = con.execute(
            # "- 1 minute": a foto das 07:00 mostra o que passou ATÉ as 07:00 (06:30–07:00),
            # então esses litros pertencem à hora das 06h.
            """SELECT substr(datetime(ts_local, '-1 minute'), 1, 13) || ':00' AS hora,
                      ROUND(SUM(litros), 2)        AS litros,
                      ROUND(MAX(vazao_lpm), 2)     AS vazao_max_lpm,
                      COUNT(*)                     AS leituras
               FROM leituras
               WHERE dispositivo = ?
                 AND ts_local >  datetime(?, ?)
                 AND ts_local <= ?
               GROUP BY substr(datetime(ts_local, '-1 minute'), 1, 13)
               ORDER BY hora""",
            (dispositivo, ultima["ts_local"], f"-{int(horas)} hours", ultima["ts_local"]),
        ).fetchall()
    return [dict(r) for r in linhas]


def ultima_leitura(dispositivo: str) -> dict | None:
    """Leitura aceita mais recente do prédio (para conferir a próxima foto)."""
    with conexao() as con:
        r = con.execute(
            "SELECT total_litros, ts_local FROM leituras WHERE dispositivo = ? ORDER BY id DESC LIMIT 1",
            (dispositivo,),
        ).fetchone()
    return dict(r) if r else None


def contar_leituras() -> int:
    with conexao() as con:
        return con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]


# --------------------------------------------------------- histórico (simulado)
def substituir_historico(linhas: list[tuple]) -> None:
    """Apaga e regrava o histórico. Cada linha: (dispositivo, data, minuto, dia_util, litros)."""
    with conexao() as con:
        con.execute("DELETE FROM consumo_historico")
        con.executemany(
            "INSERT INTO consumo_historico (dispositivo, data, minuto, dia_util, litros) VALUES (?, ?, ?, ?, ?)",
            linhas,
        )
        # o histórico também vira consumo por dia (base do histórico semanal)
        con.execute(
            """INSERT OR REPLACE INTO consumo_diario (dispositivo, data, litros)
               SELECT dispositivo, data, SUM(litros) FROM consumo_historico GROUP BY dispositivo, data"""
        )


def media_por_faixa(dispositivo: str) -> dict[int, float]:
    """Média de litros por faixa de 15 min (chave = minuto do dia), só dias úteis.
    Vazio se não há histórico."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT minuto, AVG(litros) AS media FROM consumo_historico
               WHERE dispositivo = ? AND dia_util = 1 GROUP BY minuto""",
            (dispositivo,),
        ).fetchall()
    return {r["minuto"]: r["media"] for r in linhas}


# ------------------------------------------------------------ apoio à detecção
def leituras_mais_recentes(dispositivo: str, limite: int) -> list[dict]:
    """Últimas leituras do prédio, da MAIS NOVA para a mais antiga."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT id, ts_local, litros, vazao_lpm FROM leituras
               WHERE dispositivo = ? ORDER BY id DESC LIMIT ?""",
            (dispositivo, limite),
        ).fetchall()
    return [dict(r) for r in linhas]


# -------------------------------------------------------------------- alertas
def alerta_ativo(dispositivo: str) -> dict | None:
    with conexao() as con:
        r = con.execute(
            "SELECT * FROM alertas WHERE dispositivo = ? AND status = 'ativo' ORDER BY id DESC LIMIT 1",
            (dispositivo,),
        ).fetchone()
    return dict(r) if r else None


def ultimo_alerta_resolvido(dispositivo: str) -> dict | None:
    with conexao() as con:
        r = con.execute(
            "SELECT * FROM alertas WHERE dispositivo = ? AND status = 'resolvido' ORDER BY id DESC LIMIT 1",
            (dispositivo,),
        ).fetchone()
    return dict(r) if r else None


def criar_alerta(a: dict) -> int:
    with conexao() as con:
        cur = con.execute(
            """INSERT INTO alertas (dispositivo, tipo, provavel_causa, vazao_estimada, detalhe,
                                    inicio_sim, detectado_sim, detectado_real)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (a["dispositivo"], a["tipo"], a["provavel_causa"], a["vazao_estimada"], a["detalhe"],
             a["inicio_sim"], a["detectado_sim"], agora_utc()),
        )
        return cur.lastrowid


def resolver_alerta(alerta_id: int, resolvido_sim: str, motivo: str, litros_perdidos: float) -> None:
    with conexao() as con:
        con.execute(
            """UPDATE alertas SET status = 'resolvido', resolvido_sim = ?, motivo_resolucao = ?,
                                  litros_perdidos = ? WHERE id = ?""",
            (resolvido_sim, motivo, litros_perdidos, alerta_id),
        )


OPERACOES = ("pendente", "informado", "consertado")


def definir_operacao(alerta_id: int, operacao: str) -> dict | None:
    """Campo de operação do alerta: pendente → informado (manutenção avisada) → consertado."""
    if operacao not in OPERACOES:
        raise ValueError(f"operação inválida: {operacao}")
    with conexao() as con:
        con.execute("UPDATE alertas SET operacao = ?, operacao_em = ? WHERE id = ?",
                    (operacao, agora_utc(), alerta_id))
    return obter_alerta(alerta_id)


def obter_alerta(alerta_id: int) -> dict | None:
    with conexao() as con:
        r = con.execute("SELECT * FROM alertas WHERE id = ?", (alerta_id,)).fetchone()
    return dict(r) if r else None


def consumo_semanal(dispositivo: str, semanas: int = 8) -> list[dict]:
    """Litros por semana (segunda a domingo) das últimas `semanas` semanas com dados,
    com quantos dias da semana têm registro (7 = semana completa)."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT date(data, '-6 days', 'weekday 1') AS inicio,
                      ROUND(SUM(litros), 1)                AS litros,
                      COUNT(*)                             AS dias
               FROM consumo_diario WHERE dispositivo = ?
               GROUP BY inicio ORDER BY inicio DESC LIMIT ?""",
            (dispositivo, semanas),
        ).fetchall()
    return [dict(r) for r in reversed(linhas)]


def alertas_por_operacao(finalizados: bool, limite: int = 50) -> list[dict]:
    """finalizados=True → operação 'consertado' (aba Finalizados); False → os demais."""
    condicao = "operacao = 'consertado'" if finalizados else "operacao != 'consertado'"
    with conexao() as con:
        linhas = con.execute(
            f"SELECT * FROM alertas WHERE {condicao} "
            "ORDER BY (status = 'ativo') DESC, id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(r) for r in linhas]


def limpar_alertas() -> int:
    """Apaga TODO o histórico de vazamentos (em andamento e finalizados). Usado para
    recomeçar entre testes/demonstrações; não mexe nas leituras nem no consumo registrado."""
    with conexao() as con:
        return con.execute("DELETE FROM alertas").rowcount


def todos_alertas() -> list[dict]:
    with conexao() as con:
        return [dict(r) for r in con.execute("SELECT * FROM alertas ORDER BY id").fetchall()]


def alertas_recentes(limite: int = 30) -> list[dict]:
    """Ativos primeiro, depois os mais novos."""
    with conexao() as con:
        linhas = con.execute(
            "SELECT * FROM alertas ORDER BY (status = 'ativo') DESC, id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(r) for r in linhas]
