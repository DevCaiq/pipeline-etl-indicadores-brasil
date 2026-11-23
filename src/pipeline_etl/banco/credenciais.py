"""Resolução explícita de credencial do papel de processamento local."""

from pathlib import Path

from dotenv import dotenv_values
from pydantic import SecretStr
from sqlalchemy import URL


def _resolver_url(url: SecretStr | None, arquivo: Path | None, papel: str) -> SecretStr:
    """Usa URL configurada ou arquivo local opt-in, sem autenticar como admin."""
    variavel = "URL_BANCO_" + papel.upper()
    if url is not None and arquivo is not None:
        raise ValueError(f"Escolha {variavel} ou credenciais locais, não ambos.")
    if url is not None:
        return url
    if arquivo is None:
        raise ValueError(f"Defina {variavel} ou --credenciais-locais.")
    if not arquivo.is_file():
        raise ValueError("Arquivo de credenciais locais não encontrado.")
    senha = dotenv_values(arquivo, interpolate=False).get("SENHA_BANCO_" + papel.upper())
    if not senha or senha == "SUBSTITUIR":
        raise ValueError(f"Arquivo sem senha de {papel} válida.")
    endereco = URL.create(
        "postgresql+psycopg",
        username=papel,
        password=senha,
        host="127.0.0.1",
        port=55432,
        database="etl",
    )
    return SecretStr(endereco.render_as_string(hide_password=False))


def resolver_url_processamento(url: SecretStr | None, arquivo: Path | None) -> SecretStr:
    """Credencial exclusiva do processamento, sem fallback administrativo."""
    return _resolver_url(url, arquivo, "processamento")


def resolver_url_publicador(url: SecretStr | None, arquivo: Path | None) -> SecretStr:
    """Credencial exclusiva do proprietário das visões materializadas."""
    return _resolver_url(url, arquivo, "publicador")
