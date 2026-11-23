"""Contrato HTTP sem banco disponível."""

from fastapi.testclient import TestClient
from pydantic import SecretStr

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.configuracao import ConfiguracaoAplicacao


def test_aplicacao_expoe_rotas_ibge_e_metricas_sem_banco():
    aplicacao = criar_aplicacao(ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48)))
    with TestClient(aplicacao) as cliente:
        assert cliente.get("/health").status_code == 200
        resposta = cliente.get("/metrics")
        assert resposta.status_code == 200
        assert "text/plain" in resposta.headers["content-type"]
        assert 'rota="/health"' in resposta.text
        assert "pipeline_coleta_disponivel 0.0" in resposta.text
        assert cliente.get("/api/v1/regioes").status_code == 503
        rotas = cliente.get("/openapi.json").json()["paths"]
        assert "/api/v1/municipios/{codigo_ibge}/populacao" in rotas


def test_health_independe_de_banco_e_ready_informa_503():
    with TestClient(
        criar_aplicacao(ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48)))
    ) as cliente:
        assert cliente.get("/health").status_code == 200
        resposta = cliente.get("/ready")
        assert resposta.status_code == 503
        assert resposta.json()["erro"]["requisicao_id"] == resposta.headers["X-Request-ID"]
        assert resposta.headers["Cache-Control"] == "no-store"
        assert cliente.get("/api/v1/series").status_code == 503


def test_api_valida_intervalos_sem_expor_entradas_e_limita_requisicoes():
    configuracao = ConfiguracaoAplicacao(
        segredo_cursor=SecretStr("s" * 48), limite_requisicoes_minuto=3
    )
    with TestClient(criar_aplicacao(configuracao)) as cliente:
        for consulta in ["de=2019-01-01", "limite=1001", "de=2020-01-03&ate=2020-01-01"]:
            resposta = cliente.get("/api/v1/series/432/observacoes?" + consulta)
            assert resposta.status_code == 422
        resposta = cliente.get("/api/v1/series")
        assert resposta.status_code == 429 and "Retry-After" in resposta.headers
        assert cliente.get("/health").status_code == 200


def test_excecoes_banco_e_internas_sao_sanitizadas(monkeypatch):
    import pytest
    from sqlalchemy import create_engine

    from pipeline_etl.api.repositorio import RepositorioLeitura

    configuracao = ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48))
    motor = create_engine(
        "postgresql+psycopg://teste:segredo@127.0.0.1:1/etl_testes",
        connect_args={"connect_timeout": 2},
        hide_parameters=True,
    )
    try:
        with TestClient(criar_aplicacao(configuracao, motor)) as cliente:
            resposta = cliente.get("/ready")
            assert resposta.status_code == 503 and "segredo" not in resposta.text
    finally:
        motor.dispose()

    def interromper(*argumentos, **opcoes):
        raise RuntimeError("detalhe-confidencial")

    monkeypatch.setattr(RepositorioLeitura, "estado", interromper)
    with TestClient(criar_aplicacao(configuracao)) as cliente:
        # Erro técnico antes da abertura do banco não é possível sem motor; simula o contexto.
        from contextlib import contextmanager

        @contextmanager
        def contexto(*argumentos):
            yield None

        monkeypatch.setattr(RepositorioLeitura, "instantaneo", contexto)
        resposta = cliente.get("/api/v1/series")
        assert resposta.status_code == 500
        assert "detalhe-confidencial" not in resposta.text
    with pytest.raises(ValueError):
        criar_aplicacao(ConfiguracaoAplicacao(segredo_cursor=SecretStr("curto")))


def test_limite_local_expira_e_capacidade_e_limitada():
    from pipeline_etl.api.limites import LimitadorLocal

    agora = [0.0]
    limitador = LimitadorLocal(1, lambda: agora[0])
    assert limitador.conferir("cliente") == 0
    assert limitador.conferir("cliente") == 60
    agora[0] = 61
    assert limitador.conferir("cliente") == 0
    for indice in range(4095):
        assert limitador.conferir(str(indice)) == 0
    assert limitador.conferir("sem_espaco") == 60
    agora[0] = 122
    assert limitador.conferir("sem_espaco") == 0


def test_exemplos_openapi_sao_validos_para_os_modelos():
    from pydantic import TypeAdapter

    aplicacao = criar_aplicacao(ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48)))
    for rota in aplicacao.routes:
        modelo = getattr(rota, "response_model", None)
        if modelo is not None:
            for exemplo in rota.responses[200]["content"]["application/json"]["examples"].values():
                TypeAdapter(modelo).validate_python(exemplo["value"])


def test_datas_exigem_iso_de_calendario_sem_coercao_unix_ou_timestamp():
    with TestClient(
        criar_aplicacao(ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48)))
    ) as cliente:
        for data in ["1577836800", "2020-01-01T00:00:00Z", "20200101"]:
            assert (
                cliente.get("/api/v1/series/432/observacoes", params={"de": data}).status_code
                == 422
            )
