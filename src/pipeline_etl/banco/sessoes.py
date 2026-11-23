"""Conexões síncronas e fronteira transacional explícita."""

from collections.abc import Iterator
from contextlib import contextmanager

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def criar_motor(url: SecretStr) -> Engine:
    """Cria pool sem conectar imediatamente e sem registrar parâmetros SQL."""
    return create_engine(
        url.get_secret_value(),
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 5},
    )


@contextmanager
def abrir_sessao(motor: Engine) -> Iterator[Session]:
    """Confirma ao concluir ou reverte automaticamente quando a etapa falha."""
    with Session(motor) as sessao, sessao.begin():
        yield sessao
