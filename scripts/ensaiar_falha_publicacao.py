"""Falha controlada de refresh apenas em clone novo; origem permanece somente leitura."""

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

import psycopg
from dotenv import dotenv_values
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import URL, event, text

from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.processamento.publicacao import publicar_bcb

RAIZ = Path(__file__).resolve().parents[1]
DOCKER = "C:/Program Files/Docker/Docker/resources/bin/docker.exe"


def exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise RuntimeError(mensagem)


def retratar(motor) -> dict:
    resultado = {}
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        conexao.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        for nome in (
            "core.fato_serie",
            "ops.watermark_bcb",
            "mart.mv_serie_mensal",
            "mart.mv_serie_anual",
            "mart.mv_ipca_12m",
        ):
            linhas = (
                conexao.execute(text(f"SELECT to_jsonb(t)::text FROM {nome} t ORDER BY 1"))
                .scalars()
                .all()
            )
            resultado[nome] = {
                "linhas": len(linhas),
                "sha256": hashlib.sha256(json.dumps(linhas).encode()).hexdigest(),
            }
    return resultado


def executar() -> int:
    instante = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    banco = "etl_ensaio_refresh_" + instante + "_" + token_hex(3)
    exigir(banco.startswith("etl_ensaio_refresh_") and banco != "etl", "Destino protegido.")
    segredos = dotenv_values(RAIZ / ".env.banco", interpolate=False)
    motores = []

    def motor_local(destino: str, papel: str):
        exigir(destino in {"etl", banco}, "Destino não autorizado pelo ensaio.")
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

    copia = RAIZ / "backups" / ("antes_refresh_" + instante + ".dump")
    comando = [
        DOCKER,
        "compose",
        "--project-name",
        "pipeline-etl",
        "--env-file",
        ".env.banco",
        "exec",
        "-T",
        "banco",
    ]
    try:
        origem = motor_local("etl", "administrador")
        antes = retratar(origem)
        with copia.open("xb") as saida:
            resultado = subprocess.run(
                comando + ["pg_dump", "-U", "administrador", "-Fc", "etl"],
                cwd=RAIZ,
                stdout=saida,
                stderr=subprocess.PIPE,
                check=False,
                timeout=120,
            )
        exigir(resultado.returncode == 0, "Backup não concluído; não iniciar ensaio.")
        with psycopg.connect(
            host="127.0.0.1",
            port=55432,
            dbname="postgres",
            user="administrador",
            password=segredos["SENHA_BANCO_ADMIN"],
            autocommit=True,
            connect_timeout=5,
        ) as conexao:
            exigir(
                conexao.execute("SELECT 1 FROM pg_database WHERE datname=%s", (banco,)).fetchone()
                is None,
                "Banco já existe; não reutilizar.",
            )
            conexao.execute(
                sql.SQL("CREATE DATABASE {} OWNER migracoes TEMPLATE template0").format(
                    sql.Identifier(banco)
                )
            )
            conexao.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(banco))
            )
            conexao.execute(
                sql.SQL(
                    "GRANT CONNECT ON DATABASE {} TO migracoes,processamento,api_leitura,publicador"
                ).format(sql.Identifier(banco))
            )
        with copia.open("rb") as entrada:
            resultado = subprocess.run(
                comando
                + [
                    "pg_restore",
                    "-U",
                    "administrador",
                    "-d",
                    banco,
                    "--exit-on-error",
                    "--single-transaction",
                ],
                cwd=RAIZ,
                stdin=entrada,
                capture_output=True,
                check=False,
                timeout=120,
            )
        exigir(resultado.returncode == 0, "Restauração do clone falhou.")
        clone = motor_local(banco, "administrador")
        publicador = motor_local(banco, "publicador")
        exigir(retratar(clone) == antes, "Clone inicial não coincide com origem.")
        with clone.begin() as conexao:
            conexao.execute(
                text("UPDATE ops.publicacao SET data_publicacao=NULL WHERE dominio='bcb'")
            )

        def falhar_segundo_refresh(conexao, cursor, comando, parametros, contexto, multiplos):
            if comando.startswith("REFRESH MATERIALIZED VIEW mart.mv_serie_anual"):
                raise RuntimeError("FALHA_SIMULADA_SOMENTE_NO_CLONE")

        event.listen(publicador, "before_cursor_execute", falhar_segundo_refresh)
        try:
            falha = publicar_bcb(publicador)
        finally:
            event.remove(publicador, "before_cursor_execute", falhar_segundo_refresh)
        exigir(falha.situacao == "FALHA", "Falha não foi observada.")
        exigir(retratar(clone) == antes, "Rollback não preservou core/checkpoints/gold.")
        with clone.connect() as conexao:
            estado_falha = conexao.execute(
                text(
                    "SELECT versao_core,versao_gold,situacao FROM ops.publicacao "
                    "WHERE dominio='bcb'"
                )
            ).one()
        exigir(estado_falha.situacao == "PENDENTE", "Falha precisa manter publicação pendente.")
        recuperacao = publicar_bcb(publicador)
        exigir(recuperacao.situacao == "SUCESSO", "Recuperação da publicação falhou.")
        # A referência diária pode mudar se a fonte foi publicada no dia anterior.
        depois = retratar(clone)
        for nome in ("core.fato_serie", "ops.watermark_bcb"):
            exigir(
                depois[nome] == antes[nome], "Recuperação não pode modificar fatos ou checkpoints."
            )
        with clone.connect() as conexao:
            estado = conexao.execute(
                text(
                    "SELECT versao_core,versao_gold,situacao FROM ops.publicacao "
                    "WHERE dominio='bcb'"
                )
            ).one()
        exigir(
            estado.versao_core == estado.versao_gold and estado.situacao == "PRONTA",
            "Estado final inconsistente.",
        )
        exigir(retratar(origem) == antes, "Produção mudou durante o ensaio.")
        relatorio = {
            "banco_isolado": banco,
            "backup": str(copia),
            "sha256_backup": hashlib.sha256(copia.read_bytes()).hexdigest(),
            "falha_id": str(falha.execucao_id),
            "recuperacao_id": str(recuperacao.execucao_id),
            "estado_falha": tuple(estado_falha),
            "estado_final": tuple(estado),
            "rollback_integral_gold": True,
            "origem_preservada": True,
            "fatos_checkpoints_preservados": True,
            "antes": antes,
            "depois": depois,
        }
        caminho = RAIZ / "dados/descoberta" / ("falha_refresh_" + instante + ".json")
        with caminho.open("x", encoding="utf-8") as saida:
            json.dump(relatorio, saida, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {"relatorio": str(caminho), "banco": banco, "situacao": "SUCESSO"},
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        for motor in motores:
            motor.dispose()


if __name__ == "__main__":
    raise SystemExit(executar())
