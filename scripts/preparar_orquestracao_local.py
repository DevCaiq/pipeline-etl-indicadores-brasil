"""Preparo retomável do banco/papel próprios do Prefect, sem regenerar senhas."""

import os
from pathlib import Path
from secrets import token_hex

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from sqlalchemy import URL
from sqlalchemy.engine import make_url


def executar() -> int:
    raiz = Path(__file__).resolve().parents[1]
    arquivo = raiz / ".env.orquestracao"
    if not arquivo.exists():
        endereco = URL.create(
            "postgresql+asyncpg",
            username="orquestracao_etl",
            password=token_hex(32),
            host="127.0.0.1",
            port=55432,
            database="prefect_etl",
        )
        # A credencial fica durável antes de qualquer alteração no PostgreSQL.
        with arquivo.open("x", encoding="utf-8") as saida:
            saida.write(
                "PREFECT_API_DATABASE_CONNECTION_URL="
                + endereco.render_as_string(hide_password=False)
                + "\n"
            )
            saida.flush()
            os.fsync(saida.fileno())
    endereco = make_url(
        dotenv_values(arquivo, interpolate=False).get("PREFECT_API_DATABASE_CONNECTION_URL") or ""
    )
    if (
        endereco.database != "prefect_etl"
        or endereco.username != "orquestracao_etl"
        or endereco.host != "127.0.0.1"
        or endereco.port != 55432
        or not endereco.password
    ):
        raise ValueError("Configuração deve usar banco e papel exclusivos da orquestração.")
    credenciais = dotenv_values(raiz / ".env.banco", interpolate=False)
    with psycopg.connect(
        host="127.0.0.1",
        port=55432,
        dbname="postgres",
        user="administrador",
        password=credenciais["SENHA_BANCO_ADMIN"],
        autocommit=True,
        connect_timeout=5,
    ) as conexao:
        papel = conexao.execute(
            "SELECT 1 FROM pg_roles WHERE rolname='orquestracao_etl'"
        ).fetchone()
        if papel is None:
            conexao.execute(
                sql.SQL("CREATE ROLE orquestracao_etl LOGIN PASSWORD {}").format(
                    sql.Literal(endereco.password)
                )
            )
        else:
            # Autentica a senha salva; nunca redefine a senha de um papel existente.
            with psycopg.connect(
                host="127.0.0.1",
                port=55432,
                dbname="postgres",
                user="orquestracao_etl",
                password=endereco.password,
                connect_timeout=5,
            ):
                pass
        banco = conexao.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='prefect_etl'"
        ).fetchone()
        if banco is None:
            conexao.execute("CREATE DATABASE prefect_etl OWNER orquestracao_etl TEMPLATE template0")
        elif banco[0] != "orquestracao_etl":
            raise RuntimeError("Banco existente tem outro proprietário; operação cancelada.")
        conexao.execute("REVOKE ALL ON DATABASE prefect_etl FROM PUBLIC")
        conexao.execute("GRANT CONNECT ON DATABASE prefect_etl TO orquestracao_etl")
        conexao.execute("REVOKE CONNECT ON DATABASE etl FROM orquestracao_etl")
    print("Banco/papel Prefect preparados; credenciais existentes preservadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
