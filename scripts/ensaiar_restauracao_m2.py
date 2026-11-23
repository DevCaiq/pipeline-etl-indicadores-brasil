"""Backup e restauração BCB/IBGE em banco novo, com origem somente leitura."""

import copy
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psycopg
from dotenv import dotenv_values
from ensaiar_recuperacao_local import exigir, normalizar_sql, retratar, soma_logica
from fastapi.testclient import TestClient
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import URL, text

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao

RAIZ = Path(__file__).resolve().parents[1]


def conferir_destino(destino: str) -> None:
    """Somente banco exclusivo gerado pelo ensaio pode receber restauração."""
    if not re.fullmatch(r"etl_ensaio_m2_\d{8}_\d{6}_[0-9a-f]{6}", destino):
        raise ValueError("Nome de destino fora do padrão exclusivo de restauração M2.")


def normalizar_resposta(corpo: dict) -> dict:
    """Mantém dados/metadados; o cursor pode ter outro instante de assinatura."""
    resultado = copy.deepcopy(corpo)
    if isinstance(resultado.get("pagina"), dict):
        resultado["pagina"]["proximo_cursor"] = bool(resultado["pagina"].get("proximo_cursor"))
    return resultado


def url_proxima_pagina(rota: str, cursor: str) -> str:
    """Acrescenta cursor sem perder filtros integrantes da assinatura."""
    return str(httpx.URL(rota).copy_merge_params({"cursor": cursor}))


def retratar_m2(motor) -> dict:
    """Inclui dados, ACLs, DDL, gatilhos core e posição das sequências."""
    resultado = retratar(motor)
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION READ ONLY"))
        consultas = {
            "tipos_completos": (
                "SELECT n.nspname,c.relname,a.attname,"
                "format_type(a.atttypid,a.atttypmod),a.attndims,a.attidentity,a.attgenerated "
                "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('public','core','ops','mart') "
                "AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,3"
            ),
            "funcoes_core_ops": (
                "SELECT n.nspname,p.proname,pg_get_functiondef(p.oid),"
                "pg_get_userbyid(p.proowner),p.proacl::text FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname IN ('core','ops') ORDER BY 1,2,3"
            ),
            "gatilhos": (
                "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid),t.tgenabled "
                "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('core','ops','mart') AND NOT t.tgisinternal "
                "ORDER BY 1,2,3"
            ),
            "sequencias": (
                "SELECT schemaname,sequencename,start_value,min_value,max_value,"
                "increment_by,cycle,cache_size,last_value FROM pg_sequences "
                "WHERE schemaname IN ('public','core','ops','mart') ORDER BY 1,2"
            ),
        }
        for nome, consulta in consultas.items():
            resultado["catalogo"][nome] = soma_logica(
                [
                    tuple(
                        normalizar_sql(valor) if isinstance(valor, str) else valor
                        for valor in linha
                    )
                    for linha in conexao.execute(text(consulta))
                ]
            )
    return resultado


def comparar_api(origem, restaurado) -> dict:
    """Usa o papel API nos dois bancos e reaproveita cursor assinado da origem."""
    configuracao = ConfiguracaoAplicacao(
        segredo_cursor=SecretStr(secrets.token_hex(48)),
        limite_requisicoes_minuto=1000,
        cache_habilitado=False,
    )
    rotas = [
        "/health",
        "/ready",
        "/api/v1/series",
        "/api/v1/series/432/observacoes?de=2020-01-02&ate=2020-01-06",
        "/api/v1/regioes",
        "/api/v1/ufs",
        "/api/v1/municipios?limite=2",
        "/api/v1/municipios/3550308",
        "/api/v1/municipios/3550308/populacao?limite=2",
        "/api/v1/municipios/5101837/populacao",
    ]
    for ano in (2020, 2021, 2024, 2025, 2026):
        rotas.extend(
            f"/api/v1/populacao/{nivel}?ano={ano}" for nivel in ("ufs", "regioes", "brasil")
        )
    resultado = {}
    with (
        TestClient(criar_aplicacao(configuracao, origem)) as cliente_origem,
        TestClient(criar_aplicacao(configuracao, restaurado)) as cliente_restaurado,
    ):
        for rota in rotas:
            primeira = cliente_origem.get(rota)
            segunda = cliente_restaurado.get(rota)
            exigir(
                primeira.status_code == segunda.status_code == 200,
                "Sondagem API não retornou 200 nos dois bancos.",
            )
            corpo = primeira.json()
            normalizado = normalizar_resposta(corpo)
            exigir(
                normalizado == normalizar_resposta(segunda.json()),
                "Resposta API restaurada diverge da origem.",
            )
            resultado[rota] = soma_logica([normalizado])
            cursor = (corpo.get("pagina") or {}).get("proximo_cursor")
            if cursor:
                respostas = [
                    cliente.get(url_proxima_pagina(rota, cursor))
                    for cliente in (cliente_origem, cliente_restaurado)
                ]
                exigir(
                    all(resposta.status_code == 200 for resposta in respostas),
                    "Continuidade do cursor falhou após restauração.",
                )
                exigir(
                    normalizar_resposta(respostas[0].json())
                    == normalizar_resposta(respostas[1].json()),
                    "Segunda página diverge após restauração.",
                )
                resultado[rota]["segunda_pagina"] = soma_logica(
                    [normalizar_resposta(respostas[1].json())]
                )
        exigir(
            any("segunda_pagina" in evidencia for evidencia in resultado.values()),
            "Ensaio exige ao menos uma continuidade de cursor comprovada.",
        )
    return resultado


