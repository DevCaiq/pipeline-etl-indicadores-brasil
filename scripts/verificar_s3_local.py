"""Ensaio manual MinIO: contrato, permissões e replay IBGE em banco novo."""

import hashlib
import json
import re
import secrets
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
from botocore.exceptions import ClientError
from dotenv import dotenv_values
from ensaiar_recuperacao_local import exigir, retratar
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import URL, text

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.processamento.armazenamento.objetos import (
    ObjetoBronze,
    ObjetoCorrompido,
    ObjetoJaExiste,
    S3Objetos,
    SistemaArquivosObjetos,
)
from pipeline_etl.processamento.armazenamento.s3 import criar_cliente_s3, ler_configuracao_s3
from pipeline_etl.processamento.carga_ibge import carregar_ibge, publicar_ibge
from pipeline_etl.processamento.clientes.ibge import ler_coleta

RAIZ = Path(__file__).resolve().parents[1]


def conferir_destino(banco: str) -> None:
    if not re.fullmatch(r"etl_ensaio_objetos_\d{8}_\d{6}_[0-9a-f]{6}", banco):
        raise ValueError("Replay exige banco novo exclusivo do ensaio de objetos.")


def negar(operacao) -> None:
    try:
        operacao()
    except ClientError as erro:
        exigir(
            erro.response["ResponseMetadata"]["HTTPStatusCode"] == 403,
            "Operação proibida retornou status inesperado.",
        )
    else:
        raise RuntimeError("Política não impediu operação proibida.")


def restaurar_replay(destino: str, segredos: dict) -> str:
    conferir_destino(destino)
    candidatos = sorted((RAIZ / "dados/descoberta").glob("restauracao_m2_*.json"), reverse=True)
    escolhido = None
    for caminho in candidatos:
        registro = json.loads(caminho.read_text(encoding="utf-8"))
        if registro.get("situacao") == "SUCESSO":
            escolhido = registro
            break
    exigir(escolhido is not None, "Execute primeiro o ensaio de restauração M2.")
    backup = (RAIZ / escolhido["backup"]).resolve()
    exigir(
        backup.is_relative_to((RAIZ / "backups").resolve()), "Backup fora do diretório autorizado."
    )
    exigir(
        hashlib.sha256(backup.read_bytes()).hexdigest() == escolhido["sha256_backup"],
        "Backup diverge da evidência validada.",
    )
    with psycopg.connect(
        host="127.0.0.1",
        port=55432,
        dbname="postgres",
        user="administrador",
        password=segredos["SENHA_BANCO_ADMIN"],
        autocommit=True,
    ) as conexao:
        exigir(
            conexao.execute("SELECT 1 FROM pg_database WHERE datname=%s", (destino,)).fetchone()
            is None,
            "Destino existente não pode ser reutilizado.",
        )
        conexao.execute(
            sql.SQL("CREATE DATABASE {} OWNER migracoes TEMPLATE template0").format(
                sql.Identifier(destino)
            )
        )
        conexao.execute(
            sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(destino))
        )
        conexao.execute(
            sql.SQL(
                "GRANT CONNECT ON DATABASE {} TO migracoes,processamento,publicador,api_leitura"
            ).format(sql.Identifier(destino))
        )
    docker = shutil.which("docker") or "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
    with backup.open("rb") as entrada:
        resultado = subprocess.run(
            [
                docker,
                "compose",
                "--env-file",
                ".env.banco",
                "exec",
                "-T",
                "banco",
                "pg_restore",
                "-U",
                "administrador",
                "-d",
                destino,
                "--exit-on-error",
                "--single-transaction",
            ],
            cwd=RAIZ,
            stdin=entrada,
            capture_output=True,
            timeout=180,
        )
    exigir(resultado.returncode == 0, "Restauração do replay falhou; banco isolado preservado.")
    return str(backup.relative_to(RAIZ))


