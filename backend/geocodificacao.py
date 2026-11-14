"""
geocodificacao.py — transforma o endereço digitado no cadastro em um ponto no mapa.

Usa o Nominatim, o serviço gratuito de busca de endereços do OpenStreetMap (o mesmo projeto
que fornece o mapa do painel). A busca é limitada a Londrina. Regras de uso do serviço:
no máximo 1 busca por segundo e um nome de aplicativo identificável (User-Agent) — o
cadastro faz uma busca por clique, então fica bem abaixo do limite.

Só o endereço da unidade é enviado ao serviço; nenhum dado pessoal.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "LeakFinderLondrina/1.0 (prototipo SmartCities Hackathon Londrina)"
# Caixa em volta de Londrina (oeste, norte, leste, sul) — a busca não sai dela
CAIXA_LONDRINA = "-51.40,-23.05,-50.90,-23.65"

_trava = threading.Lock()
_ultima_busca = 0.0


class EnderecoNaoEncontrado(ValueError):
    pass


def localizar(endereco: str) -> dict:
    """Devolve {'lat', 'lon', 'endereco_encontrado'} do primeiro resultado em Londrina."""
    global _ultima_busca
    endereco = (endereco or "").strip()
    if len(endereco) < 5:
        raise EnderecoNaoEncontrado("Digite o endereço (rua e número).")
    parametros = urllib.parse.urlencode({
        "q": f"{endereco}, Londrina, Paraná, Brasil",
        "format": "json",
        "limit": 1,
        "countrycodes": "br",
        "viewbox": CAIXA_LONDRINA,
        "bounded": 1,
    })
    with _trava:  # respeita o limite de 1 busca por segundo
        espera = 1.0 - (time.monotonic() - _ultima_busca)
        if espera > 0:
            time.sleep(espera)
        _ultima_busca = time.monotonic()
        pedido = urllib.request.Request(f"{URL}?{parametros}", headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(pedido, timeout=10) as resposta:
                resultados = json.load(resposta)
        except OSError as erro:
            raise EnderecoNaoEncontrado(
                "Não foi possível consultar o endereço agora (sem internet?). Marque o local clicando no mapa."
            ) from erro
    if not resultados:
        raise EnderecoNaoEncontrado(
            "Endereço não encontrado em Londrina. Confira o nome da rua ou marque o local clicando no mapa.")
    r = resultados[0]
    return {"lat": float(r["lat"]), "lon": float(r["lon"]), "endereco_encontrado": r.get("display_name", "")}
