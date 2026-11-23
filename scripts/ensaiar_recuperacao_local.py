"""Ensaio manual: restaura backup e reconstrói bronze em bancos novos, sem DROP."""

import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

import psycopg
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import URL, text

from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.carga import carregar_manifesto
from pipeline_etl.processamento.manifestos import ler_manifesto
from pipeline_etl.processamento.publicacao import publicar_bcb

RAIZ = Path(__file__).resolve().parents[1]
DOCKER = Path("C:/Program Files/Docker/Docker/resources/bin/docker.exe")


def exigir(condicao: bool, mensagem: str) -> None:
    """Falha mesmo quando Python é iniciado com otimização."""
    if not condicao:
        raise RuntimeError(mensagem)


def soma_logica(linhas) -> dict:
    conteudo = json.dumps(linhas, default=str, ensure_ascii=False, sort_keys=True).encode()
    return {"linhas": len(linhas), "sha256": hashlib.sha256(conteudo).hexdigest()}


def normalizar_sql(definicao: str) -> str:
    """Uniformiza apenas o cast textual de arrays de literais reescrito no restore."""
    padrao = r"\(ARRAY\[((?:'[^']*'::character varying(?:, )?)+)\]\)::text\[\]"

    def substituir(resultado: re.Match[str]) -> str:
        elementos = re.findall(r"'[^']*'::character varying", resultado.group(1))
        return "ARRAY[" + ", ".join(f"({elemento})::text" for elemento in elementos) + "]"

    return re.sub(padrao, substituir, definicao)


def retratar(motor) -> dict:
    """Retrato consistente dos dados, DDL básico, donos e permissões locais."""
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        conexao.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        relacoes = conexao.execute(
            text(
                "SELECT n.nspname,c.relname,c.relkind,pg_get_userbyid(c.relowner),"
                "(SELECT array_agg(a::text ORDER BY a::text)::text FROM unnest(c.relacl) a) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname IN ('public','core','ops','mart') "
                "AND c.relkind IN ('r','m','v','S') ORDER BY 1,2"
            )
        ).all()
        tabelas = {}
        for esquema, nome, tipo, _, _ in relacoes:
            if tipo in ("r", "m"):
                # Identificadores vêm exclusivamente do catálogo PostgreSQL e são citados.
                preparador = conexao.dialect.identifier_preparer
                identificador = f"{preparador.quote(esquema)}.{preparador.quote(nome)}"
                linhas = (
                    conexao.execute(
                        text(f"SELECT to_jsonb(t)::text FROM {identificador} t ORDER BY 1")
                    )
                    .scalars()
                    .all()
                )
                tabelas[f"{esquema}.{nome}"] = soma_logica(linhas)
        catalogo = {}
        consultas = {
            "permissoes_colunas": "SELECT n.nspname,c.relname,a.attname,"
            "(SELECT array_agg(p::text ORDER BY p::text)::text FROM unnest(a.attacl) p) "
            "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname IN ('public','core','ops','mart') "
            "AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2,3",
            "permissoes_banco": "SELECT pg_get_userbyid(datdba),"
            "(SELECT array_agg(p::text ORDER BY p::text)::text FROM unnest(datacl) p) "
            "FROM pg_database WHERE datname=current_database()",
            "colunas": "SELECT table_schema,table_name,column_name,ordinal_position,"
            "data_type,is_nullable,column_default,numeric_precision,numeric_scale "
            "FROM information_schema.columns WHERE table_schema IN "
            "('public','core','ops','mart') ORDER BY 1,2,4",
            "restricoes": "SELECT n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid) "
            "FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname IN ('public','core','ops','mart') ORDER BY 1,2,3",
            "indices": "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes "
            "WHERE schemaname IN ('public','core','ops','mart') ORDER BY 1,2,3",
            "esquemas": "SELECT nspname,pg_get_userbyid(nspowner),nspacl::text "
            "FROM pg_namespace WHERE nspname IN ('public','core','ops','mart') ORDER BY 1",
            "visoes": "SELECT schemaname,viewname,definition FROM pg_views "
            "WHERE schemaname IN ('core','ops','mart') ORDER BY 1,2",
            "materializadas": "SELECT schemaname,matviewname,definition FROM pg_matviews "
            "WHERE schemaname='mart' ORDER BY 1,2",
            "funcoes": "SELECT n.nspname,p.proname,pg_get_functiondef(p.oid),"
            "pg_get_userbyid(p.proowner),p.proacl::text FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='mart' ORDER BY 1,2",
            "privilegios_padrao": "SELECT pg_get_userbyid(d.defaclrole),n.nspname,"
            "d.defaclobjtype,d.defaclacl::text FROM pg_default_acl d "
            "LEFT JOIN pg_namespace n ON n.oid=d.defaclnamespace ORDER BY 1,2,3",
        }
        for nome, consulta in consultas.items():
            catalogo[nome] = soma_logica(
                [
                    tuple(
                        normalizar_sql(valor) if isinstance(valor, str) else valor
                        for valor in linha
                    )
                    for linha in conexao.execute(text(consulta))
                ]
            )
        catalogo["relacoes"] = soma_logica([tuple(linha) for linha in relacoes])
        return {"tabelas": tabelas, "catalogo": catalogo}


