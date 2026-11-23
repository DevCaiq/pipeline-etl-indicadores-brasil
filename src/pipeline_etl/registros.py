"""Registros estruturados em stderr, separados da saída dos comandos."""

import logging
import sys

import structlog
from structlog.types import EventDict, WrappedLogger


def padronizar_evento(registrador: WrappedLogger, metodo: str, evento: EventDict) -> EventDict:
    """Traduz campos internos do structlog para o contrato de registros próprio."""
    evento["mensagem"] = evento.pop("event")
    evento["nivel"] = evento.pop("level")
    return evento


def configurar_registros(nivel: str) -> None:
    """Configura JSON UTF-8 sem acumular handlers a cada chamada."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="instante"),
            padronizar_evento,
            structlog.processors.JSONRenderer(ensure_ascii=True, sort_keys=True),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[nivel]),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
