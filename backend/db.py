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
