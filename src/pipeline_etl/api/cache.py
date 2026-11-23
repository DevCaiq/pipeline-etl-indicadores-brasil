"""Cache opcional de representações, com autoridade de versão no PostgreSQL."""

import hashlib
import json
import logging
import random
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from typing import Protocol

REGISTRO = logging.getLogger(__name__)
LIMITE_RESPOSTA = 2 * 1024 * 1024
LIBERAR_TRAVA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class ErroBackendCache(Exception):
    """Falha operacional Redis normalizada pelo adaptador da aplicação."""


class ProtocoloRedis(Protocol):
    """Contrato redis-py; o adaptador deve normalizar RedisError em ErroBackendCache."""

    def get(self, name: str) -> bytes | None: ...

    def set(
        self,
        name: str,
        value: bytes | str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
    ) -> object: ...

    def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object: ...


def criar_chave_cache(
    dominio: str,
    camada: str,
    versao: object,
    data_publicacao: object,
    rota: str,
    parametros: Mapping[str, object],
) -> str:
    """Inclui geração, publicação e todos os parâmetros sem revelar valores sensíveis."""
    identidade = json.dumps(
        [dominio, camada, versao, data_publicacao, rota, dict(parametros)],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"v1:{hashlib.sha256(identidade).hexdigest()}"


def _resposta_valida(resposta: object) -> bool:
    if not isinstance(resposta, bytes) or len(resposta) > LIMITE_RESPOSTA:
        return False
    try:
        documento = json.loads(resposta)
    except (ValueError, UnicodeError, RecursionError):
        return False
    return (
        isinstance(documento, dict)
        and "data" in documento
        and isinstance(documento.get("meta"), dict)
    )


class CacheLeitura:
    """Cache sem I/O na construção; o circuito pertence exclusivamente à instância."""

    def __init__(
        self,
        cliente: ProtocoloRedis | None,
        *,
        relogio: Callable[[], float] = time.monotonic,
        esperar: Callable[[float], None] = time.sleep,
        observar: Callable[[str], None] | None = None,
    ) -> None:
        self._cliente = cliente
        self._observador = observar
        self._relogio = relogio
        self._esperar = esperar
        self._aberto_ate = 0.0
        self._trava_circuito = threading.Lock()

    def _observar(self, evento: str) -> None:
        if self._observador is not None:
            try:
                self._observador(evento)
            except Exception:
                REGISTRO.warning("Métrica de cache não registrada.")

    def _disponivel(self) -> bool:
        instante = self._relogio()
        with self._trava_circuito:
            return instante >= self._aberto_ate

    def _registrar_falha(self, erro: Exception) -> None:
        self._observar("falha_backend")
        instante = self._relogio()
        with self._trava_circuito:
            self._aberto_ate = max(self._aberto_ate, instante + 5.0)
        REGISTRO.warning("Cache indisponível; consulta seguirá pelo banco: %s", type(erro).__name__)

    def obter_ou_calcular(
        self,
        chave: str,
        calcular: Callable[[], bytes],
        validade: int = 300,
    ) -> bytes:
        """Consulta Redis com fallback; exceções da consulta nunca são capturadas."""
        if validade <= 0:
            raise ValueError("A validade deve ser positiva.")

        def calcular_observado() -> bytes:
            self._observar("calculo")
            return calcular()

        cliente = self._cliente
        if cliente is None:
            self._observar("desativado")
            return calcular_observado()
        if not self._disponivel():
            self._observar("circuito_aberto")
            return calcular_observado()
        token = secrets.token_hex(16)
        chave_trava = f"{chave}:trava"
        try:
            resposta = cliente.get(chave)
            if _resposta_valida(resposta):
                # A validação acima já exige bytes; assert apenas estreita o tipo estático.
                assert isinstance(resposta, bytes)  # nosec B101
                self._observar("acerto")
                return resposta
            self._observar("ausencia")
            possui_trava = bool(cliente.set(chave_trava, token, nx=True, px=2000))
            if not possui_trava:
                self._observar("trava_ocupada")
                self._esperar(0.05)
                resposta = cliente.get(chave)
                if _resposta_valida(resposta):
                    # A validação acima já exige bytes; não é uma barreira de segurança.
                    assert isinstance(resposta, bytes)  # nosec B101
                    self._observar("acerto")
                    return resposta
        except (ErroBackendCache, OSError) as erro:
            self._registrar_falha(erro)
            return calcular_observado()
        if not possui_trava:
            return calcular_observado()
        try:
            # A consulta fica fora dos blocos que tratam falhas do backend.
            resposta_calculada = calcular_observado()
            if _resposta_valida(resposta_calculada):
                try:
                    # Variação de TTL, sem segredo; o token da trava usa secrets.token_hex.
                    validade_efetiva = max(1, int(validade * (1 + random.uniform(-0.1, 0.1))))  # nosec B311
                    cliente.set(chave, resposta_calculada, ex=validade_efetiva)
                except (ErroBackendCache, OSError) as erro:
                    self._registrar_falha(erro)
            return resposta_calculada
        finally:
            if self._disponivel():
                try:
                    cliente.eval(LIBERAR_TRAVA, 1, chave_trava, token)
                except (ErroBackendCache, OSError) as erro:
                    self._registrar_falha(erro)
