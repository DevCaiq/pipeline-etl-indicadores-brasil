"""Filtros limitados antes da consulta ao banco."""

import re
from datetime import date, datetime
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def hoje_brasil() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


class Paginacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    limite: int = Field(default=100, ge=1, le=1000)
    cursor: str | None = Field(default=None, max_length=2048)


class FiltrosPeriodo(Paginacao):
    de: date = date(2020, 1, 1)
    ate: date = Field(default_factory=hoje_brasil)

    @field_validator("de", "ate", mode="before")
    @classmethod
    def exigir_data_iso(cls, valor: object) -> object:
        if isinstance(valor, str) and not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", valor):
            raise ValueError("Data deve usar YYYY-MM-DD.")
        return valor

    @model_validator(mode="after")
    def validar_periodo(self) -> Self:
        if (
            not date(2020, 1, 1) <= self.de <= self.ate <= hoje_brasil()
            or (self.ate - self.de).days + 1 > 3660
        ):
            raise ValueError("Período fora do recorte ou limite de3660dias.")
        return self


class FiltrosAgregados(FiltrosPeriodo):
    granularidade: Literal["mes", "ano"] = "mes"


class FiltrosExecucoes(Paginacao):
    fonte: Literal["bcb"] | None = None
    situacao: Literal["EM_EXECUCAO", "SUCESSO", "PARCIAL", "FALHA", "IGNORADA"] | None = None
