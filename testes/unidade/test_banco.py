"""Validação de credenciais antes de abrir conexões."""

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import make_url

from pipeline_etl.configuracao import ConfiguracaoAplicacao


def test_aceita_url_postgresql_sem_expor_senha() -> None:
    configuracao = ConfiguracaoAplicacao(
        url_banco_api="postgresql+psycopg://api_leitura:segredo-local@localhost:55432/etl"
    )
    assert isinstance(configuracao.url_banco_api, SecretStr)
    assert "segredo-local" not in repr(configuracao)


@pytest.mark.parametrize(
    "url",
    ["sqlite:///local.db", "postgresql://usuario:senha@localhost/etl", "texto", ""],
)
def test_rejeita_url_incompativel(url: str) -> None:
    with pytest.raises(ValidationError):
        ConfiguracaoAplicacao(url_banco_migracoes=url)


def test_monta_url_com_senha_contendo_caracteres_reservados() -> None:
    configuracao = ConfiguracaoAplicacao(
        host_banco_migracoes="banco", senha_banco_migracoes="senha@exemplo/:%"
    )
    endereco = make_url(configuracao.obter_url_migracoes().get_secret_value())
    assert endereco.host == "banco"
    assert endereco.password == "senha@exemplo/:%"
    assert endereco.database == "etl"


@pytest.mark.parametrize(
    "valores",
    [
        {"host_banco_migracoes": "banco"},
        {"senha_banco_migracoes": "senha"},
        {
            "url_banco_migracoes": "postgresql+psycopg://usuario:senha@localhost/etl",
            "host_banco_migracoes": "banco",
            "senha_banco_migracoes": "senha",
        },
    ],
)
def test_rejeita_credencial_incompleta_ou_ambigua(valores: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        ConfiguracaoAplicacao(**valores)


def test_migracao_exige_credencial_somente_ao_executar() -> None:
    with pytest.raises(ValueError, match="Defina"):
        ConfiguracaoAplicacao().obter_url_migracoes()


def test_migracao_aceita_url_explicita() -> None:
    configuracao = ConfiguracaoAplicacao(
        url_banco_migracoes="postgresql+psycopg://migracoes:senha@localhost:55432/etl"
    )
    assert make_url(configuracao.obter_url_migracoes().get_secret_value()).port == 55432
