"""Métricas isoladas, sem rede nem consultas a fontes externas."""

import asyncio
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
from starlette.types import Receive, Scope, Send

from pipeline_etl.api.metricas import EstatisticasPipeline, MetricasAPI, MiddlewareMetricas


@pytest.fixture(autouse=True)
def isolar_metricas_complementares(monkeypatch):
    # Este arquivo verifica a família anterior; o módulo complementar tem testes próprios.
    monkeypatch.setattr("pipeline_etl.api.metricas.coletar_operacionais", lambda conexao: [])


def test_conta_rota_parametrizada_e_exclui_metricas() -> None:
    metricas = MetricasAPI()
    aplicacao = FastAPI()
    aplicacao.add_middleware(MiddlewareMetricas, metricas=metricas)

    @aplicacao.get("/series/{codigo}")
    def consultar(codigo: int) -> dict[str, int]:
        return {"codigo": codigo}

    @aplicacao.get("/metrics")
    def consultar_metricas() -> str:
        return "métricas"

    with TestClient(aplicacao) as cliente:
        cliente.get("/series/1")
        cliente.get("/series/433")
        cliente.get("/metrics")
    conteudo = metricas.gerar().decode()
    assert (
        'http_requisicoes_total{metodo="GET",rota="/series/{codigo}",status="200"} 2.0' in conteudo
    )
    assert (
        'http_duracao_segundos_count{metodo="GET",rota="/series/{codigo}",status="200"} 2.0'
        in conteudo
    )
    assert "/metrics" not in conteudo
    assert "/series/433" not in conteudo


def test_urls_desconhecidas_nao_aumentam_cardinalidade() -> None:
    metricas = MetricasAPI()
    aplicacao = FastAPI()
    aplicacao.add_middleware(MiddlewareMetricas, metricas=metricas)
    with TestClient(aplicacao) as cliente:
        for indice in range(20):
            cliente.get(f"/inexistente/{indice}?segredo=oculto")
    conteudo = metricas.gerar().decode()
    assert (
        'http_requisicoes_total{metodo="GET",rota="nao_encontrada",status="404"} 20.0' in conteudo
    )
    assert "inexistente" not in conteudo
    assert "oculto" not in conteudo


def test_excecao_da_aplicacao_continua_visivel() -> None:
    metricas = MetricasAPI()

    async def falhar(escopo: Scope, receber: Receive, enviar: Send) -> None:
        raise RuntimeError("Falha deliberada da aplicação.")

    middleware = MiddlewareMetricas(falhar, metricas)
    with pytest.raises(RuntimeError, match="deliberada"):
        asyncio.run(middleware({"type": "http", "method": "SEGREDO"}, MagicMock(), MagicMock()))
    assert 'metodo="OUTRO",rota="nao_encontrada",status="500"' in metricas.gerar().decode()


def test_falha_coleta_nao_interrompe_exposicao_nem_vaza_erro() -> None:
    motor = MagicMock()
    motor.connect.side_effect = RuntimeError("senha=segredo")
    metricas = MetricasAPI()
    metricas.registro.register(EstatisticasPipeline(motor))
    conteudo = metricas.gerar().decode()
    assert "pipeline_coleta_disponivel 0.0" in conteudo
    assert "segredo" not in conteudo
    assert "pipeline_serie_defasada" not in conteudo


def test_coleta_somente_leitura_limita_rotulos() -> None:
    motor = MagicMock()
    conexao = motor.connect.return_value.__enter__.return_value
    conexao.execute.return_value.mappings.return_value.all.side_effect = [
        [{"situacao": "SUCESSO", "quantidade": 8}, {"situacao": "erro_privado", "quantidade": 1}],
        [{"codigo_sgs": 433, "fim": None}, {"codigo_sgs": 999, "fim": None}],
        [],
    ]
    registro = CollectorRegistry()
    registro.register(EstatisticasPipeline(motor))
    metricas = MetricasAPI(registro)
    conteudo = metricas.gerar().decode()
    comandos = [str(chamada.args[0]) for chamada in conexao.execute.call_args_list]
    assert comandos[0] == "SET TRANSACTION READ ONLY"
    assert 'pipeline_execucoes{situacao="SUCESSO"} 8.0' in conteudo
    assert 'pipeline_serie_defasada{serie="433"} -1.0' in conteudo
    assert "erro_privado" not in conteudo
    assert 'serie="999"' not in conteudo
    assert "pipeline_coleta_disponivel 1.0" in conteudo


def test_exporta_fases_persistidas_sem_rotulos_arbitrarios() -> None:
    motor = MagicMock()
    conexao = motor.connect.return_value.__enter__.return_value
    conexao.execute.return_value.mappings.return_value.all.side_effect = [
        [],
        [],
        [
            {
                "modo": "carga_ibge",
                "situacao": "SUCESSO",
                "quantidade": 2,
                "duracao_media": 3.5,
                "ultima_conclusao": 100.0,
            },
            {
                "modo": "pipeline_bcb",
                "situacao": "FALHA",
                "quantidade": 1,
                "duracao_media": 0.0,
                "ultima_conclusao": 200.0,
            },
            {
                "modo": "segredo",
                "situacao": "SUCESSO",
                "quantidade": 1,
                "duracao_media": 1.0,
                "ultima_conclusao": 200.0,
            },
            {
                "modo": "carga_ibge",
                "situacao": "EM_EXECUCAO",
                "quantidade": 1,
                "duracao_media": 1.0,
                "ultima_conclusao": 200.0,
            },
        ],
    ]
    metricas = MetricasAPI()
    metricas.registro.register(EstatisticasPipeline(motor))
    conteudo = metricas.gerar().decode()
    rotulos = 'fase="carga_ibge",fonte="ibge",situacao="SUCESSO"'
    assert f"pipeline_fase_execucoes{{{rotulos}}} 2.0" in conteudo
    assert f"pipeline_fase_duracao_media_segundos{{{rotulos}}} 3.5" in conteudo
    assert f"pipeline_fase_ultima_conclusao_segundos{{{rotulos}}} 100.0" in conteudo
    assert 'fase="pipeline_bcb",fonte="bcb",situacao="FALHA"' in conteudo
    assert "segredo" not in conteudo
    assert "EM_EXECUCAO" not in conteudo
    comandos = [str(chamada.args[0]) for chamada in conexao.execute.call_args_list]
    assert "finalizado_em >= iniciado_em" in comandos[-1]


def test_falha_na_consulta_das_fases_nao_publica_resultado_parcial() -> None:
    motor = MagicMock()
    conexao = motor.connect.return_value.__enter__.return_value
    conexao.execute.return_value.mappings.return_value.all.side_effect = [
        [{"situacao": "SUCESSO", "quantidade": 2}],
        [],
        RuntimeError("senha=segredo"),
    ]
    metricas = MetricasAPI()
    metricas.registro.register(EstatisticasPipeline(motor))
    conteudo = metricas.gerar().decode()
    assert "pipeline_coleta_disponivel 0.0" in conteudo
    assert "pipeline_fase_" not in conteudo
    assert "pipeline_execucoes" not in conteudo
    assert "segredo" not in conteudo
