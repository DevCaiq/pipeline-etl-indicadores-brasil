"""Transformação sem banco nem rede."""

from datetime import date
from decimal import Decimal

import pytest

from pipeline_etl.processamento.contratos.bcb import ObservacaoSGS
from pipeline_etl.processamento.transformacao import calcular_fim_contiguo, transformar_observacoes


def test_ordena_e_preserva_decimal_sem_preencher_lacunas():
    entradas = [
        ObservacaoSGS(data="03/01/2020", valor="4,2"),
        ObservacaoSGS(data="01/01/2020", valor="4.1"),
    ]
    resultado = transformar_observacoes(entradas)
    assert [(linha.data, linha.valor) for linha in resultado] == [
        (date(2020, 1, 1), Decimal("4.1")),
        (date(2020, 1, 3), Decimal("4.2")),
    ]


def test_recusa_conflito_entre_artefatos():
    with pytest.raises(ValueError):
        transformar_observacoes(
            [
                ObservacaoSGS(data="01/01/2020", valor="1"),
                ObservacaoSGS(data="01/01/2020", valor="2"),
            ]
        )


def test_cobertura_nao_salta_lacuna_e_aceita_sobreposicao():
    base = date(2020, 1, 1)
    assert calcular_fim_contiguo(base, [(date(2020, 1, 2), date(2020, 1, 10))]) is None
    assert calcular_fim_contiguo(
        base,
        [
            (date(2020, 1, 10), date(2020, 1, 15)),
            (base, date(2020, 1, 5)),
            (date(2020, 1, 4), date(2020, 1, 9)),
        ],
    ) == date(2020, 1, 15)
