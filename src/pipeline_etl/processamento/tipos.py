"""Valores de transporte: nenhuma medida econômica é interpretada nesta camada."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RespostaBCB:
    """Corpo HTTP original, com codificação preservada e origem explícita."""

    codigo_serie: int
    corpo: bytes
    url: str
    parametros: dict[str, str]
    status_http: int
    coletado_em: datetime
    tipo_conteudo: str | None
    codificacao_conteudo: str | None


@dataclass(frozen=True)
class ArtefatoBronze:
    """Referências publicadas para corpo e metadados de uma resposta."""

    caminho_corpo: Path
    caminho_metadados: Path
    checksum: str
    tamanho_bytes: int
