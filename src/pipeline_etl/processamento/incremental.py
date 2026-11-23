"""Planejamento puro das janelas de atualização BCB."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, cast

from pipeline_etl.processamento.coleta import dividir_janelas

ModoAtualizacao = Literal["incremental", "reconciliacao", "carga-historica"]


@dataclass(frozen=True)
class PlanoAtualizacao:
    codigo_serie: int
    modo: ModoAtualizacao
    inicio: date
    fim: date
    janelas: tuple[tuple[date, date], ...]


def planejar_atualizacao(
    codigo: int,
    modo: str,
    hoje: date,
    *,
    ultima_observacao: date | None = None,
    fim_coberto: date | None = None,
    inicio: date | None = None,
    fim: date | None = None,
) -> PlanoAtualizacao:
    """Não presume histórico confirmado quando falta marco de cobertura."""
    piso = date(2020, 1, 1)
    if codigo not in {1, 432, 433} or hoje < piso:
        raise ValueError("CONTEXTO_INVALIDO")
    if modo not in {"incremental", "reconciliacao", "carga-historica"}:
        raise ValueError("MODO_INVALIDO")
    if modo != "carga-historica" and (inicio is not None or fim is not None):
        raise ValueError("DATAS_EXCLUSIVAS_CARGA_HISTORICA")
    if modo == "incremental":
        if ultima_observacao is None or fim_coberto is None:
            raise ValueError("SEM_CHECKPOINT")
        if not piso <= ultima_observacao <= fim_coberto <= hoje:
            raise ValueError("CHECKPOINT_INVALIDO")
        inicio = (
            date(ultima_observacao.year - 2, ultima_observacao.month, 1)
            if codigo == 433
            else ultima_observacao - timedelta(days=30)
        )
        inicio = max(piso, inicio)
        fim = hoje
    elif modo == "reconciliacao":
        inicio, fim = piso, hoje
    if inicio is None or fim is None or not piso <= inicio <= fim <= hoje:
        raise ValueError("PERIODO_INVALIDO")
    return PlanoAtualizacao(
        codigo, cast(ModoAtualizacao, modo), inicio, fim, tuple(dividir_janelas(inicio, fim))
    )
