"""Coleta IBGE oficial, carrega e publica localmente com papéis separados."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import httpx

from pipeline_etl.banco.credenciais import resolver_url_processamento, resolver_url_publicador
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.processamento.armazenamento.s3 import abrir_armazenamento, ler_configuracao_s3
from pipeline_etl.processamento.clientes.ibge import ClienteIBGE
from pipeline_etl.processamento.pipeline_ibge import executar_ibge_coordenado


def executar() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument(
        "--configuracao-s3", type=Path, help="Arquivo privado S3; padrão: disco."
    )
    argumentos.add_argument(
        "--modo",
        choices=["incremental", "localidades", "reconciliacao", "publicacao"],
        default="reconciliacao",
    )
    opcoes = argumentos.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    referencia = {"tipo": "arquivos", "raiz": str(raiz / "dados/bronze")}
    if opcoes.configuracao_s3:
        configuracao_s3 = ler_configuracao_s3(opcoes.configuracao_s3)
        referencia = {
            "tipo": "s3",
            "endereco": configuracao_s3.endereco,
            "bucket": configuracao_s3.bucket,
            "prefixo": configuracao_s3.prefixo,
        }
    processamento = criar_motor(resolver_url_processamento(None, raiz / ".env.banco"))
    publicador = criar_motor(resolver_url_publicador(None, raiz / ".env.banco"))
    try:
        with (
            abrir_armazenamento(raiz / "dados/bronze", opcoes.configuracao_s3) as armazenamento,
            httpx.Client(trust_env=False) as transporte,
        ):
            resumo = executar_ibge_coordenado(
                ClienteIBGE(transporte, armazenamento),
                armazenamento,
                processamento,
                publicador,
                opcoes.modo,
                referencia,
            )
        print(json.dumps(asdict(resumo), ensure_ascii=False, default=str))
        return 0 if resumo.situacao == "SUCESSO" else 1
    finally:
        processamento.dispose()
        publicador.dispose()


if __name__ == "__main__":
    raise SystemExit(executar())
