"""CLI para planejamento e atualização BCB por série."""

import argparse
import json
import sys
from dataclasses import asdict

import httpx
from sqlalchemy.exc import SQLAlchemyError

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.atualizacao import ErroAtualizacao, atualizar_serie
from pipeline_etl.processamento.auditoria import ErroValidacao
from pipeline_etl.processamento.clientes.bcb import ClienteBCB


def executar_atualizacao(configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace) -> int:
    try:
        motor = criar_motor(
            resolver_url_processamento(
                configuracao.url_banco_processamento, opcoes.credenciais_locais
            )
        )
    except (OSError, ValueError):
        print("Credenciais de processamento inválidas ou ausentes.", file=sys.stderr)
        return 2
    resultados: list[dict[str, object]] = []
    try:
        with httpx.Client() as transporte:
            cliente = ClienteBCB(transporte)
            for codigo in dict.fromkeys(opcoes.serie or configuracao.series_bcb):
                try:
                    resumo = atualizar_serie(
                        cliente,
                        ArmazenamentoBronze(configuracao.caminho_bronze),
                        motor,
                        codigo,
                        opcoes.modo,
                        inicio=opcoes.inicio,
                        fim=opcoes.fim,
                        somente_planejar=opcoes.planejar,
                    )
                    resultados.append(asdict(resumo))
                except (SQLAlchemyError, ErroAtualizacao, ErroValidacao) as erro:
                    resultados.append(
                        {
                            "codigo_serie": codigo,
                            "situacao": "FALHA",
                            "motivo": "BANCO_OU_AUDITORIA_INDISPONIVEL",
                            "execucao_id": str(erro.execucao_id)
                            if isinstance(erro, (ErroAtualizacao, ErroValidacao))
                            else None,
                        }
                    )
        aprovadas = {"SUCESSO", "PLANEJADA"}
        situacao = (
            ("PLANEJADA" if opcoes.planejar else "SUCESSO")
            if all(item["situacao"] in aprovadas for item in resultados)
            else (
                "PARCIAL"
                if any(item["situacao"] in aprovadas | {"PARCIAL"} for item in resultados)
                else "FALHA"
            )
        )
        print(json.dumps({"situacao": situacao, "atualizacoes": resultados}, default=str))
        return 0 if situacao in aprovadas else 1
    finally:
        motor.dispose()
