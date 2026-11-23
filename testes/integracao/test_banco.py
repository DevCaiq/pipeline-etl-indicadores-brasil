"""Migrações, transações e permissões contra PostgreSQL exclusivo de testes."""

import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from pipeline_etl.banco.sessoes import abrir_sessao, criar_motor
from testes.conftest import banco

pytestmark = pytest.mark.integracao
RAIZ = Path(__file__).resolve().parents[2]


def test_cria_schemas_e_catalogo(banco: Engine) -> None:
    assert {"ops", "core", "mart"}.issubset(inspect(banco).get_schema_names())
    with banco.connect() as conexao:
        series = conexao.execute(text("SELECT codigo_sgs FROM core.dim_serie")).scalars().all()
    assert set(series) == {432, 433, 1}


def test_sessao_confirma_e_reverte_transacao(banco: Engine) -> None:
    identificador = uuid4()
    with abrir_sessao(banco) as sessao:
        sessao.execute(
            text("INSERT INTO ops.execucao (execucao_id, modo) VALUES (:id, 'teste')"),
            {"id": identificador},
        )
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT count(*) FROM ops.execucao WHERE execucao_id=:id"),
                {"id": identificador},
            )
            == 1
        )
    with pytest.raises(RuntimeError), abrir_sessao(banco) as sessao:
        sessao.execute(
            text("DELETE FROM ops.execucao WHERE execucao_id=:id"), {"id": identificador}
        )
        raise RuntimeError("Falha de etapa simulada")
    with banco.begin() as conexao:
        assert (
            conexao.scalar(
                text("SELECT count(*) FROM ops.execucao WHERE execucao_id=:id"),
                {"id": identificador},
            )
            == 1
        )
        conexao.execute(
            text("DELETE FROM ops.execucao WHERE execucao_id=:id"), {"id": identificador}
        )


def test_rejeita_status_invalido(banco: Engine) -> None:
    with pytest.raises(IntegrityError), banco.begin() as conexao:
        conexao.execute(
            text("INSERT INTO ops.execucao (modo, situacao) VALUES ('teste','INVALIDA')")
        )


def test_chave_estrangeira_impede_observacao_sem_lote(banco: Engine) -> None:
    with pytest.raises(IntegrityError), banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie (codigo_sgs,data,valor,lote_id) "
                "VALUES (1,'2020-01-02',:valor,:lote)"
            ),
            {"valor": Decimal("4.0213"), "lote": uuid4()},
        )


@pytest.mark.parametrize("usuario", ["api_leitura", "processamento"])
def test_papeis_nao_criam_tabelas(banco: Engine, usuario: str) -> None:
    variavel = (
        "SENHA_BANCO_API_TESTES" if usuario == "api_leitura" else "SENHA_BANCO_PROCESSAMENTO_TESTES"
    )
    senha = os.environ.get(variavel)
    assert senha, f"Defina {variavel} para testar permissões reais."
    endereco = banco.url.set(username=usuario, password=senha)
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    try:
        with pytest.raises(DBAPIError) as erro, motor.begin() as conexao:
            conexao.execute(text("CREATE TABLE core.nao_permitida (id integer)"))
        assert getattr(erro.value.orig, "sqlstate", None) == "42501"
        with motor.connect() as conexao:
            assert conexao.scalar(text("SELECT count(*) FROM core.dim_serie")) == 3
    finally:
        motor.dispose()


def test_api_nao_altera_catalogo(banco: Engine) -> None:
    senha = os.environ.get("SENHA_BANCO_API_TESTES")
    assert senha, "Defina SENHA_BANCO_API_TESTES."
    endereco = banco.url.set(username="api_leitura", password=senha)
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    try:
        with pytest.raises(DBAPIError) as erro, motor.begin() as conexao:
            conexao.execute(text("UPDATE core.dim_serie SET nome='Alterado' WHERE codigo_sgs=1"))
        assert getattr(erro.value.orig, "sqlstate", None) == "42501"
    finally:
        motor.dispose()


def test_downgrade_e_upgrade_em_banco_exclusivo(banco: Engine) -> None:
    configuracao = Config(str(RAIZ / "alembic.ini"))
    with banco.begin() as conexao:
        configuracao.attributes["conexao"] = conexao
        command.downgrade(configuracao, "base")
        assert not inspect(conexao).has_table("dim_serie", schema="core")
        command.upgrade(configuracao, "head")
        assert conexao.scalar(text("SELECT count(*) FROM core.dim_serie")) == 3


def test_preserva_decimal_e_impede_duplicata(banco: Engine) -> None:
    with pytest.raises(IntegrityError) as erro, banco.begin() as conexao:
        execucao = conexao.scalar(
            text("INSERT INTO ops.execucao (modo) VALUES ('teste') RETURNING execucao_id")
        )
        lote = conexao.scalar(
            text(
                "INSERT INTO ops.lote (execucao_id,fonte,chave,janela_inicio,janela_fim,manifesto) "
                "VALUES (:execucao,'bcb','1','2020-01-01','2020-01-31','teste.json') "
                "RETURNING lote_id"
            ),
            {"execucao": execucao},
        )
        comando = text(
            "INSERT INTO core.fato_serie (codigo_sgs,data,valor,lote_id) "
            "VALUES (1,'2020-01-02',:valor,:lote)"
        )
        conexao.execute(comando, {"valor": Decimal("4.0213"), "lote": lote})
        assert conexao.scalar(
            text("SELECT valor FROM core.fato_serie WHERE codigo_sgs=1 AND data='2020-01-02'")
        ) == Decimal("4.0213000000")
        conexao.execute(comando, {"valor": Decimal("4.0213"), "lote": lote})
    assert getattr(erro.value.orig, "sqlstate", None) == "23505"


def test_processamento_escreve_sem_privilegio_administrativo(banco: Engine) -> None:
    senha = os.environ.get("SENHA_BANCO_PROCESSAMENTO_TESTES")
    assert senha
    endereco = banco.url.set(username="processamento", password=senha)
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    try:
        with motor.connect() as conexao, conexao.begin():
            identificador = conexao.scalar(
                text("INSERT INTO ops.execucao (modo) VALUES ('teste') RETURNING execucao_id")
            )
            assert identificador is not None
            conexao.execute(
                text("DELETE FROM ops.execucao WHERE execucao_id=:id"), {"id": identificador}
            )
    finally:
        motor.dispose()


def test_api_acessa_view_sem_acessar_erro_interno(banco: Engine) -> None:
    senha = os.environ.get("SENHA_BANCO_API_TESTES")
    assert senha
    endereco = banco.url.set(username="api_leitura", password=senha)
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    try:
        with motor.connect() as conexao:
            resultado = conexao.execute(text("SELECT * FROM ops.v_execucoes"))
            campos = list(resultado.keys())
            assert "erro" not in campos
        with pytest.raises(DBAPIError) as erro, motor.begin() as conexao:
            conexao.execute(text("SELECT erro FROM ops.execucao"))
        assert getattr(erro.value.orig, "sqlstate", None) == "42501"
    finally:
        motor.dispose()


def test_recusa_outro_banco_mesmo_com_sufixo_testes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "URL_BANCO_TESTES", "postgresql+psycopg://usuario:senha@127.0.0.1:1/outro_projeto_testes"
    )
    with pytest.raises(pytest.fail.Exception, match="etl_testes"):
        next(banco.__wrapped__())
