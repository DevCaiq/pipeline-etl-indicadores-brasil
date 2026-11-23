"""Contrato HTTP IBGE sobre amostras oficiais, sem acesso à internet."""

import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.armazenamento.objetos import SistemaArquivosObjetos
from pipeline_etl.processamento.carga_ibge import carregar_ibge, publicar_ibge
from pipeline_etl.processamento.clientes.ibge import ClienteIBGE

pytestmark = pytest.mark.integracao
AMOSTRAS = Path(__file__).resolve().parents[1] / "amostras" / "ibge"


@pytest.fixture
def api_ibge(banco, tmp_path):
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "TRUNCATE core.fato_populacao,core.dim_municipio,core.municipio_snapshot,"
                "core.snapshot_localidades,core.dim_uf,core.dim_regiao CASCADE"
            )
        )
        conexao.execute(text("DELETE FROM ops.publicacao WHERE dominio='ibge'"))
        conexao.execute(text("DELETE FROM ops.lote WHERE fonte='ibge'"))
    corpos = {
        recurso: (AMOSTRAS / (arquivo + ".body")).read_bytes()
        for recurso, arquivo in {
            "regioes": "regioes",
            "estados": "estados",
            "metadados": "metadados",
            "periodos": "periodos",
        }.items()
    }
    municipios = json.loads((AMOSTRAS / "municipios_amostra.body").read_bytes())
    municipios.append(json.loads((AMOSTRAS / "municipio_hierarquia_opcional.body").read_bytes()))
    corpos["municipios"] = json.dumps(municipios).encode()
    populacao = json.loads((AMOSTRAS / "populacao_amostra.body").read_bytes())
    marcador = json.loads((AMOSTRAS / "populacao_marcador.body").read_bytes())
    populacao[0]["resultados"][0]["series"].extend(marcador[0]["resultados"][0]["series"])
    anos = (2020, 2021, 2024, 2025, 2026)
    for ano in anos:
        copia = json.loads(json.dumps(populacao))
        for serie in copia[0]["resultados"][0]["series"]:
            serie["serie"] = {str(ano): serie["serie"][str(ano)]}
        corpos[str(ano)] = json.dumps(copia).encode()

    def responder(requisicao):
        partes = requisicao.url.path.split("/")
        chave = partes[-3] if partes[-1] == "9324" else partes[-1]
        return httpx.Response(200, stream=httpx.ByteStream(corpos[chave]))

    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        coletor = ClienteIBGE(transporte, armazenamento, dormir=lambda _: None)
        manifestos = tuple(
            coletor.coletar(recurso).manifesto
            for recurso in ("regioes", "ufs", "municipios", "metadados", "periodos")
        )
        manifestos += tuple(coletor.coletar("populacao", ano).manifesto for ano in anos)
    assert carregar_ibge(armazenamento, manifestos, banco).situacao == "SUCESSO"
    assert publicar_ibge(banco).situacao == "SUCESSO"
    endereco = banco.url.set(username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"])
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    configuracao = ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48))
    try:
        with TestClient(criar_aplicacao(configuracao, motor)) as cliente:
            yield cliente
    finally:
        motor.dispose()


def test_municipios_paginados_busca_literal_e_condicional(api_ibge):
    primeira = api_ibge.get("/api/v1/municipios?limite=2")
    assert primeira.status_code == 200, primeira.text
    assert [linha["codigo_ibge"] for linha in primeira.json()["data"]] == ["1504752", "3550308"]
    cursor = primeira.json()["pagina"]["proximo_cursor"]
    segunda = api_ibge.get("/api/v1/municipios", params={"limite": 2, "cursor": cursor})
    assert [linha["codigo_ibge"] for linha in segunda.json()["data"]] == ["5101837", "5300108"]
    assert api_ibge.get("/api/v1/municipios", params={"q": "São%"}).json()["data"] == []
    assert len(api_ibge.get("/api/v1/municipios?uf=sp").json()["data"]) == 1
    assert api_ibge.get("/api/v1/municipios/9999999").status_code == 404
    regioes = api_ibge.get("/api/v1/regioes")
    assert (
        api_ibge.get(
            "/api/v1/regioes", headers={"If-None-Match": regioes.headers["ETag"]}
        ).status_code
        == 304
    )


def test_populacao_preserva_ausencia_lacunas_e_total_incompleto(api_ibge):
    resposta = api_ibge.get("/api/v1/municipios/3550308/populacao")
    assert resposta.status_code == 200, resposta.text
    assert [linha["ano"] for linha in resposta.json()["data"]] == [2020, 2021, 2024, 2025, 2026]
    assert resposta.json()["data"][0]["populacao"] == "12325232"
    assert resposta.json()["meta"]["anos_carregados"] == [2020, 2021, 2024, 2025, 2026]
    ausente = api_ibge.get("/api/v1/municipios/5101837/populacao").json()["data"][0]
    assert ausente["populacao"] is None and ausente["marcador"] == "..."
    total = api_ibge.get("/api/v1/populacao/brasil?ano=2020")
    assert total.status_code == 200, total.text
    linha = total.json()["data"][0]
    assert linha["populacao_total"] is None and linha["completo"] is False
    assert linha["municipios_esperados"] == 4
    assert linha["subtotal_disponivel"] == "15396565"


def test_cursor_ibge_rejeita_geracao_alterada(api_ibge, banco):
    primeira = api_ibge.get("/api/v1/municipios?limite=2").json()
    cursor = primeira["pagina"]["proximo_cursor"]
    with banco.begin() as conexao:
        conexao.execute(
            text("UPDATE ops.publicacao SET versao_core=versao_core+1 WHERE dominio='ibge'")
        )
    resposta = api_ibge.get("/api/v1/municipios", params={"limite": 2, "cursor": cursor})
    assert resposta.status_code == 409
