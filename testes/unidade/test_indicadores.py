"""Referência Decimal e representação pública de indicadores."""

from datetime import date
from decimal import Decimal

import pytest

from pipeline_etl.processamento.contratos.bcb import ObservacaoSGS
from pipeline_etl.processamento.indicadores import compor_ipca, formatar_decimal


def test_composto_difere_da_soma_e_preserva_precisao():
    observacoes = [ObservacaoSGS(data=f"01/{mes:02d}/2020", valor="1") for mes in range(1, 13)]
    resultado = compor_ipca(observacoes, date(2020, 12, 1))
    assert resultado.completo
    assert resultado.valor == Decimal("12.682503013196972066120100")


def test_lacuna_nao_e_substituida_por_observacao_fora_da_janela():
    observacoes = [ObservacaoSGS(data=f"01/{mes:02d}/2020", valor="1") for mes in range(1, 12)]
    observacoes.append(ObservacaoSGS(data="01/12/2019", valor="1"))
    resultado = compor_ipca(observacoes, date(2020, 12, 1))
    assert resultado.valor is None and not resultado.completo
    assert resultado.motivo == "MESES_AUSENTES"


@pytest.mark.parametrize(
    "valor,esperado",
    [
        (None, None),
        (Decimal("1.2345665"), "1.234566"),
        (Decimal("1.2345675"), "1.234568"),
        (Decimal("-0.1"), "-0.100000"),
    ],
)
def test_arredonda_somente_na_representacao(valor, esperado):
    assert formatar_decimal(valor) == esperado


def test_recusa_mes_duplicado_e_data_nao_normalizada():
    for datas in [("01/01/2020", "01/01/2020"), ("02/01/2020",)]:
        with pytest.raises(ValueError):
            compor_ipca([ObservacaoSGS(data=data, valor="1") for data in datas], date(2020, 12, 1))


@pytest.mark.parametrize("valor", ["NaN", "Infinity", "-Infinity"])
def test_representacao_rejeita_medida_nao_finita(valor):
    with pytest.raises(ValueError):
        formatar_decimal(Decimal(valor))
