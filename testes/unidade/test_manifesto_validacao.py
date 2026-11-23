"""Manifestos não confiáveis são recusados antes da validação dos valores."""

import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie
from pipeline_etl.processamento.manifestos import ler_manifesto


def criar_manifesto(raiz: Path) -> Path:
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, stream=httpx.ByteStream(b'[{"data":"02/01/2020","valor":"4.50"}]')
            )
        )
    ) as transporte:
        return coletar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(raiz),
            432,
            date(2020, 1, 2),
            date(2020, 1, 6),
        )


def test_le_manifesto_e_identidade(tmp_path: Path) -> None:
    caminho = criar_manifesto(tmp_path)
    resultado = ler_manifesto(ArmazenamentoBronze(tmp_path), caminho)
    assert resultado.manifesto.codigo_serie == 432
    assert len(resultado.artefatos) == 1
    assert resultado.artefatos[0].corpo.startswith(b"[")


@pytest.mark.parametrize(
    "alteracao", ["sha", "duplicado", "serie", "janela", "caminho", "incompleta"]
)
def test_rejeita_manifesto_adulterado(tmp_path: Path, alteracao: str) -> None:
    caminho = criar_manifesto(tmp_path)
    dados = json.loads(caminho.read_text())
    if alteracao == "sha":
        dados["artefatos"][0]["sha256"] = "0" * 64
    elif alteracao == "duplicado":
        dados["artefatos"] *= 2
    elif alteracao == "serie":
        dados["codigo_serie"] = 1
    elif alteracao == "janela":
        dados["fim"] = "2021-01-06"
    elif alteracao == "caminho":
        dados["artefatos"][0]["metadados"] = "../fora"
    else:
        dados["situacao"] = "INCOMPLETA"
    caminho.write_text(json.dumps(dados))
    with pytest.raises(ValueError):
        ler_manifesto(ArmazenamentoBronze(tmp_path), caminho)
