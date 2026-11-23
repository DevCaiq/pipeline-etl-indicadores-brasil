"""Ambiente local do SDK, sem arquivos pessoais ou telemetria externa."""

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parents[1]


def configurar_ambiente(servidor: bool = False) -> None:
    diretorio = RAIZ / ".cache/prefect"
    diretorio.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        {
            "PREFECT_HOME": str(diretorio),
            "PREFECT_API_URL": "http://127.0.0.1:4200/api",
            "PREFECT_PROFILES_PATH": str(diretorio / "profiles.toml"),
            "PREFECT_SERVER_ANALYTICS_ENABLED": "false",
            "PREFECT_API_ENABLE_HTTP2": "false",
        }
    )
    if servidor:
        configuracao = dotenv_values(RAIZ / ".env.orquestracao", interpolate=False)
        endereco = configuracao.get("PREFECT_API_DATABASE_CONNECTION_URL")
        if not endereco:
            raise ValueError("Prepare .env.orquestracao antes de iniciar o servidor.")
        url = make_url(endereco)
        if (
            url.database != "prefect_etl"
            or url.username != "orquestracao_etl"
            or url.host != "127.0.0.1"
            or url.port != 55432
            or url.drivername != "postgresql+asyncpg"
        ):
            raise ValueError("Prefect exige seu banco e papel exclusivos em loopback.")
        os.environ["PREFECT_API_DATABASE_CONNECTION_URL"] = endereco
    else:
        os.environ.pop("PREFECT_API_DATABASE_CONNECTION_URL", None)
