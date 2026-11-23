"""CLI para publicação BCB usando o papel próprio da gold."""

import argparse
import json
import sys
from dataclasses import asdict

from sqlalchemy.exc import SQLAlchemyError

from pipeline_etl.banco.credenciais import resolver_url_publicador
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.publicacao import publicar_bcb


def executar_publicacao(configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace) -> int:
    try:
        motor = criar_motor(
            resolver_url_publicador(configuracao.url_banco_publicador, opcoes.credenciais_locais)
        )
    except (OSError, ValueError):
        print("Credenciais de publicação inválidas ou ausentes.", file=sys.stderr)
        return 2
    try:
        resumo = publicar_bcb(motor)
        print(json.dumps(asdict(resumo), default=str))
        return 0 if resumo.situacao == "SUCESSO" or resumo.motivo == "JA_PUBLICADA" else 1
    except SQLAlchemyError:
        print("Publicação não concluída. Confira banco, migrações e auditoria.", file=sys.stderr)
        return 1
    finally:
        motor.dispose()
