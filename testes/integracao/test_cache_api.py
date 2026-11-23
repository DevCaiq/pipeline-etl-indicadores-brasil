"""Cache HTTP com Redis falso e autoridade PostgreSQL real."""

import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, text

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.api.cache import CacheLeitura, ErroBackendCache
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao

pytestmark = pytest.mark.integracao


class RedisFalso:
    """Backend determinístico que registra acessos e pode falhar."""

    def __init__(self):
        self.valores = {}
        self.leituras = 0
        self.falhar = False

    def get(self, name):
        self.leituras += 1
        if self.falhar:
            raise ErroBackendCache("indisponível")
        return self.valores.get(name)

    def set(self, name, value, *, ex=None, px=None, nx=False):
        if nx and name in self.valores:
            return False
        self.valores[name] = value
        return True

    def eval(self, script, numkeys, *keys_and_args):
        chave, token = keys_and_args
        if self.valores.get(chave) == token:
            del self.valores[chave]
        return 1


@pytest.fixture
def api_cache(banco):
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO ops.publicacao(dominio,versao_core) VALUES('bcb',41) "
                "ON CONFLICT(dominio) DO UPDATE SET versao_core=41, situacao='PENDENTE'"
            )
        )
    endereco = banco.url.set(username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"])
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    aplicacao = criar_aplicacao(ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48)), motor)
    falso = RedisFalso()
    aplicacao.state.cache_leitura = CacheLeitura(falso)
    consultas = []

    def registrar(conexao, cursor, comando, parametros, contexto, muitos):
        consultas.append(comando)

    event.listen(motor, "before_cursor_execute", registrar)
    try:
        with TestClient(aplicacao) as cliente:
            yield cliente, falso, consultas
    finally:
        event.remove(motor, "before_cursor_execute", registrar)
        motor.dispose()
        with banco.begin() as conexao:
            conexao.execute(text("DELETE FROM ops.publicacao WHERE dominio='bcb'"))


def test_hit_confere_autoridade_pula_dados_e_preserva_304(api_cache, banco):
    cliente, falso, consultas = api_cache
    inicial = cliente.get("/api/v1/series")
    assert inicial.status_code == 200, inicial.text
    consultas.clear()
    repetida = cliente.get("/api/v1/series", headers={"If-None-Match": inicial.headers["ETag"]})
    assert repetida.status_code == 304
    assert any("v_publicacao_api" in comando for comando in consultas)
    assert not any("FROM core.dim_serie s" in comando for comando in consultas)
    assert falso.leituras == 2
    with banco.begin() as conexao:
        conexao.execute(text("UPDATE ops.publicacao SET versao_core=42 WHERE dominio='bcb'"))
    consultas.clear()
    nova = cliente.get("/api/v1/series", headers={"If-None-Match": inicial.headers["ETag"]})
    assert nova.status_code == 200
    assert nova.json()["meta"]["versao_core"] == 42
    assert any("FROM core.dim_serie s" in comando for comando in consultas)


def test_falha_redis_e_probes_sem_cache(api_cache):
    cliente, falso, consultas = api_cache
    falso.falhar = True
    assert cliente.get("/api/v1/series").status_code == 200
    leituras = falso.leituras
    for rota in ["/health", "/ready", "/api/v1/pipeline/execucoes", "/api/v1/pipeline/frescor"]:
        assert cliente.get(rota).status_code == 200
    assert falso.leituras == leituras


def test_gold_muda_geracao_na_publicacao_e_pendencia(api_cache, banco):
    from pipeline_etl.processamento.publicacao import publicar_bcb

    cliente, falso, consultas = api_cache
    rota = "/api/v1/series/432/agregados"
    inicial = cliente.get(rota)
    assert inicial.status_code == 200, inicial.text
    consultas.clear()
    assert cliente.get(rota).content == inicial.content
    assert not any("FROM core.dim_serie s" in comando for comando in consultas)
    assert any("pg_try_advisory_lock_shared" in comando for comando in consultas)
    publicar_bcb(banco)
    publicada = cliente.get(rota)
    assert publicada.status_code == 200, publicada.text
    assert publicada.json()["meta"]["versao_gold"] == 41
    with banco.begin() as conexao:
        conexao.execute(text("UPDATE ops.publicacao SET situacao='PENDENTE' WHERE dominio='bcb'"))
    consultas.clear()
    pendente = cliente.get(rota)
    assert pendente.status_code == 200
    assert pendente.json()["meta"]["desatualizado"] is True
    assert any("FROM core.dim_serie s" in comando for comando in consultas)
    assert len([chave for chave in falso.valores if not chave.endswith(":trava")]) == 3


