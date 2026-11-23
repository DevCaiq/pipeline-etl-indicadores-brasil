"""Filtros públicos IBGE limitam períodos e preservam busca literal."""

import pytest
from pydantic import ValidationError

from pipeline_etl.api.ibge import FiltrosMunicipios, FiltrosPopulacao


def test_normaliza_uf_e_busca():
    filtros = FiltrosMunicipios(uf=" sp ", q=" São Paulo ")
    assert filtros.uf == "SP" and filtros.q == "São Paulo"


@pytest.mark.parametrize("parametros", [{"uf": "ZZ"}, {"q": "a"}, {"limite": 0}])
def test_rejeita_filtro_municipal_invalido(parametros):
    with pytest.raises(ValidationError):
        FiltrosMunicipios(**parametros)


@pytest.mark.parametrize(
    "parametros",
    [{"ano_de": 2019}, {"ano_de": 2026, "ano_ate": 2020}, {"ano_ate": 2099}, {"indicador": 0}],
)
def test_rejeita_periodo_e_indicador_invalidos(parametros):
    with pytest.raises(ValidationError):
        FiltrosPopulacao(**parametros)
