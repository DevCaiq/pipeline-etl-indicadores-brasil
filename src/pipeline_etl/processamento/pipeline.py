"""Coordenação BCB independente do Prefect; tentativas HTTP ficam no cliente."""

import json
import os
import socket
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import Engine, text

from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.atualizacao import ResumoAtualizacao, atualizar_serie
from pipeline_etl.processamento.auditoria import PAI_PIPELINE, _finalizar_falha, _iniciar
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.publicacao import ResumoPublicacao, publicar_bcb
from pipeline_etl.processamento.recuperacao import proteger_coordenacao


@dataclass(frozen=True)
class ResumoPipeline:
    situacao: str
    atualizacoes: tuple[ResumoAtualizacao, ...]
    publicacao: ResumoPublicacao | None


def executar_pipeline(
    cliente: ClienteBCB,
    armazenamento: ArmazenamentoBronze,
    processamento: Engine,
    publicador: Engine,
    modo: str,
) -> ResumoPipeline:
    """Cada série avança independentemente; uma falha não multiplica retries."""
    if modo not in {"incremental", "reconciliacao"}:
        raise ValueError("Modo de pipeline inválido.")
    with proteger_coordenacao(processamento):
        identificador = _iniciar(
            processamento,
            "pipeline_bcb",
            {"modo": modo, "maquina": socket.gethostname(), "processo_id": os.getpid()},
        )
        contexto = PAI_PIPELINE.set(identificador)
        metricas_iniciais = _obter_metricas_coleta(cliente)
        try:
            return _coordenar(
                cliente, armazenamento, processamento, publicador, modo, identificador
            )
        except Exception:
            _finalizar_falha(processamento, identificador, "COORDENACAO_INTERROMPIDA")
            raise
        finally:
            PAI_PIPELINE.reset(contexto)
            _persistir_delta_coleta(processamento, identificador, cliente, metricas_iniciais)


def _coordenar(
    cliente: ClienteBCB,
    armazenamento: ArmazenamentoBronze,
    processamento: Engine,
    publicador: Engine,
    modo: str,
    identificador: UUID,
) -> ResumoPipeline:
    resultados = []
    for codigo in (432, 433, 1):
        try:
            resultado = atualizar_serie(cliente, armazenamento, processamento, codigo, modo)
        except Exception as erro:
            resultado = ResumoAtualizacao(
                codigo,
                "FALHA",
                execucao_id=getattr(erro, "execucao_id", None),
                motivo="ETAPA_INTERROMPIDA",
            )
        resultados.append(resultado)
    try:
        publicacao = publicar_bcb(publicador)
    except Exception:
        publicacao = None
    completas = sum(item.situacao == "SUCESSO" for item in resultados)
    publicada = publicacao is not None and (
        publicacao.situacao == "SUCESSO"
        or (publicacao.situacao == "IGNORADA" and publicacao.motivo == "JA_PUBLICADA")
    )
    progresso = any(
        item.situacao in {"SUCESSO", "PARCIAL"}
        or any(
            janela.carga is not None and janela.carga.situacao == "SUCESSO"
            for janela in item.resultados
        )
        for item in resultados
    )
    if not progresso:
        with processamento.connect() as conexao:
            progresso = (
                conexao.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ops.execucao "
                        "WHERE modo='carga_bcb' AND situacao='SUCESSO' AND "
                        "parametros->>'pai_pipeline_id'=:pai)"
                    ),
                    {"pai": str(identificador)},
                )
                is True
            )
    situacao = "SUCESSO" if completas == 3 and publicada else ("PARCIAL" if progresso else "FALHA")
    with processamento.begin() as conexao:
        conexao.execute(
            text(
                "UPDATE ops.execucao SET situacao=:situacao,finalizado_em=now(), "
                "parametros=parametros || CAST(:resumo AS jsonb) WHERE execucao_id=:id"
            ),
            {
                "id": identificador,
                "situacao": situacao,
                "resumo": json.dumps(
                    {
                        "execucoes_series": [
                            str(item.execucao_id) if item.execucao_id else None
                            for item in resultados
                        ],
                        "situacoes_series": [item.situacao for item in resultados],
                        "execucao_publicacao": str(publicacao.execucao_id) if publicacao else None,
                    }
                ),
            },
        )
    return ResumoPipeline(situacao, tuple(resultados), publicacao)


def _obter_metricas_coleta(cliente: object) -> dict[str, int] | None:
    """Aceita apenas contadores instrumentados, sem converter mocks ou booleanos."""
    try:
        metricas = getattr(cliente, "metricas_coleta", None)
        if not isinstance(metricas, dict):
            return None
        if any(
            type(metricas.get(nome)) is not int or metricas[nome] < 0
            for nome in ("requisicoes", "retentativas")
        ):
            return None
        return {nome: metricas[nome] for nome in ("requisicoes", "retentativas")}
    except Exception:
        return None


def _persistir_delta_coleta(
    processamento: Engine,
    identificador: UUID,
    cliente: object,
    iniciais: dict[str, int] | None,
) -> None:
    finais = _obter_metricas_coleta(cliente)
    if iniciais is None or finais is None:
        return
    delta = {nome: finais[nome] - iniciais[nome] for nome in iniciais}
    if any(valor < 0 for valor in delta.values()):
        return
    _persistir_metricas_coleta(processamento, identificador, delta)


def _persistir_metricas_coleta(
    processamento: Engine,
    identificador: UUID,
    metricas: dict[str, int],
) -> None:
    """A telemetria complementar não substitui o resultado nem a falha do ETL."""
    try:
        with processamento.begin() as conexao:
            conexao.execute(
                text(
                    "UPDATE ops.execucao SET parametros=jsonb_set("
                    "parametros,'{metricas_coleta}',CAST(:metricas AS jsonb)) "
                    "WHERE execucao_id=:id"
                ),
                {"id": identificador, "metricas": json.dumps(metricas)},
            )
    except Exception:
        structlog.get_logger(servico="coleta").warning(
            "Não foi possível persistir métricas da coleta", execucao_id=str(identificador)
        )
