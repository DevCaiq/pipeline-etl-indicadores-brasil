"""Compara a gold real com cálculos Decimal independentes, sem HTTP externo."""

import json
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

from sqlalchemy import text

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor


def proximo_mes(periodo: date) -> date:
    return date(periodo.year + periodo.month // 12, periodo.month % 12 + 1, 1)


def compor(valores: list[Decimal]) -> Decimal:
    with localcontext() as contexto:
        contexto.prec = 500
        produto = Decimal(1)
        for valor in valores:
            produto *= Decimal(1) + valor / Decimal(100)
        return (produto - Decimal(1)) * Decimal(100)


def seis_casas(valor: Decimal) -> Decimal:
    with localcontext() as contexto:
        contexto.prec = 500
        return valor.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)


def executar() -> int:
    raiz = Path(__file__).resolve().parents[1]
    motor = criar_motor(resolver_url_processamento(None, raiz / ".env.banco"))
    try:
        with motor.begin() as conexao:
            conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            fatos = conexao.execute(
                text("SELECT codigo_sgs,data,valor FROM core.fato_serie ORDER BY codigo_sgs,data")
            ).all()
            estado = conexao.execute(
                text(
                    "SELECT versao_core,versao_gold,situacao FROM ops.publicacao "
                    "WHERE dominio='bcb'"
                )
            ).one()
            assert estado.versao_core == estado.versao_gold and estado.situacao == "PRONTA"
            mensal = (
                conexao.execute(
                    text("SELECT * FROM mart.mv_serie_mensal ORDER BY codigo_sgs,periodo")
                )
                .mappings()
                .all()
            )
            anual = (
                conexao.execute(
                    text("SELECT * FROM mart.mv_serie_anual ORDER BY codigo_sgs,periodo")
                )
                .mappings()
                .all()
            )
            ipca12 = (
                conexao.execute(text("SELECT * FROM mart.mv_ipca_12m ORDER BY periodo"))
                .mappings()
                .all()
            )
        por_serie = defaultdict(dict)
        for codigo, data, valor in fatos:
            assert valor.is_finite()
            assert codigo != 433 or data.day == 1
            por_serie[codigo][data] = valor
        assert set(por_serie) == {432, 433, 1}
        comparacoes = 0
        for granularidade, linhas in [("mes", mensal), ("ano", anual)]:
            for linha in linhas:
                periodo = linha["periodo"]
                codigo = linha["codigo_sgs"]
                fim = (
                    proximo_mes(periodo) if granularidade == "mes" else date(periodo.year + 1, 1, 1)
                )
                selecionadas = sorted(
                    (data, valor)
                    for data, valor in por_serie[codigo].items()
                    if periodo <= data < fim
                )
                valores = [valor for _, valor in selecionadas]
                assert periodo >= date(2020, 1, 1) and linha["observacoes"] == len(valores)
                assert linha["parcial"] == (fim > linha["data_referencia"])
                if codigo != 433:
                    with localcontext() as contexto:
                        contexto.prec = 500
                        media = sum(valores, Decimal(0)) / Decimal(len(valores))
                    assert seis_casas(linha["media"]) == seis_casas(media)
                    assert (linha["minimo"], linha["maximo"], linha["ultimo"]) == (
                        min(valores),
                        max(valores),
                        valores[-1],
                    )
                    assert linha["variacao"] is None and linha["completo"] is None
                elif granularidade == "mes":
                    assert linha["variacao"] == valores[0] and len(valores) == 1
                    assert linha["completo"] == (not linha["parcial"])
                else:
                    completo = (
                        len(valores) == 12
                        and {data.month for data, _ in selecionadas} == set(range(1, 13))
                        and not linha["parcial"]
                    )
                    assert linha["completo"] == completo
                    assert linha["variacao"] == (compor(valores) if completo else None)
                    assert linha["unidade"] == "% no ano"
                comparacoes += 1
        for linha in ipca12:
            periodo = linha["periodo"]
            indice = periodo.year * 12 + periodo.month - 1
            meses = [
                date((indice - deslocamento) // 12, (indice - deslocamento) % 12 + 1, 1)
                for deslocamento in reversed(range(12))
            ]
            valores = [por_serie[433][mes] for mes in meses if mes in por_serie[433]]
            completo = len(valores) == 12 and proximo_mes(periodo) <= linha["data_referencia"]
            assert linha["observacoes"] == len(valores) and linha["completo"] == completo
            assert linha["variacao"] == (compor(valores) if completo else None)
            comparacoes += 1
        relatorio = {
            "versao_core": estado.versao_core,
            "versao_gold": estado.versao_gold,
            "situacao": estado.situacao,
            "mensais": len(mensal),
            "anuais": len(anual),
            "ipca12m": len(ipca12),
            "comparacoes_independentes": comparacoes,
            "ipca_anuais_completos": sum(
                linha["codigo_sgs"] == 433 and linha["completo"] for linha in anual
            ),
            "ipca12m_completos": sum(linha["completo"] for linha in ipca12),
            "referencia_ipca": str(max(por_serie[433])),
        }
        (raiz / "dados/descoberta/validacao_gold_historica.json").write_text(
            json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(relatorio, ensure_ascii=True))
        return 0
    finally:
        motor.dispose()


if __name__ == "__main__":
    raise SystemExit(executar())