def executar() -> int:
    inicio = datetime.now(UTC)
    instante = inicio.strftime("%Y%m%d_%H%M%S")
    destino = "etl_ensaio_m2_" + instante + "_" + secrets.token_hex(3)
    conferir_destino(destino)
    docker = shutil.which("docker") or "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
    comando = [
        docker,
        "compose",
        "--project-name",
        "pipeline-etl",
        "--env-file",
        ".env.banco",
        "exec",
        "-T",
        "banco",
    ]
    segredos = dotenv_values(RAIZ / ".env.banco", interpolate=False)
    pasta = RAIZ / "dados/descoberta"
    pasta.mkdir(parents=True, exist_ok=True)
    (RAIZ / "backups").mkdir(exist_ok=True)
    backup = RAIZ / "backups" / ("m2_" + instante + "_" + destino[-6:] + ".dump")
    relatorio = {
        "iniciado_em": inicio.isoformat(),
        "destino": destino,
        "backup": str(backup.relative_to(RAIZ)),
        "situacao": "EM_EXECUCAO",
    }
    motores = []

    def motor_local(banco, papel):
        exigir(banco in {"etl", destino}, "Banco fora do escopo do ensaio.")
        chave = "ADMIN" if papel == "administrador" else "API"
        endereco = URL.create(
            "postgresql+psycopg",
            username=papel,
            password=segredos["SENHA_BANCO_" + chave],
            host="127.0.0.1",
            port=55432,
            database=banco,
        )
        motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
        motores.append(motor)
        return motor

    try:
        origem = motor_local("etl", "administrador")
        antes = retratar_m2(origem)
        exigir(
            antes["tabelas"]["core.fato_populacao"]["linhas"] > 0,
            "Ensaio M2 exige dados IBGE já confirmados.",
        )
        with backup.open("xb") as saida:
            resultado = subprocess.run(
                comando + ["pg_dump", "-U", "administrador", "-Fc", "etl"],
                cwd=RAIZ,
                stdout=saida,
                stderr=subprocess.PIPE,
                check=False,
                timeout=180,
            )
        exigir(resultado.returncode == 0, "Backup falhou; restauração não iniciada.")
        relatorio["sha256_backup"] = hashlib.sha256(backup.read_bytes()).hexdigest()
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
                conexao.execute("SELECT 1 FROM pg_database WHERE datname=%s", (destino,)).fetchone()
                is None,
                "Destino já existe; não reutilizar.",
            )
            conferir_destino(destino)
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
                    "GRANT CONNECT ON DATABASE {} TO migracoes,processamento,api_leitura,publicador"
                ).format(sql.Identifier(destino))
            )
        inicio_restauracao = time.monotonic()
        with backup.open("rb") as entrada:
            resultado = subprocess.run(
                comando
                + [
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
                check=False,
                timeout=180,
            )
        exigir(resultado.returncode == 0, "Restauração falhou; destino isolado preservado.")
        relatorio["restauracao_segundos"] = round(time.monotonic() - inicio_restauracao, 3)
        clone = motor_local(destino, "administrador")
        exigir(retratar_m2(clone) == antes, "Dados ou catálogo restaurados divergentes.")
        relatorio["http"] = comparar_api(
            motor_local("etl", "api_leitura"), motor_local(destino, "api_leitura")
        )
        exigir(retratar_m2(clone) == antes, "Sondagens modificaram o banco restaurado.")
        exigir(
            retratar_m2(origem) == antes, "Origem mudou durante o ensaio; não concluir igualdade."
        )
        relatorio.update(
            situacao="SUCESSO", origem_preservada=True, clone_preservado=True, retrato=antes
        )
        return 0
    except Exception as erro:
        relatorio.update(situacao="FALHA", tipo_erro=type(erro).__name__)
        raise
    finally:
        for motor in motores:
            motor.dispose()
        relatorio["finalizado_em"] = datetime.now(UTC).isoformat()
        caminho = pasta / ("restauracao_m2_" + instante + "_" + destino[-6:] + ".json")
        with caminho.open("x", encoding="utf-8") as saida:
            json.dump(relatorio, saida, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    "situacao": relatorio["situacao"],
                    "destino": destino,
                    "relatorio": str(caminho.relative_to(RAIZ)),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    raise SystemExit(executar())
