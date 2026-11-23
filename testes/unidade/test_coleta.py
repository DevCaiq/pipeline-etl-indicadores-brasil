"""Fluxo de coleta e manifestos, sem banco ou API externa."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie, dividir_janelas
from pipeline_etl.processamento.erros import ErroColeta


def test_divide_anos_sem_repetir_limites() -> None:
    assert list(dividir_janelas(date(2019, 12, 31), date(2021, 1, 1))) == [
        (date(2019, 12, 31), date(2019, 12, 31)),
        (date(2020, 1, 1), date(2020, 12, 31)),
        (date(2021, 1, 1), date(2021, 1, 1)),
    ]


def test_manifesto_referencia_todas_as_janelas(tmp_path: Path) -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return httpx.Response(200, stream=httpx.ByteStream(b"[]"))

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        manifesto = coletar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            1,
            date(2020, 12, 31),
            date(2021, 1, 1),
        )
    dados = json.loads(manifesto.read_text())
    assert dados["situacao"] == "COLETADA"
    assert len(dados["artefatos"]) == len(chamadas) == 2
    assert all((tmp_path / item["corpo"]).exists() for item in dados["artefatos"])


def test_falha_na_segunda_janela_preserva_primeira(tmp_path: Path) -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return httpx.Response(200 if len(chamadas) == 1 else 404, stream=httpx.ByteStream(b"[]"))

    with (
        httpx.Client(transport=httpx.MockTransport(responder)) as transporte,
        pytest.raises(ErroColeta) as erro,
    ):
        coletar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            1,
            date(2020, 12, 31),
            date(2021, 1, 1),
        )
    assert erro.value.manifesto is not None
    dados = json.loads(erro.value.manifesto.read_text())
    assert dados["situacao"] == "INCOMPLETA"
    assert len(dados["artefatos"]) == 1


def test_ipca_inclui_apoio_para_janeiro_2020(tmp_path: Path) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=httpx.ByteStream(b"[]")))
    ) as transporte:
        manifesto = coletar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            433,
            date(2020, 1, 1),
            date(2020, 1, 31),
        )
    dados = json.loads(manifesto.read_text())
    assert dados["inicio"] == "2020-01-01"
    assert dados["inicio_coleta"] == "2019-02-01"
    assert len(dados["artefatos"]) == 2


def test_periodo_invalido_nao_cria_arquivos(tmp_path: Path) -> None:
    with httpx.Client() as transporte, pytest.raises(ValueError):
        coletar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            1,
            date(2019, 1, 1),
            date(2020, 1, 1),
        )
    assert not list(tmp_path.iterdir())


def test_falha_ao_gravar_nao_publica_coleta_concluida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def impedir_publicacao(origem: object, destino: object) -> None:
        raise OSError("Falha de disco simulada")

    monkeypatch.setattr(
        "pipeline_etl.processamento.armazenamento.arquivos.os.link", impedir_publicacao
    )
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, stream=httpx.ByteStream(b"[]"))
            )
        ) as transporte,
        pytest.raises(ErroColeta, match="manifesto"),
    ):
        coletar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            1,
            date(2020, 1, 2),
            date(2020, 1, 6),
        )
    assert not list(tmp_path.rglob("manifest.json"))
    assert not list(tmp_path.rglob("*.tmp"))
