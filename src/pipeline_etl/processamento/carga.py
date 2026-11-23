"""Carga offline BCB: preparação durável e promoção transacional protegida."""

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.postgresql import insert

from pipeline_etl.banco.modelos import (
    EstadoPublicacao,
    ExecucaoPipeline,
    LoteProcessamento,
    MarcoCoberturaBCB,
    ObservacaoSerie,
    PreparacaoBCB,
)
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.auditoria import _finalizar_falha, _iniciar, validar_manifesto
from pipeline_etl.processamento.manifestos import ManifestoVerificado, ler_manifesto
from pipeline_etl.processamento.qualidade import validar_corpo
from pipeline_etl.processamento.transformacao import calcular_fim_contiguo, transformar_observacoes

CHAVE_TRAVA_BCB = 2026111801


class CargaAdiada(Exception):
    """Outra promoção detém o domínio; tentar novamente mais tarde."""


@dataclass(frozen=True)
class ResumoCarga:
    execucao_id: UUID
    situacao: str
    inseridas: int = 0
    alteradas: int = 0
    inalteradas: int = 0
    motivo: str | None = None
    avisos: tuple[str, ...] = ()


def _preparar(motor: Engine, identificador: UUID, verificado: ManifestoVerificado) -> int:
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    linhas: list[dict[str, object]] = []
    for artefato in verificado.artefatos:
        resultado = validar_corpo(
            artefato.corpo,
            verificado.manifesto.codigo_serie,
            artefato.inicio,
            artefato.fim,
            hoje,
            artefato.metadados.codificacao_conteudo,
        )
        if resultado.situacao != "SUCESSO":
            raise ValueError("QUALIDADE_INCOMPLETA")
        linhas.extend(
            {
                "execucao_id": identificador,
                "codigo_sgs": verificado.manifesto.codigo_serie,
                "data": observacao.data,
                "valor": observacao.valor,
                "origem_coletada_em": artefato.metadados.coletado_em,
            }
            for observacao in transformar_observacoes(resultado.observacoes)
        )
    if len({linha["data"] for linha in linhas}) != len(linhas):
        raise ValueError("CHAVE_REPETIDA_ENTRE_ARTEFATOS")
    with motor.begin() as conexao:
        for inicio in range(0, len(linhas), 1000):
            conexao.execute(insert(PreparacaoBCB), linhas[inicio : inicio + 1000])
    return len(linhas)