def test_erros_nao_sao_armazenados_e_parametros_separam_paginas(api_cache):
    cliente, falso, consultas = api_cache
    for _ in range(2):
        assert cliente.get("/api/v1/series/999").status_code == 404
    assert not falso.valores
    rota = "/api/v1/series/432/observacoes"
    for limite in [1, 2]:
        resposta = cliente.get(rota, params={"limite": limite})
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["pagina"]["limite"] == limite
    assert len(falso.valores) == 2
    assert all(len(chave) == 67 and chave.startswith("v1:") for chave in falso.valores)


@pytest.mark.parametrize(
    "rota,tipo,codigo,camada",
    [
        ("/api/v1/series/432/observacoes", "observacoes", 432, "core"),
        ("/api/v1/series/432/agregados", "agregados", 432, "gold"),
        ("/api/v1/indicadores/ipca-12m", "ipca12m", 433, "gold"),
    ],
)
def test_cursor_expira_antes_do_hit_mesmo_sem_mudar_hoje(
    api_cache, banco, monkeypatch, rota, tipo, codigo, camada
):
    from types import SimpleNamespace

    from pipeline_etl.api import cursores
    from pipeline_etl.api.filtros import FiltrosAgregados, FiltrosPeriodo
    from pipeline_etl.api.repositorio import RepositorioLeitura

    cliente, falso, consultas = api_cache
    instante = int(cursores.time.time())
    # Troca somente o relógio do módulo de cursores; monotonic e hoje ficam intactos.
    monkeypatch.setattr(cursores, "time", SimpleNamespace(time=lambda: instante))
    repositorio = RepositorioLeitura(banco, b"s" * 48)
    with repositorio.instantaneo() as conexao:
        estado = repositorio.estado(conexao)
    filtros = FiltrosAgregados(limite=1) if tipo == "agregados" else FiltrosPeriodo(limite=1)
    # Um cursor assinado de segunda página, após a primeira chave do período.
    cursor = cursores.assinar_cursor(
        b"s" * 48,
        f"{tipo}:{codigo}",
        cursores.resumir_filtros(filtros.model_dump(exclude={"cursor"})),
        repositorio.geracao(estado, camada),
        ["2020-01-02"],
    )
    parametros = {"limite": 1, "cursor": cursor}
    primeira = cliente.get(rota, params=parametros)
    assert primeira.status_code == 200, primeira.text
    consultas.clear()
    assert cliente.get(rota, params=parametros).content == primeira.content
    assert not any("FROM core.dim_serie s" in comando for comando in consultas)
    leituras = falso.leituras
    instante += 86401
    expirada = cliente.get(rota, params=parametros)
    assert expirada.status_code == 409, expirada.text
    assert expirada.json()["erro"]["codigo"] == "CURSOR_EXPIRADO"
    assert falso.leituras == leituras


def test_fabrica_exporta_metricas_de_cache_e_fallback(banco, monkeypatch):
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO ops.publicacao(dominio,versao_core) VALUES('bcb',41) "
                "ON CONFLICT(dominio) DO UPDATE SET versao_core=41"
            )
        )
    falso = RedisFalso()
    falso.fechar = lambda: None
    monkeypatch.setattr(
        "pipeline_etl.api.aplicacao.criar_cliente_redis", lambda configuracao: falso
    )
    motor = criar_motor(
        SecretStr(
            banco.url.set(
                username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"]
            ).render_as_string(hide_password=False)
        )
    )
    try:
        aplicacao = criar_aplicacao(
            ConfiguracaoAplicacao(segredo_cursor=SecretStr("s" * 48)), motor
        )
        with TestClient(aplicacao) as cliente:
            assert cliente.get("/api/v1/series").status_code == 200
            assert cliente.get("/api/v1/series").status_code == 200
            falso.falhar = True
            assert cliente.get("/api/v1/series").status_code == 200
            conteudo = cliente.get("/metrics").text
            assert 'cache_eventos_total{evento="acerto"} 1.0' in conteudo
            assert 'cache_eventos_total{evento="calculo"} 2.0' in conteudo
            assert 'cache_eventos_total{evento="falha_backend"} 1.0' in conteudo
    finally:
        motor.dispose()
        with banco.begin() as conexao:
            conexao.execute(text("DELETE FROM ops.publicacao WHERE dominio='bcb'"))
