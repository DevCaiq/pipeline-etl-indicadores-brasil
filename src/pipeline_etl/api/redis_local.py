"""Adaptador Redis síncrono com limites locais e falhas normalizadas."""

from contextlib import suppress
from typing import Any

from redis import Redis
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from redis.retry import Retry

from pipeline_etl.api.cache import ErroBackendCache
from pipeline_etl.configuracao import ConfiguracaoAplicacao


class RedisLocal:
    """Preserva o contrato redis-py sem capturar erros de programação."""

    def __init__(self, cliente: Redis) -> None:
        self._cliente = cliente

    def get(self, name: str) -> bytes | None:
        try:
            resposta = self._cliente.get(name)
        except RedisError as erro:
            raise ErroBackendCache("Falha na leitura do cache.") from erro
        if resposta is None or isinstance(resposta, bytes):
            return resposta
        raise TypeError("O cliente Redis deve retornar bytes.")

    def set(
        self,
        name: str,
        value: bytes | str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
    ) -> object:
        try:
            return self._cliente.set(name, value, ex=ex, px=px, nx=nx)
        except RedisError as erro:
            raise ErroBackendCache("Falha na escrita do cache.") from erro

    def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object:
        try:
            return self._cliente.eval(script, numkeys, *keys_and_args)
        except RedisError as erro:
            raise ErroBackendCache("Falha na liberação do cache.") from erro

    def fechar(self) -> None:
        """Libera o pool; indisponibilidade do cache não impede o encerramento."""
        with suppress(RedisError):
            self._cliente.close()


def criar_cliente_redis(configuracao: ConfiguracaoAplicacao) -> RedisLocal | None:
    """Constrói o cliente sem estabelecer conexão de rede."""
    if not configuracao.cache_habilitado:
        return None
    # Pydantic já exige URL ao habilitar cache; assert apenas estreita o tipo.
    assert configuracao.url_redis is not None  # nosec B101
    opcoes: dict[str, Any] = {
        "socket_connect_timeout": 0.1,
        "socket_timeout": 0.1,
        "retry": Retry(NoBackoff(), 0),
        "retry_on_error": [],
        "max_connections": 8,
        "decode_responses": False,
    }
    return RedisLocal(Redis.from_url(configuracao.url_redis.get_secret_value(), **opcoes))
