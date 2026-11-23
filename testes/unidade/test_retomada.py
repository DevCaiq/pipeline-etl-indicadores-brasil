"""Retomada é testada com HTTP simulado; nenhuma API externa é consultada."""

import json
from pathlib import Path

import httpx
import pytest


def test_pagina_fila_sem_cancelar_execucoes_remotas(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "orquestracao"))
    import gerenciar

    monkeypatch.setattr(gerenciar, "RAIZ", tmp_path)

    cliente_original = httpx.Client
    cancelados = []
    deslocamentos = []
    pedidos = []

    def responder(requisicao):
        corpo = json.loads(requisicao.content or b"{}")
        caminho = requisicao.url.path.removeprefix("/api")
        if caminho == "/deployments/filter":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "proprio",
                        "name": "bcb-incremental",
                        "work_pool_name": "pipeline-etl-local",
                    },
                    {"id": "externo", "name": "outro", "work_pool_name": "outro"},
                ],
            )
        if caminho == "/flow_runs/filter":
            assert corpo["flow_runs"]["deployment_id"]["any_"] == ["proprio"]
            deslocamentos.append(corpo["offset"])
            if corpo["offset"] == 0:
                return httpx.Response(
                    200,
                    json=[
                        {"id": str(indice), "auto_scheduled": indice != 0} for indice in range(200)
                    ],
                )
            return httpx.Response(200, json=[{"id": "200", "auto_scheduled": True}])
        if caminho.endswith("/set_state"):
            assert corpo["state"]["type"] == "CANCELLED"
            cancelados.append(caminho)
            return httpx.Response(200, json={})
        if caminho.endswith("/create_flow_run"):
            pedidos.append(corpo)
            return httpx.Response(200, json={"id": "retomada"})
        raise AssertionError("Requisição inesperada.")

    monkeypatch.setattr(
        gerenciar.httpx,
        "Client",
        lambda **_: cliente_original(
            base_url="http://127.0.0.1:4200/api", transport=httpx.MockTransport(responder)
        ),
    )
    gerenciar.preparar_retomada()
    assert deslocamentos == [0, 200]
    assert cancelados == []
    assert (tmp_path / ".cache/prefect/retomada_projeto.json").is_file()
    assert len(pedidos) == 1 and pedidos[0]["parameters"] == {"modo": "incremental"}


def test_retomada_ibge_prioriza_reconciliacao_e_preserva_manual(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "orquestracao"))
    import gerenciar

    monkeypatch.setattr(gerenciar, "RAIZ", tmp_path)

    original = httpx.Client
    pedidos = []
    cancelados = []
    registros = [
        {"id": nome, "name": nome, "work_pool_name": "pipeline-etl-local"}
        for nome in ("bcb-incremental", "ibge-incremental", "ibge-reconciliacao", "outro-projeto")
    ]

    def responder(requisicao):
        corpo = json.loads(requisicao.content or b"{}")
        caminho = requisicao.url.path
        if caminho.endswith("/deployments/filter"):
            return httpx.Response(200, json=registros)
        if caminho.endswith("/flow_runs/filter"):
            assert "outro-projeto" not in corpo["flow_runs"]["deployment_id"]["any_"]
            return httpx.Response(
                200,
                json=[
                    {"id": "mensal", "deployment_id": "ibge-incremental", "auto_scheduled": True},
                    {
                        "id": "trimestral",
                        "deployment_id": "ibge-reconciliacao",
                        "auto_scheduled": True,
                    },
                    {
                        "id": "manual",
                        "deployment_id": "ibge-reconciliacao",
                        "auto_scheduled": False,
                    },
                ],
            )
        if caminho.endswith("/set_state"):
            cancelados.append(caminho)
            return httpx.Response(200, json={})
        if caminho.endswith("/create_flow_run"):
            pedidos.append(corpo)
            return httpx.Response(200, json={"id": "nova"})
        raise AssertionError("Requisição inesperada")

    monkeypatch.setattr(
        gerenciar.httpx,
        "Client",
        lambda **_: original(
            base_url="http://127.0.0.1:4200/api", transport=httpx.MockTransport(responder)
        ),
    )
    gerenciar.preparar_retomada()
    assert cancelados == []
    assert [pedido["parameters"]["modo"] for pedido in pedidos] == ["incremental", "reconciliacao"]


def test_falha_ao_criar_substituto_preserva_agenda_vencida(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "orquestracao"))
    import gerenciar

    monkeypatch.setattr(gerenciar, "RAIZ", tmp_path)

    original = httpx.Client
    cancelados = []

    def responder(requisicao):
        caminho = requisicao.url.path
        if caminho.endswith("/deployments/filter"):
            return httpx.Response(
                200,
                json=[
                    {"id": "bcb", "name": "bcb-incremental", "work_pool_name": "pipeline-etl-local"}
                ],
            )
        if caminho.endswith("/flow_runs/filter"):
            return httpx.Response(
                200, json=[{"id": "atrasado", "deployment_id": "bcb", "auto_scheduled": True}]
            )
        if caminho.endswith("/create_flow_run"):
            return httpx.Response(503)
        if caminho.endswith("/set_state"):
            cancelados.append(caminho)
            return httpx.Response(200, json={})
        raise AssertionError("Requisição inesperada")

    monkeypatch.setattr(
        gerenciar.httpx,
        "Client",
        lambda **_: original(
            base_url="http://127.0.0.1:4200/api", transport=httpx.MockTransport(responder)
        ),
    )
    with pytest.raises(httpx.HTTPStatusError):
        gerenciar.preparar_retomada()
    assert cancelados == []
    assert not (tmp_path / ".cache/prefect/retomada_projeto.json").exists()
