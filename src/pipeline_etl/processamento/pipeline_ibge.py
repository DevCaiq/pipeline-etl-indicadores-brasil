"""Coordenação síncrona IBGE; pacote completo antes da promoção transacional."""

import json
import os
import socket
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine, text

from pipeline_etl.processamento.armazenamento.objetos import ArmazenamentoObjetos, ObjetoBronze
from pipeline_etl.processamento.auditoria import PAI_PIPELINE, _finalizar_falha, _iniciar
from pipeline_etl.processamento.carga_ibge import carregar_ibge, publicar_ibge
from pipeline_etl.processamento.clientes.ibge import ClienteIBGE, ler_coleta
from pipeline_etl.processamento.contratos.ibge import descobrir_periodos
from pipeline_etl.processamento.pipeline import _obter_metricas_coleta, _persistir_delta_coleta
from pipeline_etl.processamento.recuperacao import proteger_coordenacao


@dataclass(frozen=True)
class ResumoPipelineIBGE:
    situacao: str
    manifestos: tuple[ObjetoBronze, ...]
    anos: tuple[int, ...] = ()
    motivo: str | None = None
    execucao_id: UUID | None = None


def selecionar_anos(
    disponiveis: tuple[int, ...], carregados: set[int], modo: str
) -> tuple[int, ...]:
    if modo not in {"incremental", "localidades", "reconciliacao"}:
        raise ValueError("Modo IBGE inválido.")
    if not disponiveis:
        raise ValueError("Nenhum período IBGE disponível.")
    if modo != "incremental":
        return disponiveis
    return tuple(ano for ano in disponiveis if ano not in carregados or ano == max(disponiveis))


def executar_ibge(
    coletor: ClienteIBGE,
    armazenamento: ArmazenamentoObjetos,
    processamento: Engine,
    publicador: Engine,
    modo: str = "reconciliacao",
    registrar_manifesto: Callable[[ObjetoBronze], None] | None = None,
    registrar_periodos: Callable[[tuple[int, ...]], None] | None = None,
) -> ResumoPipelineIBGE:
    """Não publica enquanto houver coleta ou carga inválida; bronze permanece."""
    manifestos = []
    anos: tuple[int, ...] = ()

    def registrar(manifesto: ObjetoBronze) -> None:
        manifestos.append(manifesto)
        if registrar_manifesto is not None:
            registrar_manifesto(manifesto)

    for recurso in ("regioes", "ufs", "municipios", "metadados", "periodos"):
        resultado = coletor.coletar(recurso)
        registrar(resultado.manifesto)
        if resultado.situacao != "COLETADA":
            return ResumoPipelineIBGE("FALHA", tuple(manifestos), motivo="COLETA_INCOMPLETA")
    disponiveis = descobrir_periodos(ler_coleta(armazenamento, manifestos[-1]).corpo)
    if registrar_periodos is not None:
        registrar_periodos(disponiveis)
    carregados: set[int] = set()
    if modo == "incremental":
        with processamento.begin() as conexao:
            conexao.execute(text("SET TRANSACTION READ ONLY"))
            carregados = set(
                conexao.execute(
                    text("SELECT DISTINCT ano FROM core.fato_populacao WHERE indicador_id=1")
                ).scalars()
            )
    anos = selecionar_anos(disponiveis, carregados, modo)
    for ano in anos:
        resultado = coletor.coletar("populacao", ano)
        registrar(resultado.manifesto)
        if resultado.situacao != "COLETADA":
            return ResumoPipelineIBGE("FALHA", tuple(manifestos), anos, "COLETA_INCOMPLETA")
    carga = carregar_ibge(armazenamento, tuple(manifestos), processamento)
    if carga.situacao != "SUCESSO":
        return ResumoPipelineIBGE("FALHA", tuple(manifestos), anos, carga.motivo)
    publicacao = publicar_ibge(publicador)
    if publicacao.situacao == "SUCESSO" or publicacao.motivo == "JA_PUBLICADA":
        return ResumoPipelineIBGE("SUCESSO", tuple(manifestos), anos)
    return ResumoPipelineIBGE("PARCIAL", tuple(manifestos), anos, publicacao.motivo)


def executar_ibge_coordenado(
    coletor: ClienteIBGE,
    armazenamento: ArmazenamentoObjetos,
    processamento: Engine,
    publicador: Engine,
    modo: str = "incremental",
    referencia_armazenamento: dict[str, str] | None = None,
) -> ResumoPipelineIBGE:
    """Audita o pai, mantém exclusão mútua e recupera somente processos locais ausentes."""
    if modo not in {"incremental", "localidades", "reconciliacao", "publicacao"}:
        raise ValueError("Modo IBGE inválido.")
    with proteger_coordenacao(processamento, dominio="ibge"):
        identificador = _iniciar(
            processamento,
            "pipeline_ibge",
            {
                "modo": modo,
                "maquina": socket.gethostname(),
                "processo_id": os.getpid(),
                "armazenamento": referencia_armazenamento or {"tipo": "arquivos"},
                "manifestos": [],
            },
        )
        contexto = PAI_PIPELINE.set(identificador)
        metricas_iniciais = _obter_metricas_coleta(coletor)

        def registrar(manifesto: ObjetoBronze) -> None:
            with processamento.begin() as conexao:
                conexao.execute(
                    text(
                        "UPDATE ops.execucao SET parametros=jsonb_set(parametros,'{manifestos}',"
                        "COALESCE(parametros->'manifestos','[]'::jsonb) "
                        "|| CAST(:manifesto AS jsonb)) "
                        "WHERE execucao_id=:id"
                    ),
                    {"id": identificador, "manifesto": json.dumps([asdict(manifesto)])},
                )

        def registrar_periodos(disponiveis: tuple[int, ...]) -> None:
            with processamento.begin() as conexao:
                conexao.execute(
                    text(
                        "UPDATE ops.execucao SET parametros=parametros || CAST(:periodos AS jsonb) "
                        "WHERE execucao_id=:id"
                    ),
                    {
                        "id": identificador,
                        "periodos": json.dumps(
                            {
                                "anos_disponiveis": list(disponiveis),
                                "consulta_periodos_em": datetime.now(UTC).isoformat(),
                            }
                        ),
                    },
                )

        try:
            if modo == "publicacao":
                publicacao = publicar_ibge(publicador)
                sucesso = publicacao.situacao == "SUCESSO" or publicacao.motivo == "JA_PUBLICADA"
                resumo = ResumoPipelineIBGE(
                    "SUCESSO" if sucesso else "FALHA", (), motivo=publicacao.motivo
                )
            else:
                resumo = executar_ibge(
                    coletor,
                    armazenamento,
                    processamento,
                    publicador,
                    modo,
                    registrar,
                    registrar_periodos,
                )
            with processamento.begin() as conexao:
                conexao.execute(
                    text(
                        "UPDATE ops.execucao SET situacao=:situacao,finalizado_em=now(),"
                        "erro=:motivo "
                        "WHERE execucao_id=:id"
                    ),
                    {"id": identificador, "situacao": resumo.situacao, "motivo": resumo.motivo},
                )
            return replace(resumo, execucao_id=identificador)
        except Exception:
            _finalizar_falha(processamento, identificador, "COORDENACAO_IBGE_INTERROMPIDA")
            raise
        finally:
            PAI_PIPELINE.reset(contexto)
            _persistir_delta_coleta(processamento, identificador, coletor, metricas_iniciais)
