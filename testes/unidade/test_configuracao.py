"""Contratos de configuração consumida pela aplicação."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from pipeline_etl.configuracao import ConfiguracaoAplicacao


def test_carrega_variaveis_e_normaliza_series(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMBIENTE", "teste")
    monkeypatch.setenv("NIVEL_REGISTROS", "debug")
    monkeypatch.setenv("SERIES_BCB", " 433, 1 ")
    configuracao = ConfiguracaoAplicacao()
    assert configuracao.ambiente == "teste"
    assert configuracao.nivel_registros == "DEBUG"
    assert configuracao.series_bcb == (433, 1)


def test_ambiente_prevalece_sobre_arquivo(monkeypatch: pytest.MonkeyPatch) -> None:
    Path(".env").write_text("AMBIENTE=teste\nSERIES_BCB=433\n", encoding="utf-8")
    monkeypatch.setenv("AMBIENTE", "producao")
    configuracao = ConfiguracaoAplicacao()
    assert configuracao.ambiente == "producao"
    assert configuracao.series_bcb == (433,)


@pytest.mark.parametrize("series", ["", "433,", "11", "1,1", "abc", "432,999"])
def test_rejeita_selecao_de_series_invalida(monkeypatch: pytest.MonkeyPatch, series: str) -> None:
    monkeypatch.setenv("SERIES_BCB", series)
    with pytest.raises(ValidationError):
        ConfiguracaoAplicacao()


@pytest.mark.parametrize(
    ("nome", "valor"),
    [("AMBIENTE", "inexistente"), ("NIVEL_REGISTROS", "qualquer"), ("CAMINHO_BRONZE", " ")],
)
def test_rejeita_configuracao_invalida(
    monkeypatch: pytest.MonkeyPatch, nome: str, valor: str
) -> None:
    monkeypatch.setenv(nome, valor)
    with pytest.raises(ValidationError):
        ConfiguracaoAplicacao()


def test_nao_cria_diretorio_ao_carregar_configuracao() -> None:
    configuracao = ConfiguracaoAplicacao()
    assert configuracao.series_bcb == (432, 433, 1)
    assert not configuracao.caminho_bronze.exists()
