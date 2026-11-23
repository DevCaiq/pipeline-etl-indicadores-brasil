"""Configuração explícita e preparação idempotente do armazenamento local."""

from unittest.mock import Mock

import pytest

from pipeline_etl.processamento.armazenamento.s3 import garantir_bucket, politica_bronze


def test_bucket_existente_preserva_configuracao():
    from botocore.exceptions import ClientError

    cliente = Mock()
    cliente.get_bucket_policy.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucketPolicy"}}, "GetBucketPolicy"
    )
    cliente.get_bucket_versioning.return_value = {"Status": "Enabled"}
    garantir_bucket(cliente, "bronze-etl")
    cliente.create_bucket.assert_not_called()
    cliente.put_bucket_versioning.assert_not_called()


def test_bucket_com_politica_preexistente_nao_e_anunciado_privado():
    cliente = Mock()
    cliente.get_bucket_policy.return_value = {"Policy": '{"Statement":[{"Principal":"*"}]}'}
    with pytest.raises(ValueError, match="política"):
        garantir_bucket(cliente, "bronze-etl")
    cliente.put_bucket_versioning.assert_not_called()


@pytest.mark.parametrize(
    "informacoes",
    [
        {"status": "success", "policyName": "bronze-pipeline,readwrite"},
        {"status": "success", "policyName": "bronze-pipeline", "memberOf": ["administradores"]},
        {"status": "error", "error": {"Code": "AccessDenied"}},
    ],
)
def test_usuario_existente_com_permissoes_extras_e_recusado(informacoes):
    from pipeline_etl.processamento.armazenamento.s3 import validar_usuario_dedicado

    with pytest.raises(ValueError):
        validar_usuario_dedicado(informacoes)


@pytest.mark.parametrize(
    "informacoes,existe",
    [
        ({"status": "success", "policyName": "bronze-pipeline", "memberOf": None}, True),
        ({"status": "success", "policyName": "", "memberOf": []}, True),
        ({"status": "error", "error": {"cause": {"Code": "XMinioAdminNoSuchUser"}}}, False),
    ],
)
def test_usuario_novo_ou_exclusivamente_dedicado_e_aceito(informacoes, existe):
    from pipeline_etl.processamento.armazenamento.s3 import validar_usuario_dedicado

    assert validar_usuario_dedicado(informacoes) is existe


def test_bucket_novo_e_criado_e_versionado_sem_politica_publica():
    from botocore.exceptions import ClientError

    cliente = Mock()
    cliente.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")
    cliente.get_bucket_policy.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucketPolicy"}}, "GetBucketPolicy"
    )
    cliente.get_bucket_versioning.return_value = {}
    garantir_bucket(cliente, "bronze-etl")
    cliente.create_bucket.assert_called_once_with(Bucket="bronze-etl")
    cliente.put_bucket_versioning.assert_called_once_with(
        Bucket="bronze-etl", VersioningConfiguration={"Status": "Enabled"}
    )


def test_erro_de_permissao_nao_e_tratado_como_bucket_inexistente():
    from botocore.exceptions import ClientError

    cliente = Mock()
    cliente.head_bucket.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadBucket")
    with pytest.raises(ClientError):
        garantir_bucket(cliente, "bronze-etl")
    cliente.create_bucket.assert_not_called()


def test_politica_limita_prefixo_e_nao_permite_excluir():
    politica = politica_bronze("bronze-etl", "bronze")
    permissoes = [item for item in politica["Statement"] if item["Effect"] == "Allow"]
    assert all("s3:*" not in item["Action"] for item in permissoes)
    objetos = next(item for item in permissoes if "s3:PutObject" in item["Action"])
    assert objetos["Resource"] == ["arn:aws:s3:::bronze-etl/bronze/*"]
    assert "s3:DeleteObject" not in objetos["Action"]


@pytest.mark.parametrize("prefixo", ["", "../fora", "bronze/*", "bronze/"])
def test_politica_recusa_prefixos_ambiguos(prefixo):
    with pytest.raises(ValueError):
        politica_bronze("bronze-etl", prefixo)


def test_cliente_s3_exige_credenciais_e_timeouts_explicitos():
    from pydantic import SecretStr

    from pipeline_etl.processamento.armazenamento.s3 import ConfiguracaoS3, criar_cliente_s3

    configuracao = ConfiguracaoS3(
        "http://127.0.0.1:9000", "bronze-etl", SecretStr("usuario"), SecretStr("segredo-teste")
    )
    cliente = criar_cliente_s3(configuracao)
    try:
        assert cliente.meta.config.connect_timeout == 3
        assert cliente.meta.config.read_timeout == 30
        assert cliente.meta.config.retries["total_max_attempts"] == 1
    finally:
        cliente.close()


@pytest.mark.parametrize(
    "endereco", ["http://externo.invalid", "https://u:p@localhost", "ftp://localhost"]
)
def test_configuracao_recusa_endereco_inseguro(endereco):
    from pydantic import SecretStr

    from pipeline_etl.processamento.armazenamento.s3 import ConfiguracaoS3

    with pytest.raises(ValueError):
        ConfiguracaoS3(endereco, "bronze-etl", SecretStr("usuario"), SecretStr("segredo"))


def test_contexto_s3_fecha_cliente_inclusive_em_falha(monkeypatch, tmp_path):
    from pydantic import SecretStr

    from pipeline_etl.processamento.armazenamento import s3
    from pipeline_etl.processamento.armazenamento.objetos import S3Objetos

    configuracao = s3.ConfiguracaoS3(
        "http://127.0.0.1:9000", "bronze-etl", SecretStr("usuario"), SecretStr("segredo-teste")
    )
    cliente = Mock()
    monkeypatch.setattr(s3, "ler_configuracao_s3", lambda _: configuracao)
    monkeypatch.setattr(s3, "criar_cliente_s3", lambda _: cliente)
    with (
        pytest.raises(RuntimeError, match="simulada"),
        s3.abrir_armazenamento(tmp_path, tmp_path / "configuracao") as armazenamento,
    ):
        assert isinstance(armazenamento, S3Objetos)
        raise RuntimeError("Falha simulada")
    cliente.close.assert_called_once()
