"""
economia.py — demonstrativo da água que não foi desperdiçada e do valor poupado na conta.

Para cada vazamento já resolvido (o consumo voltou ao normal):
  • sem o LeakFinder, ele continuaria até aparecer na conta: vazão × DIAS_SEM_SISTEMA;
  • com o LeakFinder, vazou só até o conserto: litros_perdidos (já calculado na detecção);
  • água não desperdiçada = (sem o sistema) − (o que vazou de fato);
  • economia em R$ = água não desperdiçada (m³) × TARIFA_RS_M3.

TARIFA_RS_M3 é a tarifa média de ÁGUA da Sanepar em 2026 (R$ 7,0032/m³, sem esgoto) — por
isso a economia é uma estimativa conservadora. Os vazamentos do protótipo são SIMULADOS.
"""

from __future__ import annotations

from .config import DIAS_SEM_SISTEMA, TARIFA_RS_M3


def _virgula(valor: float) -> str:
    """7.0032 → '7,00' (formato brasileiro)."""
    return f"{valor:.2f}".replace(".", ",")


def economia_do_alerta(alerta: dict) -> dict | None:
    """Água não desperdiçada e R$ de um alerta resolvido (None se ainda está ativo)."""
    if alerta["status"] != "resolvido" or alerta.get("litros_perdidos") is None:
        return None
    sem_sistema = alerta["vazao_estimada"] * DIAS_SEM_SISTEMA * 24 * 60
    nao_desperdicado = max(0.0, sem_sistema - alerta["litros_perdidos"])
    return {
        "litros_sem_sistema": round(sem_sistema),
        "litros_nao_desperdicados": round(nao_desperdicado),
        "valor_rs": round(nao_desperdicado / 1000 * TARIFA_RS_M3, 2),
    }


def demonstrativo(alertas: list[dict]) -> dict:
    """Totais e economia por mês (mês em que o vazamento foi resolvido, horário simulado)."""
    total_litros, total_rs, ocorrencias = 0.0, 0.0, 0
    por_mes: dict[str, dict] = {}
    for a in alertas:
        e = economia_do_alerta(a)
        if not e:
            continue
        ocorrencias += 1
        total_litros += e["litros_nao_desperdicados"]
        total_rs += e["valor_rs"]
        mes = a["resolvido_sim"][:7]  # AAAA-MM
        m = por_mes.setdefault(mes, {"mes": mes, "litros": 0.0, "valor_rs": 0.0})
        m["litros"] += e["litros_nao_desperdicados"]
        m["valor_rs"] += e["valor_rs"]
    return {
        "aviso": "DADOS SIMULADOS",
        "ocorrencias": ocorrencias,
        "litros_nao_desperdicados": round(total_litros),
        "m3_nao_desperdicados": round(total_litros / 1000, 1),
        "valor_rs": round(total_rs, 2),
        "tarifa_rs_m3": TARIFA_RS_M3,
        "dias_sem_sistema": DIAS_SEM_SISTEMA,
        "hipotese": (f"Sem o LeakFinder, cada vazamento duraria {DIAS_SEM_SISTEMA:g} dias (até a próxima conta). "
                     f"Tarifa média de água da Sanepar 2026: R$ {_virgula(TARIFA_RS_M3)}/m³ (sem esgoto)."),
        "por_mes": [{"mes": m["mes"], "litros": round(m["litros"]), "valor_rs": round(m["valor_rs"], 2)}
                    for m in sorted(por_mes.values(), key=lambda x: x["mes"])],
    }
