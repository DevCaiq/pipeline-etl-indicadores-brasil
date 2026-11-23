"""Contratos de qualidade BCB, sem rede nem persistência."""

import gzip
import json
import zlib
from datetime import date
from decimal import Decimal

import pytest

from pipeline_etl.processamento.qualidade import validar_corpo

HOJE = date(2026, 11, 18)


def validar(registros: object, codigo: int = 433):
    return validar_corpo(json.dumps(registros).encode(), codigo, date(2020, 1, 1), HOJE, HOJE)


def test_preserva_decimal_e_permite_ipca_negativo() -> None:
    resultado = validar([{"data": "01/01/2020", "valor": "-0,25"}])
    assert resultado.situacao == "SUCESSO"
    assert resultado.observacoes[0].valor == Decimal("-0.25")
    assert resultado.contagens.lidas == resultado.contagens.validas == 1


@pytest.mark.parametrize(
    "valor",
    [
        "NaN",
        "Infinity",
        "1e999",
        "1e999999999999999999999999999999",
        "abc",
        "1.00000000001",
        True,
        None,
        2.5,
    ],
)
def test_valor_invalido_vai_para_quarentena(valor: object) -> None:
    resultado = validar([{"data": "01/01/2020", "valor": valor}])
    assert resultado.situacao == "FALHA"
    assert resultado.contagens.rejeitadas == 1
    assert resultado.rejeicoes[0].posicao == 1
    assert not resultado.observacoes


@pytest.mark.parametrize("data", ["31/02/2020", "1/1/2020", "01/01/2027", None, "31/12/2019"])
def test_data_invalida_futura_ou_fora_da_janela(data: object) -> None:
    assert validar([{"data": data, "valor": "1"}]).contagens.rejeitadas == 1


@pytest.mark.parametrize(
    "registros",
    [
        [{"data": "01/01/2020", "valor": "1", "novo": 1}],
        [{"data": "01/01/2020"}],
        {"data": "01/01/2020", "valor": "1"},
        [1],
    ],
)
def test_drift_ou_envelope_falha_lote_inteiro(registros: object) -> None:
    resultado = validar(registros)
    assert resultado.situacao == "FALHA"
    assert resultado.erro_estrutural is not None
    assert not resultado.observacoes


def test_drift_nao_processa_as_outras_linhas() -> None:
    resultado = validar(
        [{"data": "01/01/2020", "valor": "1"}, {"data": "01/02/2020", "outro": "1"}]
    )
    assert resultado.contagens.lidas == 2
    assert resultado.contagens.rejeitadas == 1
    assert resultado.contagens.nao_processadas == 1


def test_deduplica_identicas_e_rejeita_todas_as_conflitantes() -> None:
    iguais = validar([{"data": "01/01/2020", "valor": "1"}] * 2)
    assert iguais.situacao == "SUCESSO"
    assert iguais.contagens.validas == iguais.contagens.duplicadas == 1
    conflito = validar([{"data": "01/01/2020", "valor": "1"}, {"data": "01/01/2020", "valor": "2"}])
    assert conflito.situacao == "FALHA"
    assert conflito.contagens.rejeitadas == 2
    assert not conflito.observacoes


@pytest.mark.parametrize("total,situacao", [(20, "PARCIAL"), (19, "FALHA")])
def test_limite_cinco_porcento(total: int, situacao: str) -> None:
    registros = [{"data": f"{dia:02d}/01/2020", "valor": "1"} for dia in range(1, total + 1)]
    registros[-1]["valor"] = "invalido"
    resultado = validar(registros, 432)
    assert resultado.situacao == situacao
    assert resultado.contagens.rejeitadas == 1
    assert resultado.contagens.validas == total - 1


def test_normaliza_mes_sem_alterar_original() -> None:
    resultado = validar([{"data": "15/01/2020", "valor": "0.2"}])
    assert resultado.observacoes[0].data == date(2020, 1, 1)


def test_dolar_precisa_ser_positivo() -> None:
    assert validar([{"data": "01/01/2020", "valor": "0"}], 1).contagens.rejeitadas == 1


@pytest.mark.parametrize(
    "corpo",
    [
        b"{",
        b"[]",
        b'[{"data":"01/01/2020","valor":"1","valor":"2"}]',
        b'[{"data":"01/01/2020","valor":NaN}]',
    ],
)
def test_json_invalido_vazio_ou_ambiguo(corpo: bytes) -> None:
    assert validar_corpo(corpo, 433, date(2020, 1, 1), HOJE, HOJE).situacao == "FALHA"


def test_gzip_valido_e_limite_de_expansao() -> None:
    corpo = json.dumps([{"data": "01/01/2020", "valor": "1"}]).encode()
    assert (
        validar_corpo(gzip.compress(corpo), 433, date(2020, 1, 1), HOJE, HOJE, "gzip").situacao
        == "SUCESSO"
    )
    resultado = validar_corpo(
        gzip.compress(b" " * 1000), 433, date(2020, 1, 1), HOJE, HOJE, "gzip", limite_bytes=100
    )
    assert resultado.situacao == "FALHA"
    assert resultado.erro_estrutural == "COMPRESSAO_INVALIDA"


def test_ipca_normalizado_nao_escapa_da_janela() -> None:
    corpo = b'[{"data":"20/01/2020","valor":"0.2"}]'
    resultado = validar_corpo(corpo, 433, date(2020, 1, 15), date(2020, 1, 31), HOJE)
    assert resultado.situacao == "FALHA"
    assert not resultado.observacoes


def test_decimal_nao_aceita_separador_de_programacao() -> None:
    assert validar([{"data": "01/01/2020", "valor": "1_000"}]).situacao == "FALHA"


@pytest.mark.parametrize(
    "corpo,codificacao", [(b"x", "br"), (b"x", "gzip"), (gzip.compress(b"[]")[:-1], "gzip")]
)
def test_codificacao_invalida_ou_truncada(corpo: bytes, codificacao: str) -> None:
    assert (
        validar_corpo(corpo, 433, date(2020, 1, 1), HOJE, HOJE, codificacao).erro_estrutural
        == "COMPRESSAO_INVALIDA"
    )


def test_deflate_valido() -> None:
    corpo = json.dumps([{"data": "01/01/2020", "valor": "1"}]).encode()
    assert (
        validar_corpo(zlib.compress(corpo), 433, date(2020, 1, 1), HOJE, HOJE, "deflate").situacao
        == "SUCESSO"
    )


def test_numero_json_excessivo_e_contexto_invalido() -> None:
    assert (
        validar_corpo(
            b'[{"data":"01/01/2020","valor":1e99999}]', 433, date(2020, 1, 1), HOJE, HOJE
        ).erro_estrutural
        == "JSON_INVALIDO"
    )
    with pytest.raises(ValueError):
        validar_corpo(b"[]", 999, HOJE, HOJE, HOJE)


@pytest.mark.parametrize(
    "registro,motivo",
    [
        ({"data": "invalida", "valor": "1"}, "DATA_INVALIDA"),
        ({"data": "01/01/2020", "valor": "invalido"}, "VALOR_INVALIDO"),
        ({"data": "invalida", "valor": "invalido"}, "DATA_E_VALOR_INVALIDOS"),
        ({"data": "01/01/2027", "valor": "1"}, "DATA_FUTURA"),
    ],
)
def test_motivo_de_rejeicao_identifica_a_regra(registro: dict[str, str], motivo: str) -> None:
    assert validar([registro]).rejeicoes[0].motivo == motivo
