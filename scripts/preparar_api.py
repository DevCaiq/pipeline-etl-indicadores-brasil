"""Gera configuração local de API sem sobrescrever arquivos ou imprimir segredos."""

import secrets
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import URL


def executar() -> int:
    raiz = Path(__file__).resolve().parents[1]
    destino = raiz / ".env.api"
    senha = dotenv_values(raiz / ".env.banco", interpolate=False).get("SENHA_BANCO_API")
    if not senha or senha == "SUBSTITUIR":
        print("Prepare as credenciais do banco antes de configurar a API.")
        return 2
    endereco = URL.create(
        "postgresql+psycopg",
        username="api_leitura",
        password=senha,
        host="127.0.0.1",
        port=55432,
        database="etl",
    )
    try:
        with destino.open("x", encoding="utf-8") as arquivo:
            arquivo.write("URL_BANCO_API=" + endereco.render_as_string(hide_password=False) + "\n")
            arquivo.write("SEGREDO_CURSOR=" + secrets.token_urlsafe(48) + "\n")
    except FileExistsError:
        print(".env.api já existe; arquivo preservado.")
        return 0
    print(".env.api criado para api_leitura. Segredos preservados no arquivo local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
