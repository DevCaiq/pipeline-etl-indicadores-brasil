"""Executa a suíte com PostgreSQL local e banco exclusivo etl_testes."""

import os
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from sqlalchemy import URL


def executar() -> int:
    """Prepara somente o banco de testes e não exibe credenciais."""
    raiz = Path(__file__).resolve().parents[1]
    credenciais = dotenv_values(raiz / ".env.banco")
    nomes = ["ADMIN", "MIGRACOES", "API", "PROCESSAMENTO", "PUBLICADOR"]
    if any(not credenciais.get(f"SENHA_BANCO_{nome}") for nome in nomes):
        print("Preencha .env.banco antes de executar os testes de integração.", file=sys.stderr)
        return 2
    with psycopg.connect(
        host="127.0.0.1",
        port=55432,
        dbname="postgres",
        user="administrador",
        password=credenciais["SENHA_BANCO_ADMIN"],
        autocommit=True,
        connect_timeout=5,
    ) as conexao:
        registro = conexao.execute(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname='etl_testes'"
        ).fetchone()
        if registro is None:
            conexao.execute("CREATE DATABASE etl_testes OWNER migracoes")
        elif registro[0] != "migracoes":
            print(
                "O banco etl_testes não pertence ao papel migracoes; operação cancelada.",
                file=sys.stderr,
            )
            return 2
    endereco = URL.create(
        "postgresql+psycopg",
        username="migracoes",
        password=credenciais["SENHA_BANCO_MIGRACOES"],
        host="127.0.0.1",
        port=55432,
        database="etl_testes",
    )
    ambiente = {
        **os.environ,
        "URL_BANCO_TESTES": endereco.render_as_string(hide_password=False),
        "SENHA_BANCO_PUBLICADOR_TESTES": credenciais["SENHA_BANCO_PUBLICADOR"],
        "SENHA_BANCO_API_TESTES": credenciais["SENHA_BANCO_API"],
        "SENHA_BANCO_PROCESSAMENTO_TESTES": credenciais["SENHA_BANCO_PROCESSAMENTO"],
    }
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--cov", "--cov-report=term-missing", *sys.argv[1:]],
        cwd=raiz,
        env=ambiente,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(executar())
