"""
cadastro.py — inclusão de uma nova unidade (escola ou CMEI) pelo painel do gestor.

A unidade nova entra em dados/predios.json com camera_instalada = false: aparece no mapa
como "aguardando câmera" e não recebe leituras até a ESP32-CAM ser instalada (o simulador
também ignora unidades sem câmera). A média diária é calculada:
alunos × litros por aluno (escola 10 L, CMEI 25 L — ver CLAUDE.md).
"""

from __future__ import annotations

import json
import re
import threading

from .config import ARQUIVO_PREDIOS, LITROS_POR_ALUNO

_trava = threading.Lock()
_HORARIO = re.compile(r"^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$")
# Retângulo aproximado do município de Londrina (para evitar ponto fora da cidade)
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = -23.65, -23.05, -51.40, -50.90


class CadastroInvalido(ValueError):
    pass


def _validar(d: dict, existentes: dict) -> None:
    nome = (d.get("nome") or "").strip()
    if len(nome) < 3:
        raise CadastroInvalido("Informe o nome da unidade.")
    if any(p["nome"].strip().lower() == nome.lower() for p in existentes.values()):
        raise CadastroInvalido("Já existe uma unidade com esse nome.")
    if d.get("tipo") not in LITROS_POR_ALUNO:
        raise CadastroInvalido("Tipo deve ser escola ou CMEI.")
    if not _HORARIO.match(d.get("horario_uso") or ""):
        raise CadastroInvalido("Horário no formato 07:00-17:30.")
    ini, fim = d["horario_uso"].split("-")
    if ini >= fim:
        raise CadastroInvalido("O horário de abertura precisa ser antes do de fechamento.")
    if d.get("dias_uso") not in ("uteis", "todos"):
        raise CadastroInvalido("Dias de funcionamento: dias úteis ou todos os dias.")
    try:
        lat, lon, alunos = float(d["lat"]), float(d["lon"]), int(d["alunos"])
    except (KeyError, TypeError, ValueError):
        raise CadastroInvalido("Marque o local no mapa e informe o número de alunos.")
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        raise CadastroInvalido("O local precisa estar em Londrina.")
    if not 1 <= alunos <= 3000:
        raise CadastroInvalido("Número de alunos entre 1 e 3000.")


def _proximo_id(tipo: str, existentes: dict) -> str:
    numeros = [int(pid[len(tipo):]) for pid in existentes
               if pid.startswith(tipo) and pid[len(tipo):].isdigit()]
    return f"{tipo}{max(numeros, default=0) + 1}"


def incluir_unidade(dados: dict, existentes: dict) -> dict:
    """Valida, grava em dados/predios.json e devolve a unidade nova."""
    with _trava:
        _validar(dados, existentes)
        tipo = dados["tipo"]
        litros_por_aluno = LITROS_POR_ALUNO[tipo]
        alunos = int(dados["alunos"])
        unidade = {
            "id": _proximo_id(tipo, existentes),
            "nome": dados["nome"].strip(),
            "tipo": tipo,
            "regiao": (dados.get("regiao") or "").strip() or "—",
            "lat": round(float(dados["lat"]), 5),
            "lon": round(float(dados["lon"]), 5),
            "ativo": True,
            "camera_instalada": False,   # aguardando instalação da ESP32-CAM
            "horario_uso": dados["horario_uso"],
            "dias_uso": dados["dias_uso"],
            "alunos": alunos,
            "litros_por_aluno": litros_por_aluno,
            "media_diaria_litros": alunos * litros_por_aluno,
        }
        conteudo = json.loads(ARQUIVO_PREDIOS.read_text(encoding="utf-8"))
        conteudo["predios"].append(unidade)
        ARQUIVO_PREDIOS.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        existentes[unidade["id"]] = unidade
        return unidade
