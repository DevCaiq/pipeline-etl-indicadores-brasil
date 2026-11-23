"""Prepara credenciais privadas e provisiona MinIO local de forma repetível."""

import argparse
import json
import secrets
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr

from pipeline_etl.processamento.armazenamento.s3 import (
    criar_cliente_s3,
    garantir_bucket,
    ler_configuracao_s3,
    politica_bronze,
    validar_usuario_dedicado,
)

RAIZ = Path(__file__).resolve().parents[1]


def comando_compose() -> list[str]:
    docker = shutil.which("docker") or "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
    return [
        docker,
        "compose",
        "--env-file",
        ".env.banco",
        "--env-file",
        ".env.armazenamento",
        "-f",
        "compose.yaml",
        "-f",
        "compose.armazenamento.yaml",
        "--profile",
        "armazenamento",
    ]


def executar() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--iniciar", action="store_true", help="Construir e iniciar o MinIO.")
    argumentos.add_argument("--provisionar", action="store_true", help="Preparar bucket e usuário.")
    opcoes = argumentos.parse_args()
    destino = RAIZ / ".env.armazenamento"
    if not destino.exists():
        with destino.open("x", encoding="utf-8") as arquivo:
            arquivo.write(
                "ENDERECO_S3=http://127.0.0.1:9000\nBUCKET_S3=bronze-etl\nPREFIXO_S3=bronze\n"
            )
            arquivo.write(
                "USUARIO_MINIO_ADMIN=administrador_minio\nSENHA_MINIO_ADMIN="
                + secrets.token_hex(32)
                + "\n"
            )
            arquivo.write(
                "CHAVE_ACESSO_S3=bronze_processamento\nCHAVE_SECRETA_S3="
                + secrets.token_hex(32)
                + "\n"
            )
        print("Configuração privada criada; credenciais não exibidas.")
    configuracao = ler_configuracao_s3(destino)
    valores = dotenv_values(destino, interpolate=False)
    if configuracao.endereco.rstrip("/") not in {"http://127.0.0.1:9000", "http://localhost:9000"}:
        raise ValueError("O provisionamento é restrito ao MinIO local na porta 9000.")
    if (
        len(valores.get("SENHA_MINIO_ADMIN") or "") < 32
        or len(configuracao.chave_secreta.get_secret_value()) < 32
    ):
        raise ValueError("Gere credenciais locais fortes; não use os placeholders do exemplo.")
    if configuracao.chave_acesso.get_secret_value() == valores.get("USUARIO_MINIO_ADMIN"):
        raise ValueError("A pipeline exige usuário separado do administrador MinIO.")
    if opcoes.iniciar:
        subprocess.run(comando_compose() + ["up", "-d", "--build", "objetos"], cwd=RAIZ, check=True)
    if not opcoes.provisionar:
        return 0
    with httpx.Client(trust_env=False, timeout=3) as cliente:
        limite = time.monotonic() + 60
        while True:
            try:
                if (
                    cliente.get(
                        configuracao.endereco.rstrip("/") + "/minio/health/ready"
                    ).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() >= limite:
                raise RuntimeError("MinIO local não ficou pronto.")
            time.sleep(0.5)
    administrador = criar_cliente_s3(
        replace(
            configuracao,
            chave_acesso=SecretStr(valores.get("USUARIO_MINIO_ADMIN") or ""),
            chave_secreta=SecretStr(valores.get("SENHA_MINIO_ADMIN") or ""),
        )
    )
    try:
        garantir_bucket(administrador, configuracao.bucket)
    finally:
        administrador.close()
    codigo = """
import json, os, subprocess, sys
entrada = json.load(sys.stdin)
ambiente = dict(os.environ)
ambiente['MC_HOST_local'] = ('http://' + os.environ['MINIO_ROOT_USER'] + ':'
    + os.environ['MINIO_ROOT_PASSWORD'] + '@127.0.0.1:9000')
base = ['mc', '--config-dir', '/tmp/mc-etl']
if entrada.get('consultar'):
    resultado = subprocess.run(base + ['--json','admin','user','info','local',entrada['usuario']],
        env=ambiente, text=True, capture_output=True)
    sys.stdout.write(resultado.stdout)
    sys.exit(0)
operacoes = [
    (base + ['admin','user','add','local'], entrada['usuario'] + '\\n' + entrada['senha'] + '\\n'),
    (base + ['admin','policy','create','local','bronze-pipeline','/dev/stdin'],
        json.dumps(entrada['politica'])),
    (base + ['admin','policy','attach','local','bronze-pipeline','--user',entrada['usuario']],
        None),
]
for comando, conteudo in operacoes:
    resultado = subprocess.run(comando, input=conteudo, env=ambiente,
        text=True, capture_output=True)
    if resultado.returncode:
        raise RuntimeError('Provisionamento IAM falhou; nenhuma credencial foi exibida.')
"""
    entrada = {
        "usuario": configuracao.chave_acesso.get_secret_value(),
        "senha": configuracao.chave_secreta.get_secret_value(),
        "politica": politica_bronze(configuracao.bucket, configuracao.prefixo),
    }
    consulta = subprocess.run(
        comando_compose() + ["exec", "-T", "objetos", "python", "-c", codigo],
        input=json.dumps({**entrada, "consultar": True}),
        cwd=RAIZ,
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    validar_usuario_dedicado(json.loads(consulta.stdout))
    resultado = subprocess.run(
        comando_compose() + ["exec", "-T", "objetos", "python", "-c", codigo],
        input=json.dumps(entrada),
        cwd=RAIZ,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if resultado.returncode:
        raise RuntimeError("Falha no provisionamento IAM local; saída sensível não exibida.")
    print("Bucket privado versionado e usuário restrito provisionados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
