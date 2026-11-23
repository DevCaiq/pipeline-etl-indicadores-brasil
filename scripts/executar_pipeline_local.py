"""Entrada do worker local; serviços reutilizados sem dependência de Prefect."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import httpx

from pipeline_etl.banco.credenciais import resolver_url_processamento, resolver_url_publicador
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.pipeline import executar_pipeline
from pipeline_etl.processamento.publicacao import publicar_bcb
from pipeline_etl.registros import configurar_registros


def executar() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument(
        "--modo", choices=["incremental", "reconciliacao", "publicacao"], default="incremental"
    )
    opcoes = argumentos.parse_args()
    raiz = Path(__file__).resolve().parents[1]
    configurar_registros("INFO")
    processamento = criar_motor(resolver_url_processamento(None, raiz / ".env.banco"))
    publicador = criar_motor(resolver_url_publicador(None, raiz / ".env.banco"))
    try:
        if opcoes.modo == "publicacao":
            resumo = publicar_bcb(publicador)
            sucesso = resumo.situacao == "SUCESSO" or (
                resumo.situacao == "IGNORADA" and resumo.motivo == "JA_PUBLICADA"
            )
        else:
            from pipeline_etl.processamento.clientes.bcb import ClienteBCB

            with httpx.Client(trust_env=False) as transporte:
                resumo = executar_pipeline(
                    ClienteBCB(transporte),
                    ArmazenamentoBronze(raiz / "dados/bronze"),
                    processamento,
                    publicador,
                    opcoes.modo,
                )
            sucesso = resumo.situacao == "SUCESSO"
        print(json.dumps(asdict(resumo), default=str))
        return 0 if sucesso else 1
    finally:
        processamento.dispose()
        publicador.dispose()


if __name__ == "__main__":
    raise SystemExit(executar())
