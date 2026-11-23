"""Leitura estrita de manifesto e identidade de artefatos bronze existentes."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, JsonValue, StrictBool, StrictInt

from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.coleta import dividir_janelas
from pipeline_etl.processamento.qualidade import interpretar_json


class ReferenciaBronze(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    corpo: str
    metadados: str
    sha256: str
    tamanho_bytes: StrictInt


class ManifestoBronze(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    versao_formato: StrictInt
    execucao_id: UUID
    fonte: str
    codigo_serie: StrictInt
    inicio: date
    fim: date
    situacao: str
    motivo: str | None
    artefatos: list[ReferenciaBronze]
    inicio_coleta: date


class MetadadosBronze(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    versao_formato: StrictInt
    execucao_id: UUID
    artefato_id: UUID
    fonte: str
    codigo_serie: StrictInt
    url: str
    parametros: dict[str, str]
    status_http: StrictInt
    coletado_em: datetime
    sha256: str
    tamanho_bytes: StrictInt
    tipo_conteudo: str | None
    codificacao_conteudo: str | None
    descompressao_automatica: StrictBool
    caminho_corpo: str


@dataclass(frozen=True)
class ArtefatoVerificado:
    metadados: MetadadosBronze
    caminho_metadados: Path
    inicio: date
    fim: date
    corpo: bytes


@dataclass(frozen=True)
class ManifestoVerificado:
    manifesto: ManifestoBronze
    caminho: Path
    artefatos: tuple[ArtefatoVerificado, ...]


def _resolver(raiz: Path, nome: str) -> Path:
    relativo = Path(nome)
    if relativo.is_absolute() or ".." in relativo.parts:
        raise ValueError("Referência deve ser relativa à raiz bronze.")
    caminho = (raiz / relativo).resolve()
    if not caminho.is_relative_to(raiz):
        raise ValueError("Referência fora da raiz bronze.")
    return caminho


def _ler_json(caminho: Path) -> JsonValue:
    if caminho.stat().st_size > 1024 * 1024:
        raise ValueError("Manifesto/metadados excedem limite.")
    return interpretar_json(caminho.read_bytes())


def ler_manifesto(armazenamento: ArmazenamentoBronze, caminho: Path) -> ManifestoVerificado:
    """Confere identidade, cobertura e bytes antes de confiar nas referências."""
    raiz = armazenamento.raiz
    caminho = caminho.resolve()
    if not caminho.is_relative_to(raiz) or caminho.name != "manifest.json":
        raise ValueError("Manifesto deve estar na raiz bronze e ter nome conhecido.")
    manifesto = ManifestoBronze.model_validate(_ler_json(caminho))
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    if (
        manifesto.versao_formato != 1
        or manifesto.fonte != "bcb"
        or manifesto.codigo_serie not in {1, 432, 433}
        or manifesto.situacao != "COLETADA"
    ):
        raise ValueError("Formato, fonte ou situação de manifesto incompatível.")
    if manifesto.inicio < date(2020, 1, 1) or not manifesto.inicio <= manifesto.fim <= hoje:
        raise ValueError("Período de manifesto inválido.")
    esperado = (
        date(2019, 2, 1)
        if manifesto.codigo_serie == 433 and manifesto.inicio == date(2020, 1, 1)
        else manifesto.inicio
    )
    if manifesto.inicio_coleta != esperado:
        raise ValueError("Início efetivo não corresponde à política da coleta.")
    partes = caminho.parent.relative_to(raiz).parts
    if (
        len(partes) != 4
        or partes[0] != "bcb"
        or partes[1] != str(manifesto.codigo_serie)
        or partes[3] != str(manifesto.execucao_id)
        or date.fromisoformat(partes[2]).isoformat() != partes[2]
    ):
        raise ValueError("Pasta e identidade do manifesto divergem.")
    janelas = list(dividir_janelas(manifesto.inicio_coleta, manifesto.fim))
    if len(janelas) != len(manifesto.artefatos):
        raise ValueError("Quantidade de artefatos não cobre as janelas solicitadas.")
    resultados = []
    identificadores = set()
    for referencia, (inicio, fim) in zip(manifesto.artefatos, janelas, strict=True):
        caminho_meta = _resolver(raiz, referencia.metadados)
        caminho_corpo = _resolver(raiz, referencia.corpo)
        if caminho_meta.parent != caminho.parent or caminho_corpo.parent != caminho.parent:
            raise ValueError("Artefato pertence a outra execução.")
        meta = MetadadosBronze.model_validate(_ler_json(caminho_meta))
        if (
            meta.versao_formato != 1
            or meta.fonte != "bcb"
            or meta.execucao_id != manifesto.execucao_id
            or meta.codigo_serie != manifesto.codigo_serie
            or meta.descompressao_automatica
            or meta.coletado_em.tzinfo is None
            or not 200 <= meta.status_http < 300
        ):
            raise ValueError("Identidade de metadados incompatível.")
        if (
            meta.artefato_id in identificadores
            or caminho_meta.name != f"{meta.artefato_id}.meta.json"
            or caminho_corpo.name != f"{meta.artefato_id}.body"
        ):
            raise ValueError("Artefato duplicado ou nome incompatível.")
        identificadores.add(meta.artefato_id)
        parametros = {
            "formato": "json",
            "dataInicial": inicio.strftime("%d/%m/%Y"),
            "dataFinal": fim.strftime("%d/%m/%Y"),
        }
        endereco = urlsplit(meta.url)
        if (
            meta.parametros != parametros
            or endereco.scheme != "https"
            or endereco.netloc != "api.bcb.gov.br"
            or endereco.path != f"/dados/serie/bcdata.sgs.{meta.codigo_serie}/dados"
            or endereco.fragment
            or parse_qs(endereco.query) != {chave: [valor] for chave, valor in parametros.items()}
        ):
            raise ValueError("Origem ou janela do artefato incompatível.")
        if (
            referencia.sha256 != meta.sha256
            or referencia.tamanho_bytes != meta.tamanho_bytes
            or not 0 <= meta.tamanho_bytes <= 10 * 1024 * 1024
            or _resolver(raiz, meta.caminho_corpo) != caminho_corpo
        ):
            raise ValueError("Referência e metadados divergem.")
        corpo = armazenamento.ler_corpo(caminho_meta)
        resultados.append(ArtefatoVerificado(meta, caminho_meta, inicio, fim, corpo))
    return ManifestoVerificado(manifesto, caminho, tuple(resultados))
