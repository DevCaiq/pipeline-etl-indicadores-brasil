"""Planejamento determinístico de intervalos de coleta e revisão."""

from datetime import date

import pytest

from pipeline_etl.processamento.incremental import planejar_atualizacao


def test_diario_recua_trinta_dias_da_observacao_e_cobre_ate_hoje():
    plano = planejar_atualizacao(
        432,
        "incremental",
        date(2026, 11, 18),
        ultima_observacao=date(2026, 11, 16),
        fim_coberto=date(2026, 11, 17),
    )
    assert plano.inicio == date(2026, 10, 17) and plano.fim == date(2026, 11, 18)


def test_ipca_recua_meses_calendario_sem_aproximar_por_dias():
    plano = planejar_atualizacao(
        433,
        "incremental",
        date(2026, 3, 1),
        ultima_observacao=date(2026, 2, 1),
        fim_coberto=date(2026, 2, 28),
    )
    assert plano.inicio == date(2024, 2, 1)
    assert plano.janelas == (
        (date(2024, 2, 1), date(2024, 12, 31)),
        (date(2025, 1, 1), date(2025, 12, 31)),
        (date(2026, 1, 1), date(2026, 3, 1)),
    )


def test_recorte_inicial_nao_expoe_apoio_como_inicio_publico():
    plano = planejar_atualizacao(
        433,
        "incremental",
        date(2020, 2, 1),
        ultima_observacao=date(2020, 1, 1),
        fim_coberto=date(2020, 1, 31),
    )
    assert plano.inicio == date(2020, 1, 1)


def test_sem_checkpoint_exige_carga_historica():
    with pytest.raises(ValueError, match="SEM_CHECKPOINT"):
        planejar_atualizacao(432, "incremental", date(2026, 11, 18))


def test_reconciliacao_independe_de_checkpoint_e_cobre_desde2020():
    plano = planejar_atualizacao(1, "reconciliacao", date(2021, 2, 1))
    assert plano.janelas == (
        (date(2020, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2021, 2, 1)),
    )


@pytest.mark.parametrize(
    "codigo,modo,inicio,fim",
    [
        (2, "reconciliacao", None, None),
        (432, "outro", None, None),
        (432, "carga-historica", None, None),
        (432, "incremental", date(2020, 1, 1), None),
        (432, "reconciliacao", None, date(2020, 1, 1)),
        (432, "carga-historica", date(2019, 1, 1), date(2020, 1, 1)),
        (432, "carga-historica", date(2020, 2, 1), date(2020, 1, 1)),
        (432, "carga-historica", date(2020, 1, 1), date(2027, 1, 1)),
    ],
)
def test_rejeita_contextos_invalidos(codigo, modo, inicio, fim):
    with pytest.raises(ValueError):
        planejar_atualizacao(codigo, modo, date(2026, 11, 18), inicio=inicio, fim=fim)


@pytest.mark.parametrize(
    "ultima,cobertura",
    [
        (date(2027, 1, 1), date(2027, 1, 1)),
        (date(2026, 11, 18), date(2026, 11, 17)),
        (date(2019, 1, 1), date(2026, 1, 1)),
        (date(2026, 1, 1), None),
    ],
)
def test_rejeita_checkpoint_inconsistente(ultima, cobertura):
    with pytest.raises(ValueError):
        planejar_atualizacao(
            432, "incremental", date(2026, 11, 18), ultima_observacao=ultima, fim_coberto=cobertura
        )
