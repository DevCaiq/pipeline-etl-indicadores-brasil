"""Inicialização local da API, sem expor credenciais."""

import argparse
import sys
from typing import Any

import uvicorn
from pydantic import ValidationError

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.registros import configurar_registros


def executar_servidor(opcoes: argparse.Namespace) -> int:
    try:
        if not 1 <= opcoes.porta <= 65535:
            raise ValueError("Porta inválida.")
        parametros: dict[str, Any] = {"_env_file": opcoes.configuracao_api}
        configuracao = ConfiguracaoAplicacao(**parametros)
        configurar_registros(configuracao.nivel_registros)
        aplicacao = criar_aplicacao(configuracao)
    except (OSError, ValueError, ValidationError):
        print("Configuração da API inválida. Confira o arquivo e SEGREDO_CURSOR.", file=sys.stderr)
        return 2
    uvicorn.run(
        aplicacao, host="127.0.0.1", port=opcoes.porta, access_log=False, proxy_headers=False
    )
    return 0
