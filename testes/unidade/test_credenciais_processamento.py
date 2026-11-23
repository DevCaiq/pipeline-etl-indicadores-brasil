"""Credenciais locais são opt-in e nunca aparecem na representação."""

from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy.engine import make_url

from pipeline_etl.banco.credenciais import resolver_url_processamento


def test_codifica_senha_local_sem_reutilizar_admin(tmp_path: Path) -> None:
    arquivo = tmp_path / ".env.banco"
    arquivo.write_text("SENHA_BANCO_PROCESSAMENTO='senha@/:%'\nSENHA_BANCO_ADMIN=outro\n")
    segredo = resolver_url_processamento(None, arquivo)
    endereco = make_url(segredo.get_secret_value())
    assert endereco.username == "processamento"
    assert endereco.password == "senha@/:%"
    assert endereco.port == 55432
    assert "senha@" not in repr(segredo)


def test_url_explicita_nao_exige_arquivo() -> None:
    segredo = SecretStr("postgresql+psycopg://processamento:senha@localhost/etl")
    assert resolver_url_processamento(segredo, None) is segredo


@pytest.mark.parametrize("ambigua", [False, True])
def test_rejeita_ausencia_ou_duas_fontes(tmp_path: Path, ambigua: bool) -> None:
    with pytest.raises(ValueError):
        resolver_url_processamento(
            SecretStr("url") if ambigua else None, tmp_path / ".env" if ambigua else None
        )


def test_rejeita_arquivo_sem_senha_de_processamento(tmp_path: Path) -> None:
    arquivo = tmp_path / ".env"
    arquivo.write_text("SENHA_BANCO_ADMIN=nao_usar\n")
    with pytest.raises(ValueError):
        resolver_url_processamento(None, arquivo)


def test_publicador_usa_senha_propria_sem_recorrer_a_processamento(tmp_path):
    from pipeline_etl.banco.credenciais import resolver_url_publicador

    arquivo = tmp_path / ".env.banco"
    arquivo.write_text("SENHA_BANCO_PUBLICADOR='segredo@/:%'\nSENHA_BANCO_PROCESSAMENTO=outro\n")
    endereco = make_url(resolver_url_publicador(None, arquivo).get_secret_value())
    assert endereco.username == "publicador" and endereco.password == "segredo@/:%"
    with pytest.raises(ValueError):
        resolver_url_publicador(
            SecretStr("postgresql+psycopg://publicador:senha@localhost/etl"), arquivo
        )


def test_publicador_sem_credenciais_nao_faz_fallback(tmp_path):
    from pipeline_etl.banco.credenciais import resolver_url_publicador

    with pytest.raises(ValueError):
        resolver_url_publicador(None, None)
    arquivo = tmp_path / ".env.banco"
    arquivo.write_text("SENHA_BANCO_PROCESSAMENTO=outra\n")
    with pytest.raises(ValueError):
        resolver_url_publicador(None, arquivo)
