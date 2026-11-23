"""Avaliação local de frescor; calendário versionado e fallback nunca fazem HTTP."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

VALIDADE_CALENDARIO_DIAS = 30
TOLERANCIA_REPLICACAO_DIAS = 1


class DivulgacaoIPCA(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    identificador_origem: StrictInt = Field(gt=0)
    referencia: date
    data_divulgacao: date


class CalendarioIPCA(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    versao: str
    produto_id: Literal[9256]
    fonte_url: Literal["https://servicodados.ibge.gov.br/api/v3/calendario/?produto=9256"]
    fonte_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consultado_em: datetime
    divulgacoes: tuple[DivulgacaoIPCA, ...]

    @property
    def vigente_desde(self) -> date:
        return self.consultado_em.astimezone(ZoneInfo("America/Sao_Paulo")).date()

    @model_validator(mode="after")
    def validar_calendario(self) -> Self:
        if self.consultado_em.tzinfo is None:
            raise ValueError("Consulta do calendário deve conter fuso horário.")
        versao = "ibge-ipca-" + self.vigente_desde.strftime("%Y%m%d") + "-" + self.fonte_sha256[:12]
        if self.versao != versao:
            raise ValueError("Versão incompatível com origem e consulta.")
        if len(self.divulgacoes) != 12:
            raise ValueError("Snapshot exige doze referências oficiais de um ano.")
        ano = self.divulgacoes[0].referencia.year
        for mes, divulgacao in enumerate(self.divulgacoes, start=1):
            if divulgacao.referencia != date(ano, mes, 1):
                raise ValueError("Referências mensais incompletas ou fora de ordem.")
            proximo_mes = date(ano + mes // 12, mes % 12 + 1, 1)
            if divulgacao.data_divulgacao < proximo_mes:
                raise ValueError("Divulgação anterior ao término da referência.")
        if len({item.identificador_origem for item in self.divulgacoes}) != 12:
            raise ValueError("Identificadores oficiais repetidos.")
        datas = [item.data_divulgacao for item in self.divulgacoes]
        if any(
            anterior >= posterior for anterior, posterior in zip(datas, datas[1:], strict=False)
        ):
            raise ValueError("Datas de divulgação devem ser crescentes.")
        return self


def carregar_calendario(caminho: Path | None = None) -> tuple[CalendarioIPCA | None, str | None]:
    """Lê snapshot do pacote; falhas controladas degradam sem interromper a API."""
    try:
        conteudo = (
            caminho.read_bytes()
            if caminho is not None
            else files("pipeline_etl").joinpath("calendarios/ipca_2026.json").read_bytes()
        )
    except OSError:
        return None, "CALENDARIO_AUSENTE"
    try:
        return CalendarioIPCA.model_validate_json(conteudo), None
    except ValueError:
        return None, "CALENDARIO_INVALIDO"


@dataclass(frozen=True)
class AvaliacaoFrescor:
    defasado: bool | None
    politica: str
    motivo: str
    referencia_esperada: date | None = None
    data_limite: date | None = None
    versao_calendario: str | None = None


def avaliar_frescor(
    codigo_serie: int,
    ultima_referencia: date | None,
    hoje: date,
    calendario: CalendarioIPCA | None = None,
    motivo_indisponibilidade: str = "CALENDARIO_AUSENTE",
) -> AvaliacaoFrescor:
    """Compara apenas referências vencidas após um dia completo de tolerância local."""
    politica = "HEURISTICA_45_DIAS" if codigo_serie == 433 else "HEURISTICA_4_DIAS"
    if ultima_referencia is None:
        return AvaliacaoFrescor(None, politica, "SEM_REFERENCIA")
    if ultima_referencia > hoje or (codigo_serie == 433 and ultima_referencia.day != 1):
        return AvaliacaoFrescor(None, politica, "REFERENCIA_INVALIDA")
    motivo = motivo_indisponibilidade if codigo_serie == 433 else "CALENDARIO_NAO_HOMOLOGADO"
    if codigo_serie == 433 and calendario is not None:
        if hoje < calendario.vigente_desde:
            motivo = "CALENDARIO_AINDA_NAO_VIGENTE"
        elif hoje > calendario.vigente_desde + timedelta(days=VALIDADE_CALENDARIO_DIAS):
            motivo = "CALENDARIO_EXPIRADO"
        elif hoje > calendario.divulgacoes[-1].data_divulgacao + timedelta(
            days=TOLERANCIA_REPLICACAO_DIAS
        ):
            motivo = "CALENDARIO_FORA_COBERTURA"
        else:
            vencidas = [
                item
                for item in calendario.divulgacoes
                if hoje > item.data_divulgacao + timedelta(days=TOLERANCIA_REPLICACAO_DIAS)
            ]
            if vencidas:
                esperada = vencidas[-1]
                defasado = ultima_referencia < esperada.referencia
                return AvaliacaoFrescor(
                    defasado,
                    "CALENDARIO_IBGE",
                    "REFERENCIA_ATRASADA" if defasado else "REFERENCIA_EM_DIA",
                    esperada.referencia,
                    esperada.data_divulgacao + timedelta(days=TOLERANCIA_REPLICACAO_DIAS),
                    calendario.versao,
                )
            motivo = "CALENDARIO_SEM_REFERENCIA_VENCIDA"
    limite = 45 if codigo_serie == 433 else 4
    return AvaliacaoFrescor((hoje - ultima_referencia).days > limite, politica, motivo)


def avaliar_frescor_local(
    codigo_serie: int, ultima_referencia: date | None, hoje: date
) -> AvaliacaoFrescor:
    """Fronteira de I/O local para compartilhar a regra na API e na auditoria."""
    calendario, motivo = carregar_calendario() if codigo_serie == 433 else (None, None)
    return avaliar_frescor(
        codigo_serie, ultima_referencia, hoje, calendario, motivo or "CALENDARIO_AUSENTE"
    )
