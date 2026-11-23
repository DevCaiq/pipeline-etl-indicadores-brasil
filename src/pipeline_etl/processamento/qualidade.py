"""Validação pura de corpos SGS, sem banco, rede ou alteração do bronze."""

import json
import math
import zlib
from dataclasses import dataclass
from datetime import date
from typing import Literal

from pydantic import JsonValue, ValidationError

from pipeline_etl.processamento.contratos.bcb import ObservacaoSGS

VERSAO_CONTRATO = "sgs-v1"


@dataclass(frozen=True)
class ContagensValidacao:
    """Partição das linhas recebidas, incluindo as não processadas por drift."""

    lidas: int = 0
    validas: int = 0
    rejeitadas: int = 0
    duplicadas: int = 0
    nao_processadas: int = 0


@dataclass(frozen=True)
class RejeicaoRegistro:
    """Posição começa em1; zero representa problema do envelope inteiro."""

    posicao: int
    motivo: str
    original: JsonValue


@dataclass(frozen=True)
class ResultadoValidacao:
    """Resultado inspecionável sem autorizar carga de um lote incompleto."""

    contagens: ContagensValidacao
    observacoes: tuple[ObservacaoSGS, ...] = ()
    rejeicoes: tuple[RejeicaoRegistro, ...] = ()
    erro_estrutural: str | None = None

    @property
    def situacao(self) -> Literal["SUCESSO", "PARCIAL", "FALHA"]:
        if self.erro_estrutural or not self.contagens.lidas:
            return "FALHA"
        if self.contagens.rejeitadas * 100 > self.contagens.lidas * 5:
            return "FALHA"
        return "PARCIAL" if self.contagens.rejeitadas else "SUCESSO"


def descompactar(corpo: bytes, codificacao: str | None, limite: int) -> bytes:
    """Limita a saída antes de alocar todo um corpo comprimido."""
    if limite <= 0 or len(corpo) > limite:
        raise ValueError("Corpo excede limite.")
    codificacao = (codificacao or "identity").strip().lower()
    if codificacao == "identity":
        return corpo
    if codificacao not in {"gzip", "deflate"}:
        raise ValueError("Codificação não suportada.")
    descompactador = zlib.decompressobj(
        16 + zlib.MAX_WBITS if codificacao == "gzip" else zlib.MAX_WBITS
    )
    resultado = descompactador.decompress(corpo, limite + 1)
    if (
        len(resultado) > limite
        or descompactador.unconsumed_tail
        or not descompactador.eof
        or descompactador.unused_data
    ):
        raise ValueError("Conteúdo comprimido truncado, concatenado ou excessivo.")
    return resultado


