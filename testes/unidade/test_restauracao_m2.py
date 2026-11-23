"""Proteções e comparação do ensaio manual de restauração M2."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture
def ensaio(monkeypatch):
    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    return runpy.run_path(str(pasta / "ensaiar_restauracao_m2.py"))


@pytest.mark.parametrize("destino", ["etl", "etl_testes", "postgres", "etl_ensaio_m2_"])
def test_recusa_bancos_fora_do_destino_exclusivo(ensaio, destino):
    with pytest.raises(ValueError, match="destino"):
        ensaio["conferir_destino"](destino)


def test_aceita_apenas_nome_gerado_para_restauracao(ensaio):
    ensaio["conferir_destino"]("etl_ensaio_m2_20261119_180000_a1b2c3")


def test_comparacao_http_ignora_so_valor_opaco_do_proximo_cursor(ensaio):
    primeira = {
        "data": [{"populacao": "100"}],
        "meta": {"versao_core": 1},
        "pagina": {"limite": 2, "tem_mais": True, "proximo_cursor": "assinado-a"},
    }
    segunda = {**primeira, "pagina": {**primeira["pagina"], "proximo_cursor": "assinado-b"}}
    normalizar = ensaio["normalizar_resposta"]
    assert normalizar(primeira) == normalizar(segunda)
    assert primeira["pagina"]["proximo_cursor"] == "assinado-a"
    assert normalizar(primeira) != normalizar({**segunda, "data": [{"populacao": "101"}]})
    assert normalizar(primeira) != normalizar({**segunda, "meta": {"versao_core": 2}})
    assert normalizar(primeira) != normalizar({**segunda, "pagina": None})


def test_proxima_pagina_preserva_filtros_assinados(ensaio):
    from urllib.parse import parse_qs, urlsplit

    endereco = ensaio["url_proxima_pagina"](
        "/api/v1/populacao/ufs?ano=2020&limite=2", "cursor-assinado"
    )
    assert parse_qs(urlsplit(endereco).query) == {
        "ano": ["2020"],
        "limite": ["2"],
        "cursor": ["cursor-assinado"],
    }


def test_sondagem_nao_declara_sucesso_sem_exercitar_cursor(ensaio, monkeypatch):
    from types import SimpleNamespace

    class ClienteSemCursor:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get(self, *_):
            return SimpleNamespace(status_code=200, json=lambda: {"data": [], "pagina": None})

    comparar = ensaio["comparar_api"]
    monkeypatch.setitem(comparar.__globals__, "TestClient", ClienteSemCursor)
    monkeypatch.setitem(comparar.__globals__, "criar_aplicacao", lambda *_: None)
    with pytest.raises(RuntimeError, match="cursor"):
        comparar(None, None)