def retratar_semantica(motor) -> dict:
    """Replay recria IDs/instantes de auditoria; compara origem e valores de negócio."""
    consultas = {
        "fatos": "SELECT f.codigo_sgs,f.data,f.valor,f.origem_coletada_em,l.checksum "
        "FROM core.fato_serie f JOIN ops.lote l USING(lote_id) ORDER BY 1,2",
        "cobertura": "SELECT codigo_sgs,fim_coberto,ultima_observacao "
        "FROM ops.watermark_bcb ORDER BY 1",
        "publicacao": "SELECT * FROM ops.publicacao ORDER BY dominio",
        "catalogo": "SELECT * FROM core.dim_serie ORDER BY codigo_sgs",
    }
    for nome in ("mv_serie_mensal", "mv_serie_anual", "mv_ipca_12m"):
        consultas[nome] = f"SELECT * FROM mart.{nome} ORDER BY codigo_sgs,periodo"
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        conexao.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        return {
            nome: soma_logica([tuple(linha) for linha in conexao.execute(text(consulta))])
            for nome, consulta in consultas.items()
        }


def executar() -> int:
    if len(sys.argv) != 2:
        print(
            "Uso: uv run --frozen python scripts/ensaiar_recuperacao_local.py backups/ARQUIVO.dump"
        )
        return 2
    backup = Path(sys.argv[1]).resolve()
    exigir(backup.is_relative_to(RAIZ / "backups"), "Backup deve estar dentro de backups/.")
    exigir(backup.is_file() and backup.suffix == ".dump", "Backup local .dump obrigatório.")
    exigir(backup.read_bytes()[:5] == b"PGDMP", "Esperado backup PostgreSQL custom.")
    segredos = dotenv_values(RAIZ / ".env.banco", interpolate=False)
    inicio = datetime.now(UTC)
    sufixo = inicio.strftime("%Y%m%d_%H%M%S_") + token_hex(3)
    destinos = {"restauracao": "etl_ensaio_rest_" + sufixo, "replay": "etl_ensaio_replay_" + sufixo}
    criados = set()
    motores = []

    def motor_local(banco: str, papel: str):
        exigir(banco == "etl" or banco in criados, "Destino não criado por este ensaio.")
        endereco = URL.create(
            "postgresql+psycopg",
            username=papel,
            password=segredos[
                "SENHA_BANCO_" + ("ADMIN" if papel == "administrador" else papel.upper())
            ],
            host="127.0.0.1",
            port=55432,
            database=banco,
        )
        motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
        motores.append(motor)
        return motor

    def conferir_destino(banco: str) -> None:
        exigir(banco in criados and banco in destinos.values(), "Destino não pertence ao ensaio.")
        exigir(
            banco.startswith("etl_ensaio_") and banco not in {"etl", "etl_testes"},
            "Nome de banco protegido.",
        )

    relatorio = {
        "iniciado_em": inicio.isoformat(),
        "backup": str(backup),
        "sha256_backup": hashlib.sha256(backup.read_bytes()).hexdigest(),
        "destinos": destinos,
    }
    try:
        origem = motor_local("etl", "administrador")
        antes = retratar(origem)
        semantica = retratar_semantica(origem)
        with origem.begin() as conexao:
            conexao.execute(text("SET TRANSACTION READ ONLY"))
            plano = [
                dict(linha)
                for linha in conexao.execute(
                    text(
                        "SELECT l.manifesto,l.checksum,l.confirmado_em,l.execucao_id "
                        "FROM ops.lote l JOIN ops.execucao e USING(execucao_id) "
                        "WHERE e.modo='carga_bcb' AND e.situacao='SUCESSO' "
                        "ORDER BY l.confirmado_em,l.execucao_id"
                    )
                ).mappings()
            ]
        exigir(bool(plano), "Nenhuma promoção confirmada para reconstruir.")
        armazenamento = ArmazenamentoBronze(RAIZ / "dados/bronze")
        for item in plano:
            caminho = Path(item["manifesto"])
            ler_manifesto(armazenamento, caminho)
            exigir(
                hashlib.sha256(caminho.read_bytes()).hexdigest() == item["checksum"],
                "Manifesto difere da promoção original.",
            )
        relatorio["plano_replay"] = plano
        with psycopg.connect(
            host="127.0.0.1",
            port=55432,
            dbname="postgres",
            user="administrador",
            password=segredos["SENHA_BANCO_ADMIN"],
            autocommit=True,
            connect_timeout=5,
        ) as conexao:
            for banco in destinos.values():
                exigir(banco.startswith("etl_ensaio_"), "Nome de banco inválido.")
                exigir(
                    conexao.execute(
                        "SELECT 1 FROM pg_database WHERE datname=%s", (banco,)
                    ).fetchone()
                    is None,
                    "Banco existente: cancelado sem reutilização.",
                )
                conexao.execute(
                    sql.SQL("CREATE DATABASE {} OWNER migracoes TEMPLATE template0").format(
                        sql.Identifier(banco)
                    )
                )
                criados.add(banco)
                conexao.execute(
                    sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(banco))
                )
                conexao.execute(
                    sql.SQL(
                        "GRANT CONNECT ON DATABASE {} TO migracoes, "
                        "processamento,publicador,api_leitura"
                    ).format(sql.Identifier(banco))
                )
        banco = destinos["restauracao"]
        conferir_destino(banco)
        inicio_fase = time.monotonic()
        with backup.open("rb") as entrada:
            resultado = subprocess.run(
                [
                    str(DOCKER),
                    "compose",
                    "--env-file",
                    ".env.banco",
                    "exec",
                    "-T",
                    "banco",
                    "pg_restore",
                    "-U",
                    "administrador",
                    "--dbname",
                    banco,
                    "--exit-on-error",
                    "--single-transaction",
                ],
                cwd=RAIZ,
                stdin=entrada,
                capture_output=True,
                check=False,
                timeout=180,
            )
        exigir(resultado.returncode == 0, "pg_restore falhou; destino isolado preservado.")
        restaurado = motor_local(banco, "administrador")
        exigir(retratar(restaurado) == antes, "Restauração diverge dos dados ou catálogo atuais.")
        relatorio["restauracao"] = {
            "segundos": round(time.monotonic() - inicio_fase, 3),
            "retrato_integral_identico": True,
        }
        banco = destinos["replay"]
        conferir_destino(banco)
        inicio_fase = time.monotonic()
        migrador = motor_local(banco, "migracoes")
        configuracao = Config(str(RAIZ / "alembic.ini"))
        with migrador.begin() as conexao:
            configuracao.attributes["conexao"] = conexao
            command.upgrade(configuracao, "head")
        processamento = motor_local(banco, "processamento")
        cargas = []
        for item in plano:
            resumo = carregar_manifesto(armazenamento, Path(item["manifesto"]), processamento)
            exigir(resumo.situacao == "SUCESSO", "Replay não confirmou uma promoção.")
            cargas.append(
                {
                    "execucao_id": str(resumo.execucao_id),
                    "inseridas": resumo.inseridas,
                    "alteradas": resumo.alteradas,
                }
            )
        publicador = motor_local(banco, "publicador")
        publicacao = publicar_bcb(publicador)
        exigir(publicacao.situacao == "SUCESSO", "Publicação do replay falhou.")
        reconstruido = motor_local(banco, "administrador")
        exigir(
            retratar_semantica(reconstruido) == semantica,
            "Replay diverge em fatos, origem, cobertura ou gold.",
        )
        exigir(
            retratar(reconstruido)["catalogo"] == antes["catalogo"],
            "Replay diverge no esquema ou permissões.",
        )
        relatorio["replay"] = {
            "segundos": round(time.monotonic() - inicio_fase, 3),
            "promocoes": len(cargas),
            "cargas": cargas,
            "semantica_identica": True,
            "catalogo_identico": True,
        }
        exigir(retratar(origem) == antes, "Base etl mudou durante o ensaio.")
        relatorio.update(
            {
                "origem_preservada": True,
                "retrato_origem": antes,
                "semantica": semantica,
                "situacao": "SUCESSO",
            }
        )
        destino = RAIZ / "dados/descoberta" / ("recuperacao_" + sufixo + ".json")
        with destino.open("x", encoding="utf-8") as arquivo:
            json.dump(relatorio, arquivo, default=str, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    "situacao": "SUCESSO",
                    "relatorio": str(destino),
                    "destinos": destinos,
                    "promocoes": len(cargas),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        for motor in motores:
            motor.dispose()


if __name__ == "__main__":
    raise SystemExit(executar())
