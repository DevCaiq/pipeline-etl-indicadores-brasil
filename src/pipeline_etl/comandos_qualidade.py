"""Comandos que exigem auditoria SQL, sem revelar URLs ou senhas."""

import argparse
import json
import sys
from dataclasses import asdict

import httpx
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.auditoria import (
    ErroValidacao,
    ResumoAuditoria,
    coletar_e_validar,
    validar_manifesto,
)
from pipeline_etl.processamento.clientes.bcb import ClienteBCB


def _resumir(resumo: ResumoAuditoria) -> dict[str, object]:
    return {
        "execucao_id": str(resumo.execucao_id),
        "situacao": resumo.situacao,
        "contagens": asdict(resumo.contagens),
        "avisos": list(resumo.avisos),
    }


def _motor(configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace) -> Engine:
    return criar_motor(
        resolver_url_processamento(configuracao.url_banco_processamento, opcoes.credenciais_locais)
    )


def executar_validacao(configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace) -> int:
    """Valida somente o bronze indicado, com nova execução auditável."""
    try:
        motor = _motor(configuracao, opcoes)
    except (OSError, ValueError):
        print("Credenciais de processamento inválidas ou ausentes.", file=sys.stderr)
        return 2
    try:
        resumo = validar_manifesto(
            ArmazenamentoBronze(configuracao.caminho_bronze), opcoes.manifesto, motor
        )
        print(json.dumps(_resumir(resumo)))
        return 0 if resumo.situacao == "SUCESSO" else 1
    except (SQLAlchemyError, ErroValidacao):
        print(
            "Validação não concluída. Confira o banco, as migrações e a auditoria.", file=sys.stderr
        )
        return 1
    finally:
        motor.dispose()


def executar_coleta_validada(
    configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace
) -> int:
    """Mantém coleta bruta e qualidade distintas, iniciando SQL antes de HTTP."""
    try:
        motor = _motor(configuracao, opcoes)
    except (OSError, ValueError):
        print("Credenciais de processamento inválidas ou ausentes.", file=sys.stderr)
        return 2
    resultados = []
    try:
        with httpx.Client() as transporte:
            cliente = ClienteBCB(transporte)
            for codigo in dict.fromkeys(opcoes.serie or configuracao.series_bcb):
                try:
                    resumo = coletar_e_validar(
                        cliente,
                        ArmazenamentoBronze(configuracao.caminho_bronze),
                        motor,
                        codigo,
                        opcoes.inicio,
                        opcoes.fim,
                    )
                    resultados.append({"codigo_serie": codigo, **_resumir(resumo)})
                except (SQLAlchemyError, ErroValidacao):
                    resultados.append(
                        {
                            "codigo_serie": codigo,
                            "situacao": "FALHA",
                            "motivo": "AUDITORIA_INDISPONIVEL",
                        }
                    )
        situacao = (
            "SUCESSO"
            if all(item["situacao"] == "SUCESSO" for item in resultados)
            else "PARCIAL"
            if any(item["situacao"] in {"SUCESSO", "PARCIAL"} for item in resultados)
            else "FALHA"
        )
        print(json.dumps({"situacao": situacao, "coletas": resultados}))
        return 0 if situacao == "SUCESSO" else 1
    finally:
        motor.dispose()
