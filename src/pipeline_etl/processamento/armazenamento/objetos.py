"""Contrato de objetos bronze imutáveis para disco e S3 compatível."""

import base64
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4


class ObjetoJaExiste(FileExistsError):
    """A chave já foi publicada e não pode ser substituída."""


class ObjetoCorrompido(ValueError):
    """O corpo diverge do descritor bronze."""


def _validar_chave(chave: str) -> None:
    if (
        not chave
        or "\\" in chave
        or ":" in chave
        or "\x00" in chave
        or PurePosixPath(chave).is_absolute()
        or any(parte in {"", ".", ".."} for parte in chave.split("/"))
    ):
        raise ValueError("A chave deve ser relativa, canônica e usar separadores POSIX.")


@dataclass(frozen=True)
class ObjetoBronze:
    """Referência portável cujo checksum se aplica aos bytes originais."""

    chave: str
    sha256: str
    tamanho_bytes: int

    def __post_init__(self) -> None:
        _validar_chave(self.chave)
        if (
            len(self.sha256) != 64
            or any(caractere not in "0123456789abcdef" for caractere in self.sha256)
            or isinstance(self.tamanho_bytes, bool)
            or self.tamanho_bytes < 0
        ):
            raise ValueError("Descritor bronze inválido.")


class ArmazenamentoObjetos(Protocol):
    """Publica exclusivamente e verifica integridade durante leitura."""

    def gravar_imutavel(self, chave: str, corpo: bytes) -> ObjetoBronze: ...

    def ler(self, objeto: ObjetoBronze) -> bytes: ...


def _verificar(objeto: ObjetoBronze, corpo: bytes) -> bytes:
    if len(corpo) != objeto.tamanho_bytes or sha256(corpo).hexdigest() != objeto.sha256:
        raise ObjetoCorrompido("Tamanho ou SHA-256 divergente do objeto bronze.")
    return corpo


class SistemaArquivosObjetos:
    """Publica por hard link no mesmo volume, sem sobrescrita."""

    def __init__(self, raiz: Path) -> None:
        self._raiz = raiz.resolve()

    def _localizar(self, chave: str) -> Path:
        _validar_chave(chave)
        destino = (self._raiz / chave).resolve()
        if not destino.is_relative_to(self._raiz):
            raise ValueError("A chave deve permanecer dentro da raiz bronze.")
        return destino

    def gravar_imutavel(self, chave: str, corpo: bytes) -> ObjetoBronze:
        destino = self._localizar(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(f".{uuid4()}.tmp")
        try:
            with temporario.open("xb") as arquivo:
                arquivo.write(corpo)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            try:
                os.link(temporario, destino)
            except FileExistsError as erro:
                raise ObjetoJaExiste(f"Objeto já existe: {chave}") from erro
        finally:
            temporario.unlink(missing_ok=True)
        return ObjetoBronze(chave, sha256(corpo).hexdigest(), len(corpo))

    def ler(self, objeto: ObjetoBronze) -> bytes:
        with self._localizar(objeto.chave).open("rb") as arquivo:
            corpo = arquivo.read(objeto.tamanho_bytes + 1)
        return _verificar(objeto, corpo)


class CorpoS3(Protocol):
    """Interface de streaming preservada do SDK."""

    def read(self, amt: int = ...) -> bytes: ...

    def close(self) -> None: ...


class ClienteS3(Protocol):
    """Operações do SDK necessárias ao adaptador; sem criação de buckets."""

    def put_object(self, **argumentos: object) -> object: ...

    def get_object(self, **argumentos: object) -> dict[str, object]: ...


class S3Objetos:
    """Adaptador com cliente injetado e escrita condicional obrigatória."""

    def __init__(self, cliente: ClienteS3, bucket: str, prefixo: str = "") -> None:
        if not bucket:
            raise ValueError("O bucket deve ser informado.")
        if prefixo:
            _validar_chave(prefixo)
        self._cliente = cliente
        self._bucket = bucket
        self._prefixo = prefixo

    def _chave_completa(self, chave: str) -> str:
        _validar_chave(chave)
        return f"{self._prefixo}/{chave}" if self._prefixo else chave

    def gravar_imutavel(self, chave: str, corpo: bytes) -> ObjetoBronze:
        resumo = sha256(corpo)
        try:
            self._cliente.put_object(
                Bucket=self._bucket,
                Key=self._chave_completa(chave),
                Body=corpo,
                IfNoneMatch="*",
                Metadata={"sha256": resumo.hexdigest()},
                ChecksumSHA256=base64.b64encode(resumo.digest()).decode("ascii"),
            )
        except Exception as erro:
            resposta = getattr(erro, "response", None)
            if isinstance(resposta, dict):
                detalhe = resposta.get("Error")
                if isinstance(detalhe, dict) and detalhe.get("Code") in {
                    "PreconditionFailed",
                    "412",
                }:
                    raise ObjetoJaExiste(f"Objeto já existe: {chave}") from erro
            raise
        return ObjetoBronze(chave, resumo.hexdigest(), len(corpo))

    def ler(self, objeto: ObjetoBronze) -> bytes:
        resposta = self._cliente.get_object(
            Bucket=self._bucket, Key=self._chave_completa(objeto.chave)
        )
        from typing import cast

        fluxo = cast(CorpoS3, resposta["Body"])
        try:
            partes: list[bytes] = []
            restante = objeto.tamanho_bytes + 1
            while restante:
                parte = fluxo.read(restante)
                if not parte:
                    break
                partes.append(parte)
                restante -= len(parte)
            return _verificar(objeto, b"".join(partes))
        finally:
            fluxo.close()
