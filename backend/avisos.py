"""
avisos.py — mensagem de alerta mostrada no terminal do backend.

Os alertas aparecem no painel do gestor (rota /api/alertas); aqui eles também são
escritos no terminal, para quem estiver acompanhando a demonstração.
Todos os dados são SIMULADOS.
"""

from __future__ import annotations

from datetime import datetime

FORMATO = "%Y-%m-%d %H:%M:%S"
RODAPE = "Dados simulados — protótipo LeakFinder Londrina"


def _hora(ts_local: str) -> str:
    """'2026-11-13 01:58:00' → '13/11 01:58'"""
    return datetime.strptime(ts_local, FORMATO).strftime("%d/%m %H:%M")


def texto_alerta(evento: dict) -> str:
    """Texto curto de um evento 'novo' ou 'resolvido' gerado pela detecção."""
    a, p = evento["alerta"], evento["predio"]
    if evento["evento"] == "novo":
        titulo = "🚨 VAZAMENTO PROVÁVEL" if a["tipo"] == "vazamento" else "⚠️ CONSUMO EXCESSIVO"
        return (
            f"{titulo} — {p['nome']}\n"
            f"{a['detalhe']}\n"
            f"Vazão do problema: {a['vazao_estimada']:.1f} L/min (≈ {a['vazao_estimada'] * 60:.0f} L/h)\n"
            f"Provável causa: {a['provavel_causa']}\n"
            f"Início {_hora(a['inicio_sim'])} · detectado {_hora(a['detectado_sim'])} (horário simulado)\n"
            f"{RODAPE}"
        )
    duracao = max(0.0, (datetime.strptime(a["resolvido_sim"], FORMATO)
                        - datetime.strptime(a["inicio_sim"], FORMATO)).total_seconds() / 60)
    return (
        f"✅ RESOLVIDO — {p['nome']}\n"
        f"{a['motivo_resolucao']} às {_hora(a['resolvido_sim'])}. "
        f"Duração ≈ {duracao:.0f} min · perda estimada ≈ {a['litros_perdidos']:.0f} L\n"
        f"{RODAPE}"
    )


def mostrar(evento: dict) -> None:
    print("\n[ALERTA]\n" + texto_alerta(evento) + "\n")
