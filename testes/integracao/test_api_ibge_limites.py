"""Cursores estruturalmente inválidos e páginas territoriais sem rede externa."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from pipeline_etl.api.cursores import assinar_cursor, resumir_filtros
from pipeline_etl.api.ibge import FiltrosMunicipios, FiltrosPopulacao, FiltrosTotais

pytestmark = pytest.mark.integracao
ESPECIFICACAO = importlib.util.spec_from_file_location(
    "apoio_api_ibge_limites", Path(__file__).with_name("test_api_ibge.py")
)
assert ESPECIFICACAO is not None and ESPECIFICACAO.loader is not None
APOIO = importlib.util.module_from_spec(ESPECIFICACAO)
ESPECIFICACAO.loader.exec_module(APOIO)
api_ibge = APOIO.api_ibge


@pytest.mark.parametrize(
    "tipo,chaves",
    [
        ("municipios", ["abc"]),
        ("municipios", ["1234567", "extra"]),
        ("populacao", ["abc"]),
        ("populacao", ["2019"]),
        ("populacao", ["2020", "extra"]),
        ("total", ["1", "nao_uuid"]),
        ("total", ["0", "00000000-0000-0000-0000-000000000001"]),
        ("total", ["1"]),
    ],
)
def test_cursor_assinado_com_chave_invalida_e_recusado(api_ibge, banco, tipo, chaves):
    if tipo == "municipios":
        filtros = FiltrosMunicipios()
        rota, caminho = "ibge:municipios", "/api/v1/municipios"
    elif tipo == "populacao":
        filtros = FiltrosPopulacao()
        rota, caminho = "ibge:populacao", "/api/v1/municipios/3550308/populacao"
    else:
        filtros = FiltrosTotais(ano=2025)
        rota, caminho = "ibge:total:ufs", "/api/v1/populacao/ufs"
    identidade = filtros.model_dump(exclude={"cursor"}, mode="json")
    if tipo == "populacao":
        identidade["codigo"] = "3550308"
    with banco.connect() as conexao:
        estado = (
            conexao.execute(text("SELECT * FROM ops.publicacao WHERE dominio='ibge'"))
            .mappings()
            .one()
        )
    geracao = (
        f"ibge:gold:{estado['versao_gold']}:{estado['versao_core']}:"
        f"{estado['situacao']}:{estado['data_publicacao']}"
        if tipo == "total"
        else f"ibge:core:{estado['versao_core']}"
    )
    cursor = assinar_cursor(b"s" * 48, rota, resumir_filtros(identidade), geracao, chaves)
    resposta = api_ibge.get(
        caminho,
        params={**filtros.model_dump(exclude={"cursor"}, exclude_none=True), "cursor": cursor},
    )
    assert resposta.status_code == 422, resposta.text
    assert resposta.json()["erro"]["codigo"] == "CURSOR_INVALIDO"


@pytest.mark.parametrize("nivel", ["ufs", "regioes"])
def test_totais_paginam_sem_repetir_territorios(api_ibge, nivel):
    primeira = api_ibge.get(f"/api/v1/populacao/{nivel}", params={"ano": 2025, "limite": 1})
    assert primeira.status_code == 200, primeira.text
    cursor = primeira.json()["pagina"]["proximo_cursor"]
    assert cursor
    segunda = api_ibge.get(
        f"/api/v1/populacao/{nivel}", params={"ano": 2025, "limite": 1, "cursor": cursor}
    )
    assert segunda.status_code == 200, segunda.text
    campo = "uf_codigo" if nivel == "ufs" else "regiao_codigo"
    assert primeira.json()["data"][0][campo] < segunda.json()["data"][0][campo]


def test_catalogo_ufs_e_municipio_detalhado(api_ibge):
    assert len(api_ibge.get("/api/v1/ufs").json()["data"]) == 27
    resposta = api_ibge.get("/api/v1/municipios/3550308")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["data"]["codigo_ibge"] == "3550308"


def test_ano_futuro_e_recurso_populacional_ausente(api_ibge):
    assert api_ibge.get("/api/v1/populacao/brasil?ano=9999").status_code == 422
    assert api_ibge.get("/api/v1/municipios/9999999/populacao").status_code == 404


def test_filtro_uf_ausente_e_aceito():
    assert FiltrosMunicipios(uf=None).uf is None
