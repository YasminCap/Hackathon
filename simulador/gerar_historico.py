"""
gerar_historico.py — cria 4 semanas de consumo SIMULADO, em faixas de 15 min, para cada prédio.

Por quê: a regra de "consumo excessivo" compara o consumo atual com a média da
mesma faixa de horário da própria escola. Num protótipo recém-ligado não existe
esse passado, então geramos um, com o MESMO perfil de consumo do simulador
(picos de entrada, intervalo e merenda) e variação natural de dia para dia.

Grava na tabela consumo_historico do banco do backend (olhodagua.db).
Rodar uma vez (ou de novo para regerar), na raiz do projeto:
    .venv\\Scripts\\python.exe simulador\\gerar_historico.py
"""

import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))  # para importar o pacote backend

from backend import db  # noqa: E402
from simulador import Predio, hhmm_para_minutos  # noqa: E402  (simulador.py nesta pasta)

DIAS = 28


def main() -> None:
    with open(RAIZ / "dados" / "escolas.json", encoding="utf-8") as f:
        cadastro = [p for p in json.load(f)["predios"] if p["ativo"]]

    rng = random.Random(2026)  # reprodutível: mesmo histórico a cada execução
    hoje = date.today()
    linhas = []
    for p in cadastro:
        ini, fim = p["horario_uso"].split("-")
        predio = Predio(id=p["id"], nome=p["nome"], tipo=p["tipo"],
                        inicio_min=hhmm_para_minutos(ini), fim_min=hhmm_para_minutos(fim),
                        media_diaria=float(p["media_diaria_litros"]), total_litros=0)
        predio.preparar_perfil()
        for d in range(DIAS, 0, -1):
            dia = hoje - timedelta(days=d)
            util = dia.weekday() < 5
            fator_dia = rng.uniform(0.9, 1.1)  # dias mais ou menos movimentados
            meia_noite = datetime(dia.year, dia.month, dia.day)
            for minuto in range(0, 24 * 60, 15):
                # integra a vazão esperada (no meio de cada minuto) dentro da faixa de 15 min
                litros = sum(predio.vazao_esperada(meia_noite + timedelta(minutes=minuto + m + 0.5))
                             for m in range(15))
                litros *= fator_dia * rng.uniform(0.9, 1.1)
                linhas.append((p["id"], dia.isoformat(), minuto, 1 if util else 0, round(litros, 2)))

    db.inicializar()
    db.substituir_historico(linhas)
    print(f"[OK] Histórico SIMULADO gravado: {len(cadastro)} prédios × {DIAS} dias × 96 faixas = {len(linhas)} linhas")
    for p in cadastro:
        media = db.media_por_faixa(p["id"])
        dia_medio = sum(media.values())
        pico = max(media, key=media.get)
        print(f"  {p['id']:8} dia útil médio ≈ {dia_medio:8.0f} L  "
              f"(pico {pico // 60:02d}:{pico % 60:02d}: {media[pico]:5.0f} L em 15 min)")


if __name__ == "__main__":
    main()
