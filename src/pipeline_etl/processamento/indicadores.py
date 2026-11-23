"""Referência Decimal sem arredondamento intermediário; resposta como texto."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext

from pipeline_etl.processamento.contratos.bcb import ObservacaoSGS


@dataclass(frozen=True)
class AcumuladoIPCA:
    valor: Decimal | None
    completo: bool
    observacoes: int
    motivo: str | None = None


def compor_ipca(observacoes: Iterable[ObservacaoSGS], fim: date) -> AcumuladoIPCA:
    """Calcula12 meses-calendário consecutivos até o mês solicitado."""
    fim = fim.replace(day=1)
    indice = fim.year * 12 + fim.month - 1
    esperadas = {
        date((indice - deslocamento) // 12, (indice - deslocamento) % 12 + 1, 1)
        for deslocamento in range(12)
    }
    valores: dict[date, Decimal] = {}
    for observacao in observacoes:
        if observacao.data.day != 1 or observacao.data in valores:
            raise ValueError("Data mensal não normalizada ou duplicada.")
        valores[observacao.data] = observacao.valor
    selecionados = {data: valor for data, valor in valores.items() if data in esperadas}
    if set(selecionados) != esperadas:
        return AcumuladoIPCA(None, False, len(selecionados), "MESES_AUSENTES")
    with localcontext() as contexto:
        contexto.prec = 500
        produto = Decimal(1)
        for data in sorted(selecionados):
            produto *= 1 + selecionados[data] / 100
        return AcumuladoIPCA((produto - 1) * 100, True, 12)


def formatar_decimal(valor: Decimal | None) -> str | None:
    """Arredonda somente na fronteira pública; nenhuma conversão para float."""
    if valor is None:
        return None
    if not valor.is_finite():
        raise ValueError("Medida não finita.")
    with localcontext() as contexto:
        contexto.prec = max(
            50, len(valor.as_tuple().digits) + abs(int(valor.as_tuple().exponent)) + 10
        )
        return format(valor.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN), "f")
