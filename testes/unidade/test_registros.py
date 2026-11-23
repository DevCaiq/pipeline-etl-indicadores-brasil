"""Registros reais, sem mocks de métodos do structlog."""

import json
from datetime import datetime

import pytest
import structlog

from pipeline_etl.registros import configurar_registros


def test_escreve_json_em_stderr_com_contexto(capsys: pytest.CaptureFixture[str]) -> None:
    configurar_registros("INFO")
    structlog.get_logger(servico="coleta").info("Coleta iniciada", execucao_id="execucao-1")
    saidas = capsys.readouterr()
    assert saidas.out == ""
    evento = json.loads(saidas.err)
    assert evento["mensagem"] == "Coleta iniciada"
    assert evento["nivel"] == "info"
    assert evento["servico"] == "coleta"
    assert evento["execucao_id"] == "execucao-1"
    assert datetime.fromisoformat(evento["instante"]).utcoffset().total_seconds() == 0


def test_filtra_nivel_e_nao_duplica_apos_reconfigurar(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configurar_registros("WARNING")
    configurar_registros("WARNING")
    registrador = structlog.get_logger()
    registrador.info("Mensagem omitida")
    registrador.warning("Mensagem importante")
    linhas = capsys.readouterr().err.splitlines()
    assert len(linhas) == 1
    assert json.loads(linhas[0])["mensagem"] == "Mensagem importante"
