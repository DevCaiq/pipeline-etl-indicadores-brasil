"""Rejeições defensivas com mutações sintéticas de amostras preservadas."""

import json
from pathlib import Path

import pytest

from pipeline_etl.processamento.contratos.ibge import (
    ErroContratoIBGE,
    normalizar_localidades,
    normalizar_populacao,
    validar_metadados,
)

AMOSTRAS = Path(__file__).parents[1] / "amostras" / "ibge"
ANOS = {2020, 2021, 2024, 2025, 2026}


def corpo(nome):
    return (AMOSTRAS / (nome + ".body")).read_bytes()


def codificar(dados):
    return json.dumps(dados).encode()


@pytest.mark.parametrize(
    "anos,municipios", [(set(), {"5101837"}), ({2019}, {"5101837"}), (ANOS, set()), (ANOS, {"123"})]
)
def test_recusa_recorte_invalido_antes_de_normalizar(anos, municipios):
    with pytest.raises(ErroContratoIBGE):
        normalizar_populacao(corpo("populacao_marcador"), anos, municipios)


@pytest.mark.parametrize("mutacao", ["envelope", "classificacao", "cobertura", "objeto"])
def test_recusa_estrutura_ou_cobertura_populacional_incompativel(mutacao):
    dados = json.loads(corpo("populacao_marcador"))
    municipios = {"5101837"}
    if mutacao == "envelope":
        dados.append(dados[0])
    elif mutacao == "classificacao":
        dados[0]["resultados"][0]["classificacoes"] = [{"id": "1"}]
    elif mutacao == "cobertura":
        municipios.add("3550308")
    else:
        dados[0]["resultados"][0] = []
    with pytest.raises(ErroContratoIBGE):
        normalizar_populacao(codificar(dados), ANOS, municipios)


def test_recusa_multiplas_variaveis_mesmo_com_populacao_presente():
    dados = json.loads(corpo("metadados"))
    dados["variaveis"].append({"id": 123, "unidade": "Pessoas"})
    with pytest.raises(ErroContratoIBGE):
        validar_metadados(codificar(dados))


@pytest.mark.parametrize("mutacao", ["nome_vazio", "uf_divergente"])
def test_recusa_territorio_sem_nome_ou_com_uf_divergente(mutacao):
    municipio = json.loads(corpo("municipio_hierarquia_opcional"))
    if mutacao == "nome_vazio":
        municipio["nome"] = "  "
    else:
        municipio["regiao-imediata"]["regiao-intermediaria"]["UF"]["nome"] = "Divergente"
    with pytest.raises(ErroContratoIBGE):
        normalizar_localidades(corpo("regioes"), corpo("estados"), codificar([municipio]))
