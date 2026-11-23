"""Adaptador Redis sem rede e configuração condicional."""

from unittest.mock import Mock

import pytest
from pydantic import SecretStr, ValidationError
from redis.exceptions import ConnectionError as ErroConexaoRedis

from pipeline_etl.api.cache import ErroBackendCache
from pipeline_etl.api.redis_local import RedisLocal, criar_cliente_redis
from pipeline_etl.configuracao import ConfiguracaoAplicacao


def test_adaptador_normaliza_somente_redis():
    cliente = Mock()
    adaptador = RedisLocal(cliente)
    for metodo, argumentos in [
        ("get", ("chave",)),
        ("set", ("chave", b"valor")),
        ("eval", ("script", 1, "chave")),
    ]:
        getattr(cliente, metodo).side_effect = ErroConexaoRedis("segredo")
        with pytest.raises(ErroBackendCache) as captura:
            getattr(adaptador, metodo)(*argumentos)
        assert isinstance(captura.value.__cause__, ErroConexaoRedis)
        getattr(cliente, metodo).side_effect = TypeError("erro de programação")
        with pytest.raises(TypeError):
            getattr(adaptador, metodo)(*argumentos)
    adaptador.fechar()
    cliente.close.assert_called_once()


def test_construcao_sem_rede_e_limites(monkeypatch):
    construir = Mock()
    monkeypatch.setattr("pipeline_etl.api.redis_local.Redis.from_url", construir)
    assert criar_cliente_redis(ConfiguracaoAplicacao()) is None
    assert not construir.called
    criar_cliente_redis(
        ConfiguracaoAplicacao(
            cache_habilitado=True, url_redis=SecretStr("redis://localhost:6379/0")
        )
    )
    opcoes = construir.call_args.kwargs
    assert opcoes["socket_connect_timeout"] == opcoes["socket_timeout"] == 0.1
    assert opcoes["max_connections"] == 8
    assert opcoes["retry"].get_retries() == 0


def test_configuracao_cache_condicional():
    ConfiguracaoAplicacao(url_redis=SecretStr("desabilitado"))
    for endereco in [
        None,
        "http://localhost",
        "redis://localhost:errada",
        "redis://localhost?socket_timeout=90",
    ]:
        with pytest.raises(ValidationError):
            ConfiguracaoAplicacao(
                cache_habilitado=True, url_redis=SecretStr(endereco) if endereco else None
            )
