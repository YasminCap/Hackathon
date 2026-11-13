"""
deteccao.py — regras de vazamento e consumo excessivo.

Tudo é avaliado no RELÓGIO SIMULADO (horário de Londrina gravado em ts_local),
não no relógio real — assim o tempo acelerado do simulador funciona naturalmente.

Regras (ver CLAUDE.md):
  1. Fora do horário de uso: fluxo contínuo > 0 por mais de LIMITE_FLUXO_CONTINUO_MIN
     → "vazamento".
  2. No horário de uso: litros da última janela (JANELA_EXCESSO_MIN) > FATOR_EXCESSO ×
     média histórica da mesma faixa de horário do próprio prédio (faixas de 15 min) e
     excesso ≥ MIN_EXCESSO_LPM → "consumo_excessivo".

Ciclo de vida do alerta:
  • no máximo 1 alerta ativo por prédio;
  • resolvido quando o fluxo zera (ex.: registro fechado) ou, no consumo excessivo,
    quando o consumo cai abaixo de FATOR_EXCESSO_RESOLVIDO × média;
  • depois de resolvido, COOLDOWN_MIN sem novo alerta no mesmo prédio.

A causa é sempre apresentada como "provável", deduzida da vazão do problema.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from . import db
from .config import (COOLDOWN_MIN, FATOR_EXCESSO, FATOR_EXCESSO_RESOLVIDO,
                     JANELA_EXCESSO_MIN, LACUNA_MAX_MIN,
                     LIMITE_FLUXO_CONTINUO_MIN, MIN_EXCESSO_LPM)

FORMATO = "%Y-%m-%d %H:%M:%S"
LEITURAS_ANALISADAS = 600  # ~20 h simuladas com 1 leitura a cada 2 min simulados
JANELA_RECENTE_MIN = 6     # vazão esperada "agora", para estimar a vazão do problema


def _dt(texto: str) -> datetime:
    return datetime.strptime(texto, FORMATO)


def _minutos(texto: str) -> int:
    h, m = texto.split(":")
    return int(h) * 60 + int(m)


def em_horario(predio: dict, t: datetime) -> bool:
    """Dia de funcionamento (dias_uso: "uteis" ou "todos") e dentro do horario_uso."""
    if t.weekday() >= 5 and predio.get("dias_uso", "uteis") != "todos":
        return False
    ini, fim = (_minutos(x) for x in predio["horario_uso"].split("-"))
    return ini <= t.hour * 60 + t.minute < fim


def provavel_causa(vazao_lpm: float) -> str:
    """Classificação pela vazão atribuída ao problema (faixas dos cenários do projeto)."""
    if vazao_lpm < 3:
        return "descarga vazando (válvula ou caixa acoplada)"
    if vazao_lpm < 5:
        return "boia da caixa d'água travada"
    if vazao_lpm < 15:
        return "torneira aberta ou mal fechada"
    return "cano rompido"


class Detector:
    def __init__(self, predios: dict[str, dict]):
        self.predios = {pid: p for pid, p in predios.items() if p["ativo"]}
        self._ultimo_id: dict[str, int] = {}          # última leitura já avaliada
        self._medias: dict[str, dict[int, float]] = {}  # cache do histórico por faixa de 15 min

    # ------------------------------------------------------------------ entrada
    def avaliar(self) -> list[dict]:
        """Avalia os prédios com leitura nova. Devolve eventos 'novo' e 'resolvido'."""
        eventos = []
        registros = db.estado_registros()
        for pid, predio in self.predios.items():
            leituras = db.leituras_mais_recentes(pid, LEITURAS_ANALISADAS)
            if not leituras or leituras[0]["id"] == self._ultimo_id.get(pid):
                continue
            self._ultimo_id[pid] = leituras[0]["id"]
            evento = self._avaliar_predio(predio, leituras, registros.get(pid, "aberto"))
            if evento:
                eventos.append(evento)
        return eventos

    # -------------------------------------------------------------- por prédio
    def _avaliar_predio(self, predio: dict, leituras: list[dict], registro: str) -> dict | None:
        pid = predio["id"]
        ultima = leituras[0]
        t = _dt(ultima["ts_local"])

        ativo = db.alerta_ativo(pid)
        if ativo:
            motivo = self._motivo_resolucao(ativo, predio, leituras, t, registro)
            if not motivo:
                return None
            duracao = max(0.0, (t - _dt(ativo["inicio_sim"])).total_seconds() / 60)
            perdidos = round(ativo["vazao_estimada"] * duracao, 1)
            db.resolver_alerta(ativo["id"], ultima["ts_local"], motivo, perdidos)
            return {"evento": "resolvido", "predio": predio, "registro": registro,
                    "alerta": db.obter_alerta(ativo["id"])}

        anterior = db.ultimo_alerta_resolvido(pid)
        if anterior and t < _dt(anterior["resolvido_sim"]) + timedelta(minutes=COOLDOWN_MIN):
            return None  # cooldown

        achado = self._regra_fora_do_horario(predio, leituras, t) or self._regra_excesso(predio, leituras, t)
        if not achado:
            return None
        achado["dispositivo"] = pid
        achado["detectado_sim"] = ultima["ts_local"]
        alerta_id = db.criar_alerta(achado)
        return {"evento": "novo", "predio": predio, "registro": registro,
                "alerta": db.obter_alerta(alerta_id)}

    def _motivo_resolucao(self, alerta, predio, leituras, t, registro) -> str | None:
        if leituras[0]["vazao_lpm"] <= 0:
            return "registro fechado — fluxo zerou" if registro == "fechado" else "fluxo zerou"
        if alerta["tipo"] == "consumo_excessivo" and em_horario(predio, t):
            janela = self._janela(predio, leituras, t)
            if janela and janela[1] > 0 and janela[0] < FATOR_EXCESSO_RESOLVIDO * janela[1]:
                return "consumo voltou ao normal"
        return None

    # ------------------------------------------------------------------- regras
    def _regra_fora_do_horario(self, predio, leituras, t) -> dict | None:
        """Sequência mais recente de leituras com vazão > 0, todas fora do horário de uso."""
        sequencia, anterior = [], None
        for r in leituras:  # da mais nova para a mais antiga
            tr = _dt(r["ts_local"])
            if r["vazao_lpm"] <= 0 or em_horario(predio, tr):
                break
            if anterior and anterior - tr > timedelta(minutes=LACUNA_MAX_MIN):
                break  # buraco nas leituras (relógio adiantado, prédio offline)
            sequencia.append(r)
            anterior = tr
        if not sequencia:
            return None
        inicio = sequencia[-1]["ts_local"]
        duracao = (t - _dt(inicio)).total_seconds() / 60
        if duracao < LIMITE_FLUXO_CONTINUO_MIN:
            return None
        vazao = round(median(r["vazao_lpm"] for r in sequencia), 2)
        return {
            "tipo": "vazamento",
            "provavel_causa": provavel_causa(vazao),
            "vazao_estimada": vazao,
            "detalhe": f"Fluxo contínuo fora do horário de uso há {duracao:.0f} min "
                       f"(vazão mediana {vazao:.1f} L/min).",
            "inicio_sim": inicio,
        }

    def _regra_excesso(self, predio, leituras, t) -> dict | None:
        if not em_horario(predio, t):
            return None
        janela = self._janela(predio, leituras, t)
        if not janela:
            return None
        litros, base = janela
        if base < 1 or litros <= FATOR_EXCESSO * base:
            return None
        if litros - base < MIN_EXCESSO_LPM * JANELA_EXCESSO_MIN:
            return None
        # Vazão do problema: vazão ATUAL (mediana das últimas leituras) menos a vazão esperada
        # para este horário. A média da janela diluiria um vazamento que começou no meio dela.
        excesso_total = litros - base
        excesso = excesso_total / JANELA_EXCESSO_MIN
        recente = self._janela(predio, leituras, t, JANELA_RECENTE_MIN)
        if recente:
            vazao_atual = median(r["vazao_lpm"] for r in leituras[:3])
            excesso = max(excesso, vazao_atual - recente[1] / JANELA_RECENTE_MIN)
        # início estimado: há quanto tempo esse excesso, nessa vazão, vem acontecendo
        minutos_problema = min(JANELA_EXCESSO_MIN, excesso_total / excesso)
        return {
            "tipo": "consumo_excessivo",
            "provavel_causa": provavel_causa(excesso),
            "vazao_estimada": round(excesso, 2),
            "detalhe": f"{litros:.0f} L nos últimos {JANELA_EXCESSO_MIN} min — "
                       f"{litros / base:.1f}× a média da mesma faixa de horário ({base:.0f} L).",
            "inicio_sim": (t - timedelta(minutes=minutos_problema)).strftime(FORMATO),
        }

    def _janela(self, predio, leituras, t, minutos: int = JANELA_EXCESSO_MIN) -> tuple[float, float] | None:
        """(litros medidos, litros esperados pelo histórico) nos `minutos` que terminam em t."""
        medias = self._medias.get(predio["id"]) or db.media_por_faixa(predio["id"])
        if not medias:
            return None  # sem histórico: rode simulador/gerar_historico.py
        self._medias[predio["id"]] = medias

        inicio = t - timedelta(minutes=minutos)
        dentro = [r for r in leituras if _dt(r["ts_local"]) > inicio]
        tempos = [_dt(r["ts_local"]) for r in dentro]
        # a janela precisa estar coberta: começo perto do início e sem buracos
        if not tempos or tempos[-1] - inicio > timedelta(minutes=max(2.0, minutos * 0.2)):
            return None
        if any(a - b > timedelta(minutes=LACUNA_MAX_MIN) for a, b in zip(tempos, tempos[1:])):
            return None
        litros = sum(r["litros"] for r in dentro)

        # esperado: média de cada faixa de 15 min, proporcional aos minutos da janela nela
        base, cursor = 0.0, inicio
        while cursor < t:
            faixa = (cursor.hour * 60 + cursor.minute) // 15 * 15
            inicio_faixa = cursor.replace(hour=faixa // 60, minute=faixa % 60, second=0)
            proxima = min(t, inicio_faixa + timedelta(minutes=15))
            base += medias.get(faixa, 0.0) * (proxima - cursor).total_seconds() / (15 * 60)
            cursor = proxima
        return litros, base