def _objeto_unico(pares: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    resultado: dict[str, JsonValue] = {}
    for chave, valor in pares:
        if chave in resultado:
            raise ValueError("Chave JSON duplicada.")
        resultado[chave] = valor
    return resultado


def _numero_finito(valor: str) -> float:
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError("Número JSON não finito.")
    return numero


def _constante_invalida(valor: str) -> None:
    raise ValueError("Constante JSON não permitida.")


def interpretar_json(corpo: bytes) -> JsonValue:
    """Evita perder chaves duplicadas ou deixar NaN entrar na quarentena SQL."""
    resultado: JsonValue = json.loads(
        corpo.decode("utf-8-sig"),
        object_pairs_hook=_objeto_unico,
        parse_float=_numero_finito,
        parse_constant=_constante_invalida,
    )
    return resultado


def validar_corpo(
    corpo: bytes,
    codigo: int,
    inicio: date,
    fim: date,
    hoje: date,
    codificacao: str | None = None,
    *,
    limite_bytes: int = 10 * 1024 * 1024,
) -> ResultadoValidacao:
    """Classifica estrutura, linhas e duplicatas com contagens conservadas."""
    if codigo not in {1, 432, 433} or inicio > fim:
        raise ValueError("Contexto de validação inválido.")
    try:
        descompactado = descompactar(corpo, codificacao, limite_bytes)
    except (ValueError, zlib.error):
        return ResultadoValidacao(
            ContagensValidacao(),
            rejeicoes=(RejeicaoRegistro(0, "COMPRESSAO_INVALIDA", None),),
            erro_estrutural="COMPRESSAO_INVALIDA",
        )
    try:
        registros = interpretar_json(descompactado)
    except (ValueError, RecursionError):
        return ResultadoValidacao(
            ContagensValidacao(),
            rejeicoes=(RejeicaoRegistro(0, "JSON_INVALIDO", None),),
            erro_estrutural="JSON_INVALIDO",
        )
    if not isinstance(registros, list) or not registros:
        motivo = "RESPOSTA_VAZIA" if registros == [] else "ENVELOPE_INVALIDO"
        return ResultadoValidacao(
            ContagensValidacao(),
            rejeicoes=(RejeicaoRegistro(0, motivo, None),),
            erro_estrutural=motivo,
        )
    estrutura = [
        RejeicaoRegistro(pos, "ESQUEMA_ALTERADO", registro)
        for pos, registro in enumerate(registros, 1)
        if not isinstance(registro, dict) or set(registro) != {"data", "valor"}
    ]
    if estrutura:
        return ResultadoValidacao(
            ContagensValidacao(
                lidas=len(registros),
                rejeitadas=len(estrutura),
                nao_processadas=len(registros) - len(estrutura),
            ),
            rejeicoes=tuple(estrutura),
            erro_estrutural="ESQUEMA_ALTERADO",
        )
    rejeicoes: list[RejeicaoRegistro] = []
    grupos: dict[date, list[tuple[int, ObservacaoSGS, JsonValue]]] = {}
    for posicao, registro in enumerate(registros, 1):
        try:
            observacao = ObservacaoSGS.model_validate(registro)
            if observacao.data > hoje:
                raise ValueError("DATA_FUTURA")
            if not inicio <= observacao.data <= fim:
                raise ValueError("DATA_FORA_JANELA")
            if codigo == 1 and observacao.valor <= 0:
                raise ValueError("VALOR_NAO_POSITIVO")
            if codigo == 433:
                observacao = observacao.model_copy(update={"data": observacao.data.replace(day=1)})
                if not inicio <= observacao.data <= fim:
                    raise ValueError("DATA_NORMALIZADA_FORA_JANELA")
        except ValidationError as erro:
            campos = {
                item["loc"][0] for item in erro.errors(include_input=False, include_context=False)
            }
            motivo = (
                "DATA_E_VALOR_INVALIDOS"
                if len(campos) > 1
                else ("DATA_INVALIDA" if "data" in campos else "VALOR_INVALIDO")
            )
            rejeicoes.append(RejeicaoRegistro(posicao, motivo, registro))
            continue
        except ValueError as erro:
            rejeicoes.append(RejeicaoRegistro(posicao, str(erro), registro))
            continue
        grupos.setdefault(observacao.data, []).append((posicao, observacao, registro))
    observacoes = []
    duplicadas = 0
    conflito = False
    for grupo in grupos.values():
        if len({observacao.valor for _, observacao, _ in grupo}) > 1:
            conflito = True
            rejeicoes.extend(
                RejeicaoRegistro(pos, "DUPLICATA_CONFLITANTE", original)
                for pos, _, original in grupo
            )
        else:
            observacoes.append(grupo[0][1])
            duplicadas += len(grupo) - 1
    return ResultadoValidacao(
        ContagensValidacao(len(registros), len(observacoes), len(rejeicoes), duplicadas),
        tuple(sorted(observacoes, key=lambda observacao: observacao.data)),
        tuple(sorted(rejeicoes, key=lambda rejeicao: rejeicao.posicao)),
        "DUPLICATA_CONFLITANTE" if conflito else None,
    )