def executar() -> int:
    instante = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    identificador = instante + "_" + secrets.token_hex(3)
    destino = "etl_ensaio_objetos_" + identificador
    configuracao = ler_configuracao_s3(RAIZ / ".env.armazenamento")
    valores = dotenv_values(RAIZ / ".env.armazenamento", interpolate=False)
    segredos = dotenv_values(RAIZ / ".env.banco", interpolate=False)
    cliente = criar_cliente_s3(configuracao)
    administrador = criar_cliente_s3(
        replace(
            configuracao,
            chave_acesso=SecretStr(valores["USUARIO_MINIO_ADMIN"]),
            chave_secreta=SecretStr(valores["SENHA_MINIO_ADMIN"]),
        )
    )
    armazenamento = S3Objetos(
        cliente, configuracao.bucket, configuracao.prefixo + "/ensaios/" + identificador
    )
    local = SistemaArquivosObjetos(RAIZ / ".cache" / ("objetos_" + identificador))
    origem = SistemaArquivosObjetos(RAIZ / "dados/bronze")
    relatorio = {
        "instante_utc": instante,
        "situacao": "EM_EXECUCAO",
        "destino_replay": destino,
        "prefixo_ensaio": configuracao.prefixo + "/ensaios/" + identificador,
    }
    motores = []

    def motor_replay(papel):
        conferir_destino(destino)
        chave = "ADMIN" if papel == "administrador" else papel.upper()
        endereco = URL.create(
            "postgresql+psycopg",
            username=papel,
            password=segredos["SENHA_BANCO_" + chave],
            host="127.0.0.1",
            port=55432,
            database=destino,
        )
        motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
        motores.append(motor)
        return motor

    try:
        corpo = (RAIZ / "testes/amostras/ibge/regioes.body").read_bytes()
        objeto = armazenamento.gravar_imutavel("contrato/regioes.body", corpo)
        exigir(
            objeto == local.gravar_imutavel(objeto.chave, corpo),
            "Descritores dos adapters divergentes.",
        )
        exigir(armazenamento.ler(objeto) == local.ler(objeto), "Bytes retornados divergentes.")
        for tentativa in (corpo, b"sobrescrita indevida"):
            try:
                armazenamento.gravar_imutavel(objeto.chave, tentativa)
            except ObjetoJaExiste:
                pass
            else:
                raise RuntimeError("Sobrescrita não foi impedida.")
        exigir(armazenamento.ler(objeto) == corpo, "Colisão alterou corpo original.")
        try:
            armazenamento.ler(ObjetoBronze(objeto.chave, "0" * 64, objeto.tamanho_bytes))
        except ObjetoCorrompido:
            pass
        else:
            raise RuntimeError("Checksum divergente não foi detectado.")

        def disputar(conteudo):
            try:
                return armazenamento.gravar_imutavel("contrato/disputa.body", conteudo)
            except ObjetoJaExiste:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            respostas = list(executor.map(disputar, (b"primeiro", b"segundo")))
        vencedores = [resposta for resposta in respostas if resposta is not None]
        exigir(len(vencedores) == 1, "Escrita concorrente não teve vencedor exclusivo.")
        armazenamento.ler(vencedores[0])
        chave = relatorio["prefixo_ensaio"] + "/" + objeto.chave
        versao = administrador.head_object(Bucket=configuracao.bucket, Key=chave)["VersionId"]
        negar(lambda: cliente.delete_object(Bucket=configuracao.bucket, Key=chave))
        negar(
            lambda: cliente.delete_object(Bucket=configuracao.bucket, Key=chave, VersionId=versao)
        )
        negar(
            lambda: cliente.put_object(
                Bucket=configuracao.bucket, Key="fora/" + identificador, Body=b"x"
            )
        )
        with httpx.Client(trust_env=False, timeout=5) as anonimo:
            exigir(
                anonimo.get(
                    configuracao.endereco.rstrip("/") + "/" + configuracao.bucket + "/" + chave
                ).status_code
                == 403,
                "Leitura anônima foi permitida.",
            )
        exigir(
            administrador.get_bucket_versioning(Bucket=configuracao.bucket)["Status"] == "Enabled",
            "Versionamento não está habilitado.",
        )
        relatorio["contrato"] = {
            "bytes_sha256": True,
            "sobrescritas_recusadas": 2,
            "vencedor_concorrente_unico": True,
            "corrupcao_detectada": True,
            "exclusao_negada": True,
            "exclusao_versao_negada": True,
            "fora_prefixo_negado": True,
            "anonimo_negado": True,
            "versionado": True,
        }
        print("Contrato S3 e permissões reais aprovados.", flush=True)
        motor_origem = criar_motor(resolver_url_processamento(None, RAIZ / ".env.banco"))
        motores.append(motor_origem)
        with motor_origem.begin() as conexao:
            conexao.execute(text("SET TRANSACTION READ ONLY"))
            parametros = conexao.scalar(
                text(
                    "SELECT e.parametros FROM ops.execucao e JOIN ops.lote l USING(execucao_id) "
                    "LEFT JOIN ops.execucao p "
                    "ON p.execucao_id::text=e.parametros->>'pai_pipeline_id' "
                    "WHERE e.modo='carga_ibge' AND e.situacao='SUCESSO' AND l.fonte='ibge' "
                    "AND COALESCE(p.parametros->'armazenamento'->>'tipo','arquivos')='arquivos' "
                    "ORDER BY e.finalizado_em DESC LIMIT 1"
                )
            )
        exigir(parametros is not None, "Carga IBGE original não encontrada.")
        manifestos = tuple(ObjetoBronze(**objeto) for objeto in parametros["manifestos"])
        descritores = {objeto.chave: objeto for objeto in manifestos}
        for manifesto in manifestos:
            ler_coleta(origem, manifesto)
            for tentativa in json.loads(origem.ler(manifesto))["tentativas"]:
                for nome in ("corpo", "metadados"):
                    descritor = ObjetoBronze(**tentativa[nome])
                    descritores[descritor.chave] = descritor
        for descritor in descritores.values():
            exigir(
                armazenamento.gravar_imutavel(descritor.chave, origem.ler(descritor)) == descritor,
                "Descritor mudou ao migrar objeto.",
            )
        for manifesto in manifestos:
            exigir(
                ler_coleta(origem, manifesto) == ler_coleta(armazenamento, manifesto),
                "Replay do manifesto divergiu entre adapters.",
            )
        relatorio["objetos_transferidos"] = len(descritores)
        relatorio["manifestos"] = len(manifestos)
        relatorio["backup_replay"] = restaurar_replay(destino, segredos)
        processamento = motor_replay("processamento")
        publicador = motor_replay("publicador")
        auditor = motor_replay("administrador")
        arquivos = carregar_ibge(origem, manifestos, processamento)
        exigir(arquivos.situacao == "SUCESSO", "Replay de referência em arquivos falhou.")
        publicar_ibge(publicador)
        antes = {
            nome: valor
            for nome, valor in retratar(auditor)["tabelas"].items()
            if nome.startswith(("core.", "mart."))
        }
        remoto = carregar_ibge(armazenamento, manifestos, processamento)
        exigir(
            remoto.situacao == "SUCESSO" and remoto.inseridas == remoto.alteradas == 0,
            "Replay S3 não foi idempotente.",
        )
        publicacao = publicar_ibge(publicador)
        exigir(publicacao.motivo == "JA_PUBLICADA", "Replay S3 alterou publicação.")
        depois = {
            nome: valor
            for nome, valor in retratar(auditor)["tabelas"].items()
            if nome.startswith(("core.", "mart."))
        }
        exigir(antes == depois, "Replay alterou fatos, metadados ou gold.")
        relatorio.update(
            situacao="SUCESSO",
            referencia_arquivos=asdict(arquivos),
            replay_s3=asdict(remoto),
            publicacao=asdict(publicacao),
            core_mart_preservados=True,
        )
        return 0
    except Exception as erro:
        relatorio.update(situacao="FALHA", tipo_erro=type(erro).__name__)
        raise
    finally:
        for motor in motores:
            motor.dispose()
        cliente.close()
        administrador.close()
        caminho = RAIZ / "dados/descoberta" / ("objetos_s3_" + identificador + ".json")
        caminho.write_text(
            json.dumps(relatorio, default=str, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {"situacao": relatorio["situacao"], "relatorio": str(caminho.relative_to(RAIZ))}
            )
        )


if __name__ == "__main__":
    raise SystemExit(executar())
