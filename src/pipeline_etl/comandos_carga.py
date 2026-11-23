"""Interface de carga offline com saídas seguras."""

import argparse
import json
import sys
from dataclasses import asdict

from sqlalchemy.exc import SQLAlchemyError

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.auditoria import ErroValidacao
from pipeline_etl.processamento.carga import carregar_manifesto


def executar_carga(configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace) -> int:
    try:
        motor = criar_motor(
            resolver_url_processamento(
                configuracao.url_banco_processamento, opcoes.credenciais_locais
            )
        )
    except (OSError, ValueError):
        print("Credenciais de processamento inválidas ou ausentes.", file=sys.stderr)
        return 2
    try:
        resumo = carregar_manifesto(
            ArmazenamentoBronze(configuracao.caminho_bronze), opcoes.manifesto, motor
        )
        saida = asdict(resumo)
        saida["execucao_id"] = str(resumo.execucao_id)
        print(json.dumps(saida))
        return 0 if resumo.situacao == "SUCESSO" else 1
    except (SQLAlchemyError, ErroValidacao):
        print("Carga não concluída. Confira o banco, as migrações e a auditoria.", file=sys.stderr)
        return 1
    finally:
        motor.dispose()
