from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest

from pipeline_etl.processamento.armazenamento.objetos import (
    ObjetoBronze,
    ObjetoCorrompido,
    ObjetoJaExiste,
    S3Objetos,
    SistemaArquivosObjetos,
)


class ErroS3(Exception):
    def __init__(self, codigo: str) -> None:
        self.response = {"Error": {"Code": codigo}}


class ClienteS3Simulado:
    def __init__(self) -> None:
        self.objetos: dict[str, bytes] = {}
        self.argumentos: dict[str, object] = {}
        self.corpo = BytesIO()
        self.erro: Exception | None = None

    def put_object(self, **argumentos: object) -> object:
        self.argumentos = argumentos
        if self.erro:
            raise self.erro
        chave = str(argumentos["Key"])
        if chave in self.objetos:
            raise ErroS3("PreconditionFailed")
        corpo = argumentos["Body"]
        assert isinstance(corpo, bytes)
        self.objetos[chave] = corpo
        return {}

    def get_object(self, **argumentos: object) -> dict[str, object]:
        self.corpo = BytesIO(self.objetos[str(argumentos["Key"])])
        return {"Body": self.corpo}


@pytest.fixture(params=["arquivos", "s3"])
def armazenamento(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "arquivos":
        return SistemaArquivosObjetos(tmp_path)
    return S3Objetos(ClienteS3Simulado(), "bronze", "coletas")


def test_preservar_bytes_e_descritor_imutavel(armazenamento):
    corpo = b"corpo bruto\x00"
    objeto = armazenamento.gravar_imutavel("ibge/objeto.bin", corpo)
    assert objeto == ObjetoBronze("ibge/objeto.bin", sha256(corpo).hexdigest(), len(corpo))
    assert armazenamento.ler(objeto) == corpo
    with pytest.raises(FrozenInstanceError):
        objeto.chave = "outra"


@pytest.mark.parametrize("novo_corpo", [b"original", b"alterado"])
def test_recusar_colisao_sem_alterar_objeto(armazenamento, novo_corpo):
    objeto = armazenamento.gravar_imutavel("objeto", b"original")
    with pytest.raises(ObjetoJaExiste):
        armazenamento.gravar_imutavel("objeto", novo_corpo)
    assert armazenamento.ler(objeto) == b"original"


@pytest.mark.parametrize(
    "chave", ["", "/", "../fora", "a/../b", "./a", "a//b", "a/", "C:/a", "a\\b"]
)
def test_recusar_chaves_nao_canonicas(armazenamento, chave):
    with pytest.raises(ValueError):
        armazenamento.gravar_imutavel(chave, b"corpo")


def test_detectar_corrupcao_filesystem(tmp_path):
    armazenamento = SistemaArquivosObjetos(tmp_path)
    objeto = armazenamento.gravar_imutavel("objeto", b"original")
    (tmp_path / "objeto").write_bytes(b"alterado")
    with pytest.raises(ObjetoCorrompido):
        armazenamento.ler(objeto)


def test_s3_exigir_escrita_condicional_e_checksum():
    cliente = ClienteS3Simulado()
    armazenamento = S3Objetos(cliente, "bronze", "coletas")
    armazenamento.gravar_imutavel("objeto", b"original")
    assert cliente.argumentos["IfNoneMatch"] == "*"
    assert cliente.argumentos["Key"] == "coletas/objeto"
    assert cliente.argumentos["Metadata"] == {"sha256": sha256(b"original").hexdigest()}
    assert cliente.argumentos["ChecksumSHA256"] == "BoLF8gdvCZw0z90VqeBjhJ7UN6SWd+b8xbQZjHZXW+U="


@pytest.mark.parametrize("corpo", [b"curto", b"original excedente", b"alterado"])
def test_s3_validar_corpo_e_fechar(corpo):
    cliente = ClienteS3Simulado()
    armazenamento = S3Objetos(cliente, "bronze")
    objeto = armazenamento.gravar_imutavel("objeto", b"original")
    cliente.objetos["objeto"] = corpo
    with pytest.raises(ObjetoCorrompido):
        armazenamento.ler(objeto)
    assert cliente.corpo.closed


def test_s3_propagar_erro_de_rede():
    cliente = ClienteS3Simulado()
    cliente.erro = OSError("rede indisponível")
    with pytest.raises(OSError, match="rede indisponível"):
        S3Objetos(cliente, "bronze").gravar_imutavel("objeto", b"corpo")
