"""Integridade e identidade de cursores sem banco."""

import pytest

from pipeline_etl.api.cursores import assinar_cursor, ler_cursor
from pipeline_etl.api.erros import ErroAPI

SEGREDO = b"s" * 48


def test_cursor_preserva_chaves_e_teto_sem_aceitar_outros_filtros():
    token = assinar_cursor(SEGREDO, "observacoes", "filtros", "core1", ["2020-01-02"], agora=1000)
    assert ler_cursor(token, SEGREDO, "observacoes", "filtros", "core1", agora=1001).chaves == [
        "2020-01-02"
    ]
    for rota, filtros in [("outra", "filtros"), ("observacoes", "outros")]:
        with pytest.raises(ErroAPI) as erro:
            ler_cursor(token, SEGREDO, rota, filtros, "core1", agora=1001)
        assert erro.value.status == 422


def test_cursor_adulterado_expirado_e_geracao_antiga():
    token = assinar_cursor(SEGREDO, "rota", "filtros", "core1", ["2020-01-02"], agora=1000)
    for adulterado in [token[:-1] + ("0" if token[-1] != "0" else "1"), "x" * 2049, "invalido"]:
        with pytest.raises(ErroAPI) as erro:
            ler_cursor(adulterado, SEGREDO, "rota", "filtros", "core1", agora=1001)
        assert erro.value.status == 422
    for geracao, agora in [("core2", 1001), ("core1", 87400)]:
        with pytest.raises(ErroAPI) as erro:
            ler_cursor(token, SEGREDO, "rota", "filtros", geracao, agora=agora)
        assert erro.value.status == 409


@pytest.mark.parametrize(
    "alteracao",
    [
        {"versao": 2},
        {"versao": True},
        {"chaves": [1]},
        {"chaves": ["x" * 101]},
        {"emitido_em": 2000},
        {"extra": "indevido"},
    ],
)
def test_payload_assinado_malformado_nao_chega_a_consulta(alteracao):
    import base64
    import hashlib
    import hmac
    import json

    dados = {
        "versao": 1,
        "rota": "rota",
        "filtros": "filtros",
        "geracao": "core1",
        "chaves": ["2020-01-02"],
        "emitido_em": 1000,
        "teto": None,
    }
    dados.update(alteracao)
    bruto = base64.urlsafe_b64encode(json.dumps(dados).encode()).rstrip(b"=")
    token = bruto.decode() + "." + hmac.new(SEGREDO, bruto, hashlib.sha256).hexdigest()
    with pytest.raises(ErroAPI) as erro:
        ler_cursor(token, SEGREDO, "rota", "filtros", "core1", agora=1001)
    assert erro.value.status == 422


def test_json_invalido_e_tipos_sao_bloqueados_mesmo_com_assinatura():
    import base64
    import hashlib
    import hmac

    for corpo in [b"{", b"[]", b"\xff"]:
        bruto = base64.urlsafe_b64encode(corpo).rstrip(b"=")
        token = bruto.decode() + "." + hmac.new(SEGREDO, bruto, hashlib.sha256).hexdigest()
        with pytest.raises(ErroAPI):
            ler_cursor(token, SEGREDO, "rota", "filtros", "core1", agora=1001)
