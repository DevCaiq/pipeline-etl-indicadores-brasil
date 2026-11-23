"""Contratos públicos tipados; nenhum payload operacional interno."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

from pipeline_etl.processamento.indicadores import formatar_decimal


class Cobertura(BaseModel):
    inicio: date | None = None
    fim: date | None = None
    observacoes: int = 0
    unidade_contagem: Literal["observacoes", "periodos"] = "observacoes"
    completa: bool | None = None
    motivo: str = "CALENDARIO_NAO_HOMOLOGADO"


class Metadados(BaseModel):
    camada: str
    versao_dados: int
    versao_core: int = 0
    versao_gold: int = 0
    data_publicacao: date | None = None
    desatualizado: bool = False
    motivo: str | None = None
    codigo: int | None = None
    unidade: str | None = None
    de: date | None = None
    ate: date | None = None
    cobertura: Cobertura | None = None


class Pagina(BaseModel):
    limite: int
    proximo_cursor: str | None = None
    tem_mais: bool = False


class RespostaPaginada[Item](BaseModel):
    data: list[Item]
    pagina: Pagina
    meta: Metadados


class RespostaDados[Item](BaseModel):
    data: Item
    meta: Metadados


class Serie(BaseModel):
    codigo: int
    nome: str
    periodicidade: str
    unidade: str
    inicio_publico: date
    cobertura: Cobertura
    regra: str


class Observacao(BaseModel):
    data: date
    valor: str

    @field_validator("valor", mode="before")
    @classmethod
    def representar_valor(cls, valor: object) -> object:
        return formatar_decimal(valor) if isinstance(valor, Decimal) else valor


class Agregado(BaseModel):
    periodo: date
    unidade: str
    observacoes: int
    media: str | None = None
    minimo: str | None = None
    maximo: str | None = None
    ultimo: str | None = None
    variacao: str | None = None
    completo: bool | None
    parcial: bool
    motivo: str | None
    data_referencia: date

    @field_validator("media", "minimo", "maximo", "ultimo", "variacao", mode="before")
    @classmethod
    def representar_valor(cls, valor: object) -> object:
        return formatar_decimal(valor) if isinstance(valor, Decimal) else valor


class Execucao(BaseModel):
    execucao_id: UUID
    modo: str
    fonte: str | None
    situacao: str
    iniciado_em: datetime
    finalizado_em: datetime | None

    @field_validator("iniciado_em", "finalizado_em")
    @classmethod
    def normalizar_utc(cls, valor: datetime | None) -> datetime | None:
        return valor.astimezone(UTC) if valor is not None else None


class Frescor(BaseModel):
    codigo: int
    unidade: str
    cobertura: Cobertura
    ultima_consulta: datetime | None
    ultima_referencia: date | None
    ultima_publicacao: datetime | None
    defasado: bool | None
    politica: str
    calendario_homologado: bool = False
    motivo: str | None = None
    referencia_esperada: date | None = None
    data_limite: date | None = None
    versao_calendario: str | None = None

    @field_validator("ultima_consulta", "ultima_publicacao")
    @classmethod
    def normalizar_utc(cls, valor: datetime | None) -> datetime | None:
        return valor.astimezone(UTC) if valor is not None else None


class EstadoServico(BaseModel):
    situacao: str
    esquema: str | None = None
