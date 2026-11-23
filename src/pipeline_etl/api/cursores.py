"""Cursores assinados: identidade de consulta e geração, sem confiança no cliente."""

import base64
import hashlib
import hmac
import json
import re
import time

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError

from pipeline_etl.api.erros import ErroAPI
from pipeline_etl.processamento.qualidade import interpretar_json


class ConteudoCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    versao: StrictInt
    rota: str = Field(max_length=150)
    filtros: str = Field(max_length=150)
    geracao: str = Field(max_length=150)
    chaves: list[str] = Field(min_length=1, max_length=2)
    emitido_em: StrictInt
    teto: str | None = Field(default=None, max_length=100)


def resumir_filtros(filtros: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(filtros, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def assinar_cursor(
    segredo: bytes,
    rota: str,
    filtros: str,
    geracao: str,
    chaves: list[str],
    *,
    teto: str | None = None,
    agora: int | None = None,
) -> str:
    conteudo = ConteudoCursor(
        versao=1,
        rota=rota,
        filtros=filtros,
        geracao=geracao,
        chaves=chaves,
        emitido_em=int(time.time()) if agora is None else agora,
        teto=teto,
    )
    dados = base64.urlsafe_b64encode(conteudo.model_dump_json().encode()).rstrip(b"=")
    assinatura = hmac.digest(segredo, dados, "sha256").hex()
    return dados.decode() + "." + assinatura


def ler_cursor(
    token: str, segredo: bytes, rota: str, filtros: str, geracao: str, *, agora: int | None = None
) -> ConteudoCursor:
    try:
        if not 1 <= len(token) <= 2048:
            raise ValueError()
        dados, assinatura = token.split(".")
        if not re.fullmatch(r"[a-f0-9]{64}", assinatura) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", dados
        ):
            raise ValueError()
        if not hmac.compare_digest(
            hmac.digest(segredo, dados.encode(), "sha256").hex(), assinatura
        ):
            raise ValueError()
        bruto = base64.b64decode(dados + "=" * (-len(dados) % 4), altchars=b"-_", validate=True)
        conteudo = ConteudoCursor.model_validate(interpretar_json(bruto))
        if (
            conteudo.versao != 1
            or conteudo.rota != rota
            or conteudo.filtros != filtros
            or any(len(chave) > 100 for chave in conteudo.chaves)
        ):
            raise ValueError()
        instante = int(time.time()) if agora is None else agora
        if conteudo.emitido_em > instante + 60:
            raise ValueError()
    except (ValueError, ValidationError, UnicodeError, RecursionError):
        raise ErroAPI(
            422, "CURSOR_INVALIDO", "Cursor inválido para os filtros informados."
        ) from None
    if conteudo.geracao != geracao or instante - conteudo.emitido_em >= 86400:
        raise ErroAPI(409, "CURSOR_EXPIRADO", "Cursor expirado; reinicie a navegação.")
    return conteudo
