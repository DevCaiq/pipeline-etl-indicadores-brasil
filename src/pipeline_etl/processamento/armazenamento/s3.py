"""Cliente S3 explícito e provisionamento de bucket privado versionado."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from dotenv import dotenv_values
from pydantic import SecretStr

from pipeline_etl.processamento.armazenamento.objetos import (
    ArmazenamentoObjetos,
    S3Objetos,
    SistemaArquivosObjetos,
    _validar_chave,
)


def validar_bucket(bucket: str) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket) or ".." in bucket:
        raise ValueError("Nome de bucket inválido.")


@dataclass(frozen=True)
class ConfiguracaoS3:
    endereco: str
    bucket: str
    chave_acesso: SecretStr
    chave_secreta: SecretStr
    prefixo: str = "bronze"

    def __post_init__(self) -> None:
        endereco = urlsplit(self.endereco)
        if (
            endereco.scheme not in {"http", "https"}
            or not endereco.hostname
            or endereco.username
            or endereco.password
            or endereco.query
            or endereco.fragment
            or endereco.path not in {"", "/"}
        ):
            raise ValueError("Endpoint S3 inválido.")
        if endereco.scheme == "http" and endereco.hostname not in {
            "127.0.0.1",
            "localhost",
            "objetos",
        }:
            raise ValueError("HTTP S3 é permitido somente no ambiente local.")
        validar_bucket(self.bucket)
        _validar_chave(self.prefixo)
        if any(simbolo in self.prefixo for simbolo in "*?$"):
            raise ValueError("Prefixo S3 não pode conter curingas.")
        if not self.chave_acesso.get_secret_value() or not self.chave_secreta.get_secret_value():
            raise ValueError("Credenciais S3 explícitas são obrigatórias.")


def ler_configuracao_s3(arquivo: Path) -> ConfiguracaoS3:
    valores = dotenv_values(arquivo, interpolate=False)
    return ConfiguracaoS3(
        endereco=valores.get("ENDERECO_S3") or "",
        bucket=valores.get("BUCKET_S3") or "",
        chave_acesso=SecretStr(valores.get("CHAVE_ACESSO_S3") or ""),
        chave_secreta=SecretStr(valores.get("CHAVE_SECRETA_S3") or ""),
        prefixo=valores.get("PREFIXO_S3") or "bronze",
    )


def criar_cliente_s3(configuracao: ConfiguracaoS3) -> Any:
    """Usa credenciais explícitas; mantém TLS e não faz retries silenciosos."""
    return boto3.client(
        "s3",
        endpoint_url=configuracao.endereco,
        region_name="us-east-1",
        aws_access_key_id=configuracao.chave_acesso.get_secret_value(),
        aws_secret_access_key=configuracao.chave_secreta.get_secret_value(),
        config=Config(
            signature_version="s3v4",
            connect_timeout=3,
            read_timeout=30,
            retries={"total_max_attempts": 1},
            s3={"addressing_style": "path"},
        ),
    )


@contextmanager
def abrir_armazenamento(
    raiz: Path, arquivo_s3: Path | None = None
) -> Iterator[ArmazenamentoObjetos]:
    """Mantém arquivos como padrão e fecha o cliente S3 mesmo quando a operação falha."""
    if arquivo_s3 is None:
        yield SistemaArquivosObjetos(raiz)
        return
    configuracao = ler_configuracao_s3(arquivo_s3)
    cliente = criar_cliente_s3(configuracao)
    try:
        yield S3Objetos(cliente, configuracao.bucket, configuracao.prefixo)
    finally:
        cliente.close()


def garantir_bucket(cliente: Any, bucket: str) -> None:
    """Cria somente quando inexistente e habilita versionamento sem remover dados."""
    validar_bucket(bucket)
    try:
        cliente.head_bucket(Bucket=bucket)
    except ClientError as erro:
        if erro.response.get("Error", {}).get("Code") not in {"404", "NoSuchBucket", "NotFound"}:
            raise
        try:
            cliente.create_bucket(Bucket=bucket)
        except ClientError as concorrencia:
            if concorrencia.response.get("Error", {}).get("Code") != "BucketAlreadyOwnedByYou":
                raise
    try:
        cliente.get_bucket_policy(Bucket=bucket)
    except ClientError as erro:
        if erro.response.get("Error", {}).get("Code") != "NoSuchBucketPolicy":
            raise
    else:
        raise ValueError("Bucket possui política própria; configuração preservada para revisão.")
    if cliente.get_bucket_versioning(Bucket=bucket).get("Status") != "Enabled":
        cliente.put_bucket_versioning(Bucket=bucket, VersioningConfiguration={"Status": "Enabled"})


def validar_usuario_dedicado(informacoes: dict[str, Any]) -> bool:
    """Recusa permissões anteriores diretas/herdadas e erros de consulta ambíguos."""
    if informacoes.get("status") == "success":
        politicas = informacoes.get("policyName") or ""
        if not isinstance(politicas, str) or informacoes.get("memberOf"):
            raise ValueError("Conta dedicada possui grupos ou políticas inesperadas.")
        if any(nome.strip() not in {"", "bronze-pipeline"} for nome in politicas.split(",")):
            raise ValueError(
                "Conta dedicada possui permissões adicionais; configuração preservada."
            )
        return True

    def usuario_ausente(valor: Any) -> bool:
        if isinstance(valor, dict):
            return valor.get("Code") == "XMinioAdminNoSuchUser" or any(
                usuario_ausente(item) for item in valor.values()
            )
        if isinstance(valor, list):
            return any(usuario_ausente(item) for item in valor)
        return False

    if informacoes.get("status") == "error" and usuario_ausente(informacoes.get("error")):
        return False
    raise ValueError("Não foi possível verificar as permissões da conta dedicada.")


def politica_bronze(bucket: str, prefixo: str) -> dict[str, Any]:
    validar_bucket(bucket)
    _validar_chave(prefixo)
    if any(simbolo in prefixo for simbolo in "*?$"):
        raise ValueError("Prefixo da política não pode conter curingas.")
    recurso = f"arn:aws:s3:::{bucket}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetBucketLocation"], "Resource": [recurso]},
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": [recurso],
                "Condition": {"StringLike": {"s3:prefix": [prefixo + "/", prefixo + "/*"]}},
            },
            {
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:PutObject"],
                "Resource": [recurso + "/" + prefixo + "/*"],
            },
            {
                "Effect": "Deny",
                "Action": ["s3:DeleteObject", "s3:DeleteObjectVersion"],
                "Resource": [recurso + "/*"],
            },
        ],
    }
