"""Contrato SGS: datas textuais e medidas decimais exatas."""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, ConfigDict, field_validator


class ObservacaoSGS(BaseModel):
    """Converte uma observação sem aceitar coerção de números JSON para texto."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    data: date
    valor: Decimal

    @field_validator("data", mode="before")
    @classmethod
    def interpretar_data(cls, valor: object) -> date:
        if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", valor):
            raise ValueError("Data deve usar DD/MM/AAAA.")
        return datetime.strptime(valor, "%d/%m/%Y").date()

    @field_validator("valor", mode="before")
    @classmethod
    def interpretar_valor(cls, valor: object) -> Decimal:
        if not isinstance(valor, str) or not re.fullmatch(
            r"[+-]?[0-9]+(?:[.,][0-9]+)?(?:[eE][+-]?[0-9]+)?", valor.strip()
        ):
            raise ValueError("Medida deve ser texto decimal.")
        try:
            numero = Decimal(valor.replace(",", "."))
        except InvalidOperation as erro:
            raise ValueError("Medida decimal inválida.") from erro
        # A gramática aceita somente números finitos; NaN/Infinity não chegam ao Decimal.
        expoente = numero.as_tuple().exponent
        if not isinstance(expoente, int) or expoente < -10 or numero.copy_abs() >= Decimal("1e14"):
            raise ValueError("Medida não cabe em NUMERIC(24,10).")
        return numero
