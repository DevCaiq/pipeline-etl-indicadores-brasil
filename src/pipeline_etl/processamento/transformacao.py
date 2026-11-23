"""Transformações puras sem preencher lacunas ou arredondar medidas."""

from collections.abc import Iterable
from datetime import date, timedelta

from pipeline_etl.processamento.contratos.bcb import ObservacaoSGS


def transformar_observacoes(observacoes: Iterable[ObservacaoSGS]) -> tuple[ObservacaoSGS, ...]:
    por_data: dict[date, ObservacaoSGS] = {}
    for observacao in observacoes:
        anterior = por_data.get(observacao.data)
        if anterior is not None and anterior.valor != observacao.valor:
            raise ValueError("Observações conflitantes entre artefatos.")
        por_data[observacao.data] = observacao
    return tuple(por_data[chave] for chave in sorted(por_data))


def calcular_fim_contiguo(inicio: date, janelas: Iterable[tuple[date, date]]) -> date | None:
    """Avança por intervalos confirmados, sem confundir lacuna com feriado."""
    fim_coberto = inicio - timedelta(days=1)
    for inicio_janela, fim_janela in sorted(janelas):
        if inicio_janela > fim_coberto + timedelta(days=1):
            break
        fim_coberto = max(fim_coberto, fim_janela)
    return fim_coberto if fim_coberto >= inicio else None
