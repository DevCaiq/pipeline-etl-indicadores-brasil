"""Contratos IBGE offline; mutações abaixo são casos sintéticos explícitos."""

import json
from pathlib import Path

import pytest

from pipeline_etl.processamento.contratos.ibge import (
    ErroContratoIBGE,
    descobrir_periodos,
    normalizar_localidades,
    normalizar_populacao,
    validar_metadados,
)

AMOSTRAS = Path(__file__).parents[1] / "amostras" / "ibge"
ANOS = {2020, 2021, 2024, 2025, 2026}


def corpo(nome):
    return (AMOSTRAS / (nome + ".body")).read_bytes()


def codificar(dados):
    return json.dumps(dados, ensure_ascii=False).encode("utf-8")


def test_homologa_metadados_periodos_e_populacao_oficiais():
    validar_metadados(corpo("metadados"))
    assert descobrir_periodos(corpo("periodos")) == (2020, 2021, 2024, 2025, 2026)
    linhas = normalizar_populacao(corpo("populacao_marcador"), ANOS, {"5101837"})
    assert [(linha.ano, linha.populacao) for linha in linhas] == [
        (2020, None),
        (2021, None),
        (2024, None),
        (2025, 5877),
        (2026, 5983),
    ]
    assert linhas[0].marcador == "..."
    assert linhas[0].motivo == "DADO_NAO_DISPONIVEL"


def test_hierarquia_opcional_oficial_e_referencias():
    municipios = codificar([json.loads(corpo("municipio_hierarquia_opcional"))])
    resultado = normalizar_localidades(corpo("regioes"), corpo("estados"), municipios)
    assert resultado.municipios[0].codigo_ibge == "5101837"
    assert resultado.municipios[0].uf_codigo == 51
    assert len(resultado.regioes) == 5
    assert len(resultado.ufs) == 27


@pytest.mark.parametrize("valor", ["-", "..", "X", "", "1.0", "-1", "9223372036854775808", 1, True])
def test_recusa_valores_sinteticos_nao_homologados(valor):
    dados = json.loads(corpo("populacao_marcador"))
    dados[0]["resultados"][0]["series"][0]["serie"]["2025"] = valor
    with pytest.raises(ErroContratoIBGE):
        normalizar_populacao(codificar(dados), ANOS, {"5101837"})


@pytest.mark.parametrize("anos,municipios", [({2025}, {"5101837"}), (ANOS, {"3550308"})])
def test_recusa_cobertura_sintetica_divergente(anos, municipios):
    with pytest.raises(ErroContratoIBGE):
        normalizar_populacao(corpo("populacao_marcador"), anos, municipios)


@pytest.mark.parametrize("entrada", [b"\xff", b"{}", b"null", b"[]", b'{"id":6579,"id":1}'])
def test_recusa_metadados_invalidos(entrada):
    with pytest.raises(ErroContratoIBGE):
        validar_metadados(entrada)


def test_recusa_uf_ausente_ou_id_booleano_sintetico():
    municipio = json.loads(corpo("municipio_hierarquia_opcional"))
    for identificador in [True, 5101837.0]:
        municipio["id"] = identificador
        with pytest.raises(ErroContratoIBGE):
            normalizar_localidades(corpo("regioes"), corpo("estados"), codificar([municipio]))
    municipio["id"] = 5101837
    municipio["regiao-imediata"] = None
    with pytest.raises(ErroContratoIBGE):
        normalizar_localidades(corpo("regioes"), corpo("estados"), codificar([municipio]))


def test_recusa_duplicata_sintetica_conflitante():
    dados = json.loads(corpo("populacao_marcador"))
    series = dados[0]["resultados"][0]["series"]
    duplicata = json.loads(json.dumps(series[0]))
    duplicata["serie"]["2025"] = "999"
    series.append(duplicata)
    with pytest.raises(ErroContratoIBGE):
        normalizar_populacao(codificar(dados), ANOS, {"5101837"})


@pytest.mark.parametrize("campo,valor", [("id", "1"), ("unidade", "%")])
def test_recusa_envelope_sintetico_incompativel(campo, valor):
    dados = json.loads(corpo("populacao_amostra"))
    dados[0][campo] = valor
    with pytest.raises(ErroContratoIBGE):
        normalizar_populacao(codificar(dados), ANOS, {"3550308", "5300108", "1504752"})


def test_ordena_e_elimina_duplicatas_identicas_sinteticas():
    dados = json.loads(corpo("populacao_amostra"))
    series = dados[0]["resultados"][0]["series"]
    series.append(series[0])
    linhas = normalizar_populacao(codificar(dados), ANOS, {"3550308", "5300108", "1504752"})
    assert len(linhas) == 15
    assert [(linha.codigo_ibge, linha.ano) for linha in linhas] == sorted(
        (linha.codigo_ibge, linha.ano) for linha in linhas
    )


def test_recusa_hierarquias_sinteticas_conflitantes():
    municipio = json.loads(corpo("municipio_hierarquia_opcional"))
    outra_uf = json.loads(corpo("estados"))[0]
    municipio["microrregiao"] = {"mesorregiao": {"UF": outra_uf}}
    with pytest.raises(ErroContratoIBGE):
        normalizar_localidades(corpo("regioes"), corpo("estados"), codificar([municipio]))


def test_recusa_referencia_regional_sintetica_ausente():
    estados = json.loads(corpo("estados"))
    estados[0]["regiao"]["id"] = 999
    with pytest.raises(ErroContratoIBGE):
        normalizar_localidades(
            corpo("regioes"),
            codificar(estados),
            codificar([json.loads(corpo("municipio_hierarquia_opcional"))]),
        )


@pytest.mark.parametrize("identificador", [True, 2025.0, "202A", None])
def test_recusa_periodos_sinteticos_invalidos(identificador):
    with pytest.raises(ErroContratoIBGE):
        descobrir_periodos(codificar([{"id": identificador}]))


def test_recusa_periodos_sinteticos_conflitantes():
    with pytest.raises(ErroContratoIBGE):
        descobrir_periodos(codificar([{"id": "2025", "literals": ["2025"]}, {"id": "2025"}]))


@pytest.mark.parametrize("mutacao", ["variavel", "unidade", "classificacao", "nivel", "frequencia"])
def test_recusa_metadados_sinteticos_fora_do_contrato(mutacao):
    dados = json.loads(corpo("metadados"))
    if mutacao == "variavel":
        dados["variaveis"][0]["id"] = True
    elif mutacao == "unidade":
        dados["variaveis"][0]["unidade"] = "%"
    elif mutacao == "classificacao":
        dados["classificacoes"] = [{"id": 1}]
    elif mutacao == "nivel":
        dados["nivelTerritorial"]["Administrativo"] = ["N3"]
    else:
        dados["periodicidade"]["frequencia"] = "mensal"
    with pytest.raises(ErroContratoIBGE):
        validar_metadados(codificar(dados))
