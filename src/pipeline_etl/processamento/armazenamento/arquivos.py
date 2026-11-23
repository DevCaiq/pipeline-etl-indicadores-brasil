"""Bronze imutável: publicação atômica e exclusiva no mesmo filesystem."""

import json
import os
from collections.abc import Sequence
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pipeline_etl.processamento.tipos import ArtefatoBronze, RespostaBCB


class ArmazenamentoBronze:
    """Guarda bytes sem normalização e rejeita referências fora da raiz."""

    def __init__(self, raiz: Path) -> None:
        self._raiz = raiz.resolve()

    @property
    def raiz(self) -> Path:
        """Raiz canônica usada para resolver referências portáveis."""
        return self._raiz

    def _localizar(self, caminho: Path) -> Path:
        resultado = caminho.resolve()
        if not resultado.is_relative_to(self._raiz):
            raise ValueError("O caminho deve permanecer dentro da raiz bronze.")
        return resultado

    def _diretorio(self, codigo: int, execucao_id: UUID, instante: datetime) -> Path:
        if codigo not in {432, 433, 1} or not isinstance(execucao_id, UUID):
            raise ValueError("Identificadores de origem inválidos.")
        if instante.tzinfo is None:
            raise ValueError("O instante deve incluir fuso horário.")
        return self._localizar(
            self._raiz
            / "bcb"
            / str(codigo)
            / instante.astimezone(UTC).date().isoformat()
            / str(execucao_id)
        )

    @staticmethod
    def _gravar_atomico(destino: Path, conteudo: bytes) -> None:
        """Publica por hard link para nunca substituir um arquivo existente."""
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(f".{uuid4()}.tmp")
        try:
            with temporario.open("xb") as arquivo:
                arquivo.write(conteudo)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            os.link(temporario, destino)
        finally:
            temporario.unlink(missing_ok=True)

    def salvar(
        self, resposta: RespostaBCB, execucao_id: UUID, instante: datetime
    ) -> ArtefatoBronze:
        """Grava o corpo antes de construir metadados, sem tentar interpretar JSON."""
        diretorio = self._diretorio(resposta.codigo_serie, execucao_id, instante)
        artefato_id = uuid4()
        corpo = diretorio / f"{artefato_id}.body"
        caminho_metadados = diretorio / f"{artefato_id}.meta.json"
        checksum = sha256(resposta.corpo).hexdigest()
        self._gravar_atomico(corpo, resposta.corpo)
        metadados = {
            "versao_formato": 1,
            "execucao_id": str(execucao_id),
            "artefato_id": str(artefato_id),
            "fonte": "bcb",
            "codigo_serie": resposta.codigo_serie,
            "url": resposta.url,
            "parametros": resposta.parametros,
            "status_http": resposta.status_http,
            "coletado_em": resposta.coletado_em.isoformat(),
            "sha256": checksum,
            "tamanho_bytes": len(resposta.corpo),
            "tipo_conteudo": resposta.tipo_conteudo,
            "codificacao_conteudo": resposta.codificacao_conteudo,
            "descompressao_automatica": False,
            "caminho_corpo": corpo.relative_to(self._raiz).as_posix(),
        }
        self._gravar_atomico(
            caminho_metadados,
            (json.dumps(metadados, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        return ArtefatoBronze(corpo, caminho_metadados, checksum, len(resposta.corpo))

    def _verificar_artefato(self, caminho_metadados: Path) -> tuple[ArtefatoBronze, bytes]:
        caminho_metadados = self._localizar(caminho_metadados)
        metadados = json.loads(caminho_metadados.read_text(encoding="utf-8"))
        if not isinstance(metadados, dict):
            raise ValueError("Metadados bronze devem ser um objeto.")
        nome = metadados.get("caminho_corpo")
        if not isinstance(nome, str) or not nome:
            raise ValueError("Metadados sem caminho de corpo válido.")
        relativo = Path(nome)
        if relativo.is_absolute() or ".." in relativo.parts:
            raise ValueError("A referência deve ser relativa à raiz bronze.")
        caminho_corpo = self._localizar(self._raiz / relativo)
        checksum = metadados.get("sha256")
        tamanho = metadados.get("tamanho_bytes")
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(caractere not in "0123456789abcdef" for caractere in checksum)
        ):
            raise ValueError("Metadados sem checksum SHA-256 válido.")
        if not isinstance(tamanho, int) or isinstance(tamanho, bool) or tamanho < 0:
            raise ValueError("Metadados sem tamanho válido.")
        if caminho_corpo.stat().st_size != tamanho:
            raise ValueError("Tamanho ou checksum do corpo bronze divergente.")
        corpo = caminho_corpo.read_bytes()
        if sha256(corpo).hexdigest() != checksum or len(corpo) != tamanho:
            raise ValueError("Tamanho ou checksum do corpo bronze divergente.")
        return ArtefatoBronze(caminho_corpo, caminho_metadados, checksum, tamanho), corpo

    def ler_corpo(self, caminho_metadados: Path) -> bytes:
        """Verifica tamanho e SHA-256 antes de devolver conteúdo para reprocessamento."""
        return self._verificar_artefato(caminho_metadados)[1]

    def salvar_manifesto(
        self,
        codigo: int,
        execucao_id: UUID,
        instante: datetime,
        inicio: date,
        fim: date,
        artefatos: Sequence[ArtefatoBronze],
        *,
        situacao: Literal["COLETADA", "INCOMPLETA"] = "COLETADA",
        motivo: str | None = None,
        inicio_coleta: date | None = None,
    ) -> Path:
        """Publica o índice por último, somente com artefatos verificados."""
        diretorio = self._diretorio(codigo, execucao_id, instante)
        if situacao == "COLETADA" and not artefatos:
            raise ValueError("Não publicar coleta concluída sem artefatos.")
        referencias = []
        for artefato in artefatos:
            if artefato.caminho_metadados.parent != diretorio:
                raise ValueError("Artefato pertence a outra execução.")
            referencia, _ = self._verificar_artefato(artefato.caminho_metadados)
            if referencia != artefato or referencia.caminho_corpo.parent != diretorio:
                raise ValueError("Referência do artefato diverge dos metadados verificados.")
            referencias.append(
                {
                    "corpo": artefato.caminho_corpo.relative_to(self._raiz).as_posix(),
                    "metadados": artefato.caminho_metadados.relative_to(self._raiz).as_posix(),
                    "sha256": artefato.checksum,
                    "tamanho_bytes": artefato.tamanho_bytes,
                }
            )
        manifesto = {
            "versao_formato": 1,
            "execucao_id": str(execucao_id),
            "fonte": "bcb",
            "codigo_serie": codigo,
            "inicio": inicio.isoformat(),
            "fim": fim.isoformat(),
            "situacao": situacao,
            "motivo": motivo,
            "artefatos": referencias,
            "inicio_coleta": (inicio_coleta or inicio).isoformat(),
        }
        destino = diretorio / "manifest.json"
        self._gravar_atomico(destino, (json.dumps(manifesto, indent=2) + "\n").encode("utf-8"))
        return destino
