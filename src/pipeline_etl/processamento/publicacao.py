"""Publicação atômica do domínio BCB; a gold anterior sobrevive a falhas."""

import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import date
from uuid import UUID

import structlog
from sqlalchemy import Connection, Engine, text

from pipeline_etl.processamento.auditoria import _iniciar
from pipeline_etl.processamento.carga import CHAVE_TRAVA_BCB, CargaAdiada


@dataclass(frozen=True)
class ResumoPublicacao:
    execucao_id: UUID
    situacao: str
    versao_core: int | None = None
    versao_gold: int | None = None
    motivo: str | None = None
    data_publicacao: date | None = None


def _registrar(conexao: Connection, resumo: ResumoPublicacao) -> None:
    conexao.execute(
        text(
            "UPDATE ops.execucao SET situacao=:situacao,finalizado_em=now(), "
            "erro=:motivo,parametros=parametros || CAST(:resumo AS jsonb) WHERE execucao_id=:id"
        ),
        {
            "id": resumo.execucao_id,
            "situacao": resumo.situacao,
            "motivo": resumo.motivo,
            "resumo": json.dumps(asdict(resumo), default=str),
        },
    )


def _atualizar(motor: Engine, identificador: UUID, espera: float) -> ResumoPublicacao:
    with motor.begin() as conexao:
        conexao.execute(text("SET LOCAL statement_timeout='30s'"))
        limite = time.monotonic() + espera
        while not conexao.scalar(
            text("SELECT pg_try_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB}
        ):
            if time.monotonic() >= limite:
                raise CargaAdiada()
            time.sleep(min(0.1, max(0, limite - time.monotonic())))
        hoje = conexao.scalar(
            text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date")
        )
        estado = conexao.execute(
            text(
                "SELECT versao_core,versao_gold,situacao,data_publicacao "
                "FROM ops.publicacao WHERE dominio='bcb' FOR UPDATE"
            )
        ).first()
        if estado is None or estado.versao_core == 0:
            resumo = ResumoPublicacao(identificador, "IGNORADA", motivo="SEM_GERACAO_CORE")
        elif (
            estado.versao_gold == estado.versao_core
            and estado.situacao == "PRONTA"
            and estado.data_publicacao == hoje
        ):
            resumo = ResumoPublicacao(
                identificador,
                "IGNORADA",
                estado.versao_core,
                estado.versao_gold,
                "JA_PUBLICADA",
                estado.data_publicacao,
            )
        else:
            # A referência e as MVs avançam juntas; rollback preserva ambas.
            conexao.execute(
                text("UPDATE ops.publicacao SET data_publicacao=:hoje WHERE dominio='bcb'"),
                {"hoje": hoje},
            )
            for visao in ("mv_serie_mensal", "mv_serie_anual", "mv_ipca_12m"):
                conexao.execute(text(f"REFRESH MATERIALIZED VIEW mart.{visao}"))
            conexao.execute(
                text(
                    "UPDATE ops.publicacao SET versao_gold=versao_core,situacao='PRONTA', "
                    "data_publicacao=:hoje WHERE dominio='bcb'"
                ),
                {"hoje": hoje},
            )
            resumo = ResumoPublicacao(
                identificador,
                "SUCESSO",
                estado.versao_core,
                estado.versao_core,
                data_publicacao=hoje,
            )
        _registrar(conexao, resumo)
        return resumo


def publicar_bcb(motor: Engine, *, espera_trava: float = 30.0) -> ResumoPublicacao:
    """Refresh conjunto e troca de geração usam a mesma transação e trava da carga."""
    if not math.isfinite(espera_trava) or espera_trava < 0:
        raise ValueError("Espera de trava inválida.")
    identificador = _iniciar(motor, "publicacao_bcb", {"dominio": "bcb"})
    try:
        return _atualizar(motor, identificador, espera_trava)
    except CargaAdiada:
        resumo = ResumoPublicacao(identificador, "IGNORADA", motivo="TRAVA_OCUPADA")
        with motor.begin() as conexao:
            _registrar(conexao, resumo)
        return resumo
    except Exception:
        resumo = ResumoPublicacao(identificador, "FALHA", motivo="PUBLICACAO_FALHOU")
        try:
            with motor.begin() as conexao:
                conexao.execute(text("SET LOCAL statement_timeout='30s'"))
                conexao.execute(
                    text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB}
                )
                # Não sobrescreve publicação mais recente que tenha recuperado a gold.
                conexao.execute(
                    text(
                        "UPDATE ops.publicacao SET situacao='PENDENTE' WHERE dominio='bcb' "
                        "AND (versao_gold<versao_core OR data_publicacao IS NULL OR "
                        "data_publicacao < "
                        "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date)"
                    )
                )
                _registrar(conexao, resumo)
        except Exception:
            structlog.get_logger(servico="publicacao").error(
                "Registro de falha indisponível", execucao_id=str(identificador)
            )
        return resumo
