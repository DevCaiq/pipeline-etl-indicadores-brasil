"""Coordenação IBGE: coleta completa antes da carga e publicação condicionada."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline_etl.processamento import pipeline_ibge


def test_descobre_anos_e_so_publica_depois_de_carga_valida(monkeypatch):
    coletor = Mock()
    coletor.coletar.side_effect = lambda recurso, ano=None: SimpleNamespace(
        situacao="COLETADA", manifesto=(recurso, ano)
    )
    monkeypatch.setattr(pipeline_ibge, "ler_coleta", lambda *_: SimpleNamespace(corpo=b"[]"))
    monkeypatch.setattr(pipeline_ibge, "descobrir_periodos", lambda _: (2020, 2024))
    carga = Mock(return_value=SimpleNamespace(situacao="SUCESSO"))
    publicacao = Mock(return_value=SimpleNamespace(situacao="SUCESSO"))
    monkeypatch.setattr(pipeline_ibge, "carregar_ibge", carga)
    monkeypatch.setattr(pipeline_ibge, "publicar_ibge", publicacao)
    resultado = pipeline_ibge.executar_ibge(coletor, "bronze", "carga", "gold")
    assert resultado.situacao == "SUCESSO"
    assert carga.call_args.args[1][-2:] == (("populacao", 2020), ("populacao", 2024))
    publicacao.assert_called_once_with("gold")


def test_coleta_falha_nao_carrega_nem_publica(monkeypatch):
    coletor = Mock()
    coletor.coletar.return_value = SimpleNamespace(situacao="FALHA", manifesto="evidencia")
    carga = Mock()
    publicacao = Mock()
    monkeypatch.setattr(pipeline_ibge, "carregar_ibge", carga)
    monkeypatch.setattr(pipeline_ibge, "publicar_ibge", publicacao)
    resultado = pipeline_ibge.executar_ibge(coletor, "bronze", "carga", "gold")
    assert resultado.situacao == "FALHA"
    assert resultado.motivo == "COLETA_INCOMPLETA"
    carga.assert_not_called()
    publicacao.assert_not_called()


@pytest.mark.parametrize(
    "modo,esperados",
    [
        ("incremental", (2025, 2026)),
        ("localidades", (2020, 2021, 2024, 2025, 2026)),
        ("reconciliacao", (2020, 2021, 2024, 2025, 2026)),
    ],
)
def test_selecao_periodos_mantem_revisao_mais_recente(modo, esperados):
    disponiveis = (2020, 2021, 2024, 2025, 2026)
    assert pipeline_ibge.selecionar_anos(disponiveis, {2020, 2021, 2024}, modo) == esperados


def test_incremental_com_todos_anos_carregados_revisa_so_ultimo():
    assert pipeline_ibge.selecionar_anos((2020, 2021, 2024), {2020, 2021, 2024}, "incremental") == (
        2024,
    )
