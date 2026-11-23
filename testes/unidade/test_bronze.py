"""Persistência real no filesystem temporário, com checksums e publicação exclusiva."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.tipos import RespostaBCB


def resposta_original(corpo: bytes = b"{json invalido") -> RespostaBCB:
    return RespostaBCB(
        432,
        corpo,
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados",
        {"formato": "json", "dataInicial": "02/01/2020", "dataFinal": "06/01/2020"},
        200,
        datetime(2026, 11, 18, tzinfo=UTC),
        "application/json",
        None,
    )


def test_guarda_bytes_antes_de_qualquer_parse(tmp_path: Path) -> None:
    armazenamento = ArmazenamentoBronze(tmp_path)
    resposta = resposta_original()
    identificador = uuid4()
    artefato = armazenamento.salvar(resposta, identificador, resposta.coletado_em)
    assert artefato.caminho_corpo.read_bytes() == resposta.corpo
    metadados = json.loads(artefato.caminho_metadados.read_text(encoding="utf-8"))
    assert metadados["sha256"] == sha256(resposta.corpo).hexdigest()
    assert metadados["execucao_id"] == str(identificador)
    assert metadados["descompressao_automatica"] is False
    assert armazenamento.ler_corpo(artefato.caminho_metadados) == resposta.corpo


def test_detecta_corrupcao_do_corpo(tmp_path: Path) -> None:
    armazenamento = ArmazenamentoBronze(tmp_path)
    resposta = resposta_original()
    artefato = armazenamento.salvar(resposta, uuid4(), resposta.coletado_em)
    artefato.caminho_corpo.write_bytes(b"alterado")
    with pytest.raises(ValueError, match="checksum"):
        armazenamento.ler_corpo(artefato.caminho_metadados)


def test_manifesto_nao_sobrescreve_execucao(tmp_path: Path) -> None:
    armazenamento = ArmazenamentoBronze(tmp_path)
    resposta = resposta_original()
    identificador = uuid4()
    artefato = armazenamento.salvar(resposta, identificador, resposta.coletado_em)
    argumentos = (
        432,
        identificador,
        resposta.coletado_em,
        date(2020, 1, 2),
        date(2020, 1, 6),
        [artefato],
    )
    manifesto = armazenamento.salvar_manifesto(*argumentos)
    original = manifesto.read_bytes()
    with pytest.raises(FileExistsError):
        armazenamento.salvar_manifesto(*argumentos)
    assert manifesto.read_bytes() == original
    assert not list(tmp_path.rglob("*.tmp"))


def test_nao_publica_manifesto_com_artefato_ausente(tmp_path: Path) -> None:
    armazenamento = ArmazenamentoBronze(tmp_path)
    resposta = resposta_original()
    identificador = uuid4()
    artefato = armazenamento.salvar(resposta, identificador, resposta.coletado_em)
    artefato.caminho_corpo.unlink()
    with pytest.raises(OSError):
        armazenamento.salvar_manifesto(
            432, identificador, resposta.coletado_em, date(2020, 1, 2), date(2020, 1, 6), [artefato]
        )
    assert not list(tmp_path.rglob("manifest.json"))


def test_recusa_leitura_fora_da_raiz(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="raiz"):
        ArmazenamentoBronze(tmp_path / "bronze").ler_corpo(tmp_path / "fora.json")


def test_recusa_travessia_em_metadados(tmp_path: Path) -> None:
    armazenamento = ArmazenamentoBronze(tmp_path)
    caminho = tmp_path / "falso.meta.json"
    caminho.write_text(json.dumps({"caminho_corpo": "../fora", "sha256": "x", "tamanho_bytes": 1}))
    with pytest.raises(ValueError, match="raiz"):
        armazenamento.ler_corpo(caminho)


@pytest.mark.parametrize("alteracao", ["corpo", "tamanho", "travessia"])
def test_manifesto_rejeita_referencia_diferente_dos_metadados(
    tmp_path: Path, alteracao: str
) -> None:
    armazenamento = ArmazenamentoBronze(tmp_path)
    resposta = resposta_original()
    identificador = uuid4()
    artefato = armazenamento.salvar(resposta, identificador, resposta.coletado_em)
    if alteracao == "corpo":
        artefato = replace(artefato, caminho_corpo=tmp_path / "inexistente.body")
    elif alteracao == "tamanho":
        artefato = replace(artefato, tamanho_bytes=999)
    else:
        artefato = replace(
            artefato, caminho_corpo=artefato.caminho_corpo.parent / ".." / "inexistente.body"
        )
    with pytest.raises(ValueError):
        armazenamento.salvar_manifesto(
            432, identificador, resposta.coletado_em, date(2020, 1, 2), date(2020, 1, 6), [artefato]
        )
    assert not list(tmp_path.rglob("manifest.json"))


@pytest.mark.parametrize(
    "conteudo",
    [[], {}, {"caminho_corpo": 5}, {"caminho_corpo": "a.body", "sha256": "x", "tamanho_bytes": 1}],
)
def test_rejeita_metadados_invalidos_sem_ler_outro_arquivo(
    tmp_path: Path, conteudo: object
) -> None:
    caminho = tmp_path / "invalido.meta.json"
    caminho.write_text(json.dumps(conteudo))
    with pytest.raises(ValueError):
        ArmazenamentoBronze(tmp_path).ler_corpo(caminho)
