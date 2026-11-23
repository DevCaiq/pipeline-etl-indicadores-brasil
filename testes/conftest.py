"""Isolamento de configuração e registros para testes sem rede."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from pipeline_etl.banco.sessoes import criar_motor


@pytest.fixture(autouse=True)
def isolar_ambiente(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    """Evita ler configuração pessoal ou compartilhar registros entre testes."""
    for nome in (
        "AMBIENTE",
        "SEGREDO_CURSOR",
        "LIMITE_REQUISICOES_MINUTO",
        "NIVEL_REGISTROS",
        "CAMINHO_BRONZE",
        "SERIES_BCB",
        "URL_BANCO_API",
        "URL_BANCO_PUBLICADOR",
        "URL_BANCO_PROCESSAMENTO",
        "URL_BANCO_MIGRACOES",
        "HOST_BANCO_MIGRACOES",
        "SENHA_BANCO_MIGRACOES",
    ):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.chdir(tmp_path)
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def banco() -> Iterator[Engine]:
    endereco = os.environ.get("URL_BANCO_TESTES")
    if not endereco:
        pytest.skip("Defina URL_BANCO_TESTES para executar integração PostgreSQL.")
    if make_url(endereco).database != "etl_testes":
        pytest.fail("Integração exige exatamente o banco exclusivo etl_testes.")
    motor = criar_motor(SecretStr(endereco))
    configuracao = Config(str(RAIZ / "alembic.ini"))
    try:
        with motor.begin() as conexao:
            configuracao.attributes["conexao"] = conexao
            command.upgrade(configuracao, "head")
        yield motor
    finally:
        motor.dispose()
