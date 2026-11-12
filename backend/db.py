"""
db.py — persistência em SQLite.

Tabelas:
  leituras  — cada mensagem recebida em hidrometro/<id>/leitura
  comandos  — cada comando enviado em hidrometro/<id>/comando (trilha de auditoria)

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

CREATE TABLE IF NOT EXISTS comandos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    dispositivo     TEXT NOT NULL,
    acao            TEXT NOT NULL,   -- fechar_registro | abrir_registro
    autorizado_por  TEXT NOT NULL,   -- ex.: telegram:<user_id>, painel
    timestamp       TEXT NOT NULL    -- UTC
);
CREATE INDEX IF NOT EXISTS ix_comandos_disp ON comandos (dispositivo, id);

-- Consumo em faixas de 15 min de semanas anteriores (SIMULADO, gerado por
-- simulador/gerar_historico.py). É a "média da mesma faixa da própria escola" usada na
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
    telegram_msg_id    INTEGER
);
CREATE INDEX IF NOT EXISTS ix_alertas_disp ON alertas (dispositivo, id);
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
    """Litros somados por hora (horário de Londrina) nas últimas `horas` horas simuladas."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT substr(ts_local, 1, 13) || ':00' AS hora,
                      ROUND(SUM(litros), 2)        AS litros,
                      ROUND(MAX(vazao_lpm), 2)     AS vazao_max_lpm,
                      COUNT(*)                     AS leituras
               FROM leituras WHERE dispositivo = ?
               GROUP BY substr(ts_local, 1, 13)
               ORDER BY hora DESC LIMIT ?""",
            (dispositivo, horas),
        ).fetchall()
    return [dict(r) for r in reversed(linhas)]


def contar_leituras() -> int:
    with conexao() as con:
        return con.execute("SELECT COUNT(*) FROM leituras").fetchone()[0]


# ------------------------------------------------------------------ comandos
def registrar_comando(dispositivo: str, acao: str, autorizado_por: str, timestamp: str) -> int:
    with conexao() as con:
        cur = con.execute(
            "INSERT INTO comandos (dispositivo, acao, autorizado_por, timestamp) VALUES (?, ?, ?, ?)",
            (dispositivo, acao, autorizado_por, timestamp),
        )
        return cur.lastrowid


def estado_registros() -> dict[str, str]:
    """'aberto' ou 'fechado' para cada prédio, pelo último comando enviado."""
    with conexao() as con:
        linhas = con.execute(
            """SELECT c.dispositivo, c.acao FROM comandos c
               JOIN (SELECT dispositivo, MAX(id) AS id FROM comandos GROUP BY dispositivo) u
                 ON u.id = c.id"""
        ).fetchall()
    return {r["dispositivo"]: ("fechado" if r["acao"] == "fechar_registro" else "aberto") for r in linhas}


def comandos_recentes(limite: int = 20) -> list[dict]:
    with conexao() as con:
        linhas = con.execute("SELECT * FROM comandos ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
    return [dict(r) for r in linhas]


# --------------------------------------------------------- histórico (simulado)
def substituir_historico(linhas: list[tuple]) -> None:
    """Apaga e regrava o histórico. Cada linha: (dispositivo, data, minuto, dia_util, litros)."""
    with conexao() as con:
        con.execute("DELETE FROM consumo_historico")
        con.executemany(
            "INSERT INTO consumo_historico (dispositivo, data, minuto, dia_util, litros) VALUES (?, ?, ?, ?, ?)",
            linhas,
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


def salvar_telegram_msg(alerta_id: int, msg_id: int) -> None:
    with conexao() as con:
        con.execute("UPDATE alertas SET telegram_msg_id = ? WHERE id = ?", (msg_id, alerta_id))


def obter_alerta(alerta_id: int) -> dict | None:
    with conexao() as con:
        r = con.execute("SELECT * FROM alertas WHERE id = ?", (alerta_id,)).fetchone()
    return dict(r) if r else None


def alertas_recentes(limite: int = 30) -> list[dict]:
    """Ativos primeiro, depois os mais novos."""
    with conexao() as con:
        linhas = con.execute(
            "SELECT * FROM alertas ORDER BY (status = 'ativo') DESC, id DESC LIMIT ?", (limite,)
        ).fetchall()
    return [dict(r) for r in linhas]
