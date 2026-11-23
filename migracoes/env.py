"""Ambiente Alembic; nomes obrigatórios da ferramenta são preservados."""

from alembic import context
from sqlalchemy import Connection

from pipeline_etl.banco import modelos_ibge  # noqa: F401 - registra metadados IBGE
from pipeline_etl.banco.modelos import BaseModelo
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao


def aplicar_migracoes(conexao: Connection) -> None:
    """Executa revisões usando transação gerenciada pelo Alembic."""
    context.configure(connection=conexao, target_metadata=BaseModelo.metadata, include_schemas=True)
    with context.begin_transaction():
        context.run_migrations()


def executar() -> None:
    """Aceita conexão de teste ou carrega credencial própria do migrador."""
    conexao = context.config.attributes.get("conexao")
    if conexao is not None:
        aplicar_migracoes(conexao)
        return
    configuracao = ConfiguracaoAplicacao()
    motor = criar_motor(configuracao.obter_url_migracoes())
    try:
        with motor.connect() as conexao:
            aplicar_migracoes(conexao)
    finally:
        motor.dispose()


executar()