def _promover(
    motor: Engine,
    identificador: UUID,
    verificado: ManifestoVerificado,
    soma_verificacao: str,
    espera_trava: float,
) -> ResumoCarga:
    codigo = verificado.manifesto.codigo_serie
    with motor.begin() as conexao:
        conexao.execute(text("SET LOCAL statement_timeout='30s'"))
        limite = time.monotonic() + espera_trava
        while not conexao.scalar(
            text("SELECT pg_try_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB}
        ):
            if time.monotonic() >= limite:
                raise CargaAdiada()
            time.sleep(min(0.1, max(0, limite - time.monotonic())))
        linhas = (
            conexao.execute(
                select(PreparacaoBCB)
                .where(PreparacaoBCB.execucao_id == identificador)
                .order_by(PreparacaoBCB.data)
            )
            .mappings()
            .all()
        )
        atuais = {
            linha.data: linha
            for linha in conexao.execute(
                select(ObservacaoSerie).where(
                    ObservacaoSerie.codigo_sgs == codigo,
                    ObservacaoSerie.data >= verificado.manifesto.inicio_coleta,
                    ObservacaoSerie.data <= verificado.manifesto.fim,
                )
            ).mappings()
        }
        origens_confirmadas = dict(
            conexao.execute(
                select(PreparacaoBCB.data, func.max(PreparacaoBCB.origem_coletada_em))
                .join(ExecucaoPipeline, ExecucaoPipeline.execucao_id == PreparacaoBCB.execucao_id)
                .where(
                    PreparacaoBCB.codigo_sgs == codigo,
                    ExecucaoPipeline.situacao == "SUCESSO",
                    PreparacaoBCB.data >= verificado.manifesto.inicio_coleta,
                    PreparacaoBCB.data <= verificado.manifesto.fim,
                )
                .group_by(PreparacaoBCB.data)
            )
            .tuples()
            .all()
        )
        avisos = (
            ("OBSERVACOES_AUSENTES_NA_JANELA",)
            if set(atuais) - {linha.data for linha in linhas}
            else ()
        )
        inseridas = alteradas = inalteradas = 0
        for linha in linhas:
            anterior = atuais.get(linha.data)
            if anterior is None:
                inseridas += 1
            elif anterior.valor == linha.valor:
                inalteradas += 1
            else:
                if anterior.origem_coletada_em is None or linha.origem_coletada_em <= max(
                    anterior.origem_coletada_em,
                    origens_confirmadas.get(linha.data, anterior.origem_coletada_em),
                ):
                    raise ValueError("BRONZE_ANTIGO_DIVERGENTE")
                alteradas += 1
        lote = uuid4()
        conexao.execute(
            insert(LoteProcessamento).values(
                lote_id=lote,
                execucao_id=identificador,
                fonte="bcb",
                chave=str(codigo),
                janela_inicio=verificado.manifesto.inicio_coleta,
                janela_fim=verificado.manifesto.fim,
                manifesto=str(verificado.caminho),
                checksum=soma_verificacao,
                confirmado_em=datetime.now(UTC),
            )
        )
        for inicio in range(0, len(linhas), 1000):
            valores = [
                {
                    "codigo_sgs": codigo,
                    "data": linha.data,
                    "valor": linha.valor,
                    "lote_id": lote,
                    "origem_coletada_em": linha.origem_coletada_em,
                }
                for linha in linhas[inicio : inicio + 1000]
            ]
            comando = insert(ObservacaoSerie).values(valores)
            comando = comando.on_conflict_do_update(
                index_elements=[ObservacaoSerie.codigo_sgs, ObservacaoSerie.data],
                set_={
                    "valor": comando.excluded.valor,
                    "lote_id": comando.excluded.lote_id,
                    "origem_coletada_em": comando.excluded.origem_coletada_em,
                    "alterado_em": func.now(),
                },
                where=ObservacaoSerie.valor.is_distinct_from(comando.excluded.valor),
            )
            conexao.execute(comando)
        janelas = conexao.execute(
            select(LoteProcessamento.janela_inicio, LoteProcessamento.janela_fim).where(
                LoteProcessamento.fonte == "bcb",
                LoteProcessamento.chave == str(codigo),
                LoteProcessamento.confirmado_em.is_not(None),
            )
        ).all()
        base = date(2019, 2, 1) if codigo == 433 else date(2020, 1, 1)
        fim_coberto = calcular_fim_contiguo(base, [(linha[0], linha[1]) for linha in janelas])
        if fim_coberto is not None:
            ultima = conexao.scalar(
                select(func.max(ObservacaoSerie.data)).where(
                    ObservacaoSerie.codigo_sgs == codigo, ObservacaoSerie.data <= fim_coberto
                )
            )
            marcador = insert(MarcoCoberturaBCB).values(
                codigo_sgs=codigo, fim_coberto=fim_coberto, ultima_observacao=ultima
            )
            conexao.execute(
                marcador.on_conflict_do_update(
                    index_elements=[MarcoCoberturaBCB.codigo_sgs],
                    set_={
                        "fim_coberto": func.greatest(
                            MarcoCoberturaBCB.fim_coberto, marcador.excluded.fim_coberto
                        ),
                        "ultima_observacao": marcador.excluded.ultima_observacao,
                        "atualizado_em": func.now(),
                    },
                    where=(
                        MarcoCoberturaBCB.fim_coberto.is_distinct_from(
                            marcador.excluded.fim_coberto
                        )
                        | MarcoCoberturaBCB.ultima_observacao.is_distinct_from(
                            marcador.excluded.ultima_observacao
                        )
                    ),
                )
            )
        if inseridas + alteradas:
            estado = insert(EstadoPublicacao).values(
                dominio="bcb", versao_core=1, situacao="PENDENTE"
            )
            conexao.execute(
                estado.on_conflict_do_update(
                    index_elements=[EstadoPublicacao.dominio],
                    set_={"versao_core": EstadoPublicacao.versao_core + 1, "situacao": "PENDENTE"},
                )
            )
        resumo = ResumoCarga(
            identificador, "SUCESSO", inseridas, alteradas, inalteradas, avisos=avisos
        )
        conexao.execute(
            text(
                "UPDATE ops.execucao SET situacao='SUCESSO', finalizado_em=now(), "
                "parametros=parametros || CAST(:resumo AS jsonb) WHERE execucao_id=:id"
            ),
            {
                "id": identificador,
                "resumo": json.dumps(
                    {
                        "inseridas": inseridas,
                        "alteradas": alteradas,
                        "inalteradas": inalteradas,
                        "lote_id": str(lote),
                        "avisos": list(avisos),
                    }
                ),
            },
        )
        return resumo


def carregar_manifesto(
    armazenamento: ArmazenamentoBronze, caminho: Path, motor: Engine, *, espera_trava: float = 30.0
) -> ResumoCarga:
    """Revalida os bytes antes da carga; nova tentativa não muda fatos iguais."""
    if not math.isfinite(espera_trava) or espera_trava < 0:
        raise ValueError("Espera de lock inválida.")
    validacao = validar_manifesto(armazenamento, caminho, motor)
    identificador = _iniciar(
        motor,
        "carga_bcb",
        {"manifesto": str(caminho.resolve()), "validacao_id": str(validacao.execucao_id)},
    )
    if validacao.situacao != "SUCESSO":
        _finalizar_falha(motor, identificador, "QUALIDADE_INCOMPLETA")
        return ResumoCarga(identificador, "FALHA", motivo="QUALIDADE_INCOMPLETA")
    try:
        verificado = ler_manifesto(armazenamento, caminho)
        _preparar(motor, identificador, verificado)
        soma_verificacao = hashlib.sha256(caminho.read_bytes()).hexdigest()
        return _promover(motor, identificador, verificado, soma_verificacao, espera_trava)
    except CargaAdiada:
        with motor.begin() as conexao:
            conexao.execute(
                text(
                    "UPDATE ops.execucao SET situacao='IGNORADA', finalizado_em=now(), "
                    "erro='LOCK_OCUPADO' WHERE execucao_id=:id AND situacao='EM_EXECUCAO'"
                ),
                {"id": identificador},
            )
        return ResumoCarga(identificador, "IGNORADA", motivo="LOCK_OCUPADO")
    except Exception as erro:
        motivo = (
            "BRONZE_ANTIGO_DIVERGENTE"
            if isinstance(erro, ValueError) and str(erro) == "BRONZE_ANTIGO_DIVERGENTE"
            else "CARGA_FALHOU"
        )
        _finalizar_falha(motor, identificador, motivo)
        return ResumoCarga(identificador, "FALHA", motivo=motivo)
