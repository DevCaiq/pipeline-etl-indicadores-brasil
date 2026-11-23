"""Benchmark M2: um milhão de observações SIMULADAS em banco e Redis exclusivos."""

import hashlib
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path

import httpx
import psycopg
import redis
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from medir_desempenho_local import comparar_planos, exigir, medir_http, retratar
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy import URL, text

from pipeline_etl.banco.sessoes import criar_motor

RAIZ = Path(__file__).resolve().parents[1]
SEMENTE = 20261119
SERIES_SINTETICAS = 400
DIAS_POR_SERIE = 2500


class MedidorCache:
    """Instrumentação exclusiva do benchmark; registra retorno sem executar cálculo."""

    def __init__(self, cache):
        self.cache = cache
        self.trava = threading.Lock()
        self.acertos = 0
        self.calculos = 0

    def obter_ou_calcular(self, chave, calcular, validade=300):
        calculou = False

        def calcular_contado():
            nonlocal calculou
            calculou = True
            return calcular()

        resultado = self.cache.obter_ou_calcular(chave, calcular_contado, validade)
        with self.trava:
            if calculou:
                self.calculos += 1
            else:
                self.acertos += 1
        return resultado

    def retratar(self):
        with self.trava:
            return {"acertos": self.acertos, "calculos": self.calculos}


def servir_ensaio(porta):
    """API real com contador adicional apenas no subprocesso do benchmark."""
    import uvicorn

    from pipeline_etl.api.aplicacao import criar_aplicacao
    from pipeline_etl.configuracao import ConfiguracaoAplicacao
    from pipeline_etl.registros import configurar_registros

    configuracao = ConfiguracaoAplicacao()
    configurar_registros(configuracao.nivel_registros)
    aplicacao = criar_aplicacao(configuracao)
    medidor = MedidorCache(aplicacao.state.cache_leitura)
    aplicacao.state.cache_leitura = medidor

    @aplicacao.get("/benchmark/contadores", include_in_schema=False)
    def consultar_contadores():
        return medidor.retratar()

    uvicorn.run(aplicacao, host="127.0.0.1", port=porta, access_log=False, proxy_headers=False)


def limpar_redis_exclusivo(docker, rotulo):
    """Remove somente recursos do rótulo aleatório e nunca interrompe o relatório."""
    filtro = "label=pipeline_etl.benchmark=" + rotulo
    try:
        consulta = subprocess.run(
            [docker, "ps", "-aq", "--filter", filtro],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        identificadores = consulta.stdout.split()
        for identificador in identificadores:
            subprocess.run(
                [docker, "rm", "-f", identificador], capture_output=True, check=True, timeout=30
            )
        confirmacao = subprocess.run(
            [docker, "ps", "-aq", "--filter", filtro],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        )
        return {"confirmada": not confirmacao.stdout.strip(), "recursos": len(identificadores)}
    except Exception as erro:
        return {"confirmada": False, "tipo_erro": type(erro).__name__}


def conferir_destino(banco: str) -> None:
    if not re.fullmatch(r"etl_benchmark_m2_\d{8}_\d{6}_[0-9a-f]{6}", banco):
        raise ValueError("Benchmark exige banco exclusivo gerado pelo próprio ensaio.")


def avaliar_meta(resumo: dict, cache: bool) -> bool:
    return (
        resumo["p95_ms"] <= (250 if cache else 500)
        and resumo["percentual_5xx"] < 1
        and set(resumo["estados_http"]) == {"200"}
        and resumo["erros_transporte"] == resumo["erros_validacao"] == 0
    )


def porta_livre() -> int:
    with socket.socket() as reserva:
        reserva.bind(("127.0.0.1", 0))
        return reserva.getsockname()[1]


def retratar_sintetico(motor) -> dict:
    """SHA-256 de todas as linhas via COPY, sem acumular o milhão em RAM Python."""
    resultado = {}
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        conexao.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        relacoes = conexao.execute(
            text(
                "SELECT n.nspname,c.relname FROM pg_class c JOIN pg_namespace n "
                "ON n.oid=c.relnamespace WHERE n.nspname IN ('core','ops','mart') "
                "AND c.relkind IN ('r','m') ORDER BY 1,2"
            )
        ).all()
        for esquema, nome in relacoes:
            identificador = sql.Identifier(esquema, nome)
            ordem = (
                sql.SQL("codigo_sgs,data")
                if (esquema, nome) == ("core", "fato_serie")
                else sql.SQL("1")
            )
            consulta = sql.SQL(
                "COPY (SELECT to_jsonb(t)::text FROM {} t ORDER BY {}) TO STDOUT (FORMAT BINARY)"
            ).format(identificador, ordem)
            soma = hashlib.sha256()
            with (
                conexao.connection.driver_connection.cursor() as cursor,
                cursor.copy(consulta) as copia,
            ):
                for bloco in copia:
                    soma.update(bloco)
            preparador = conexao.dialect.identifier_preparer
            nome_sql = preparador.quote(esquema) + "." + preparador.quote(nome)
            quantidade = conexao.scalar(text(f"SELECT count(*) FROM {nome_sql}"))
            resultado[f"{esquema}.{nome}"] = {"linhas": quantidade, "sha256": soma.hexdigest()}
    return resultado


def preparar_sintetico(motor, destino: str) -> dict:
    """Usa somente migrações/índices existentes; não altera dados operacionais."""
    conferir_destino(destino)
    exigir(motor.url.database == destino, "Motor não aponta para o banco exclusivo.")
    exigir(
        date(2020, 1, 1) + timedelta(days=DIAS_POR_SERIE - 1) <= date.today(),
        "Recorte sintético não pode conter observações futuras.",
    )
    configuracao = Config(str(RAIZ / "alembic.ini"))
    with motor.begin() as conexao:
        configuracao.attributes["conexao"] = conexao
        command.upgrade(configuracao, "head")
        exigir(
            conexao.scalar(text("SELECT count(*) FROM core.fato_serie")) == 0,
            "Não reutilizar banco já populado.",
        )
        conexao.execute(text("DELETE FROM core.dim_serie"))
        conexao.execute(
            text(
                "INSERT INTO core.dim_serie(codigo_sgs,nome,periodicidade,unidade,inicio_publico) "
                "SELECT CASE WHEN numero=0 THEN 432 ELSE 10000+numero END,"
                "'SIMULADA — série '||numero,'diaria','unidade simulada','2020-01-01'::date "
                "FROM generate_series(0,:series-1) AS numero"
            ),
            {"series": SERIES_SINTETICAS},
        )
        execucao = conexao.scalar(
            text(
                "INSERT INTO ops.execucao(modo,situacao,parametros,finalizado_em) "
                "VALUES('benchmark_simulado','SUCESSO',CAST(:parametros AS jsonb),now()) "
                "RETURNING execucao_id"
            ),
            {"parametros": json.dumps({"simulacao": True, "semente": SEMENTE})},
        )
        lote = conexao.scalar(
            text(
                "INSERT INTO ops.lote(execucao_id,fonte,chave,janela_inicio,janela_fim,"
                "manifesto,confirmado_em) VALUES(:execucao,'simulacao','benchmark_m2',"
                "'2020-01-01','2026-11-04','SIMULACAO_SEM_FONTE_EXTERNA',now()) RETURNING lote_id"
            ),
            {"execucao": execucao},
        )
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id,origem_coletada_em) "
                "SELECT s.codigo_sgs,DATE '2020-01-01'+dia,"
                "((s.codigo_sgs::bigint*17+dia*31+:semente)%100000)::numeric/100::numeric,"
                ":lote,'2026-11-19T00:00:00Z'::timestamptz "
                "FROM core.dim_serie s CROSS JOIN generate_series(0,:dias-1) AS dia"
            ),
            {"semente": SEMENTE, "lote": lote, "dias": DIAS_POR_SERIE},
        )
        for nome in ("mv_serie_mensal", "mv_serie_anual", "mv_ipca_12m"):
            conexao.execute(text(f"REFRESH MATERIALIZED VIEW mart.{nome}"))
        conexao.execute(
            text(
                "INSERT INTO ops.publicacao"
                "(dominio,versao_core,versao_gold,situacao,data_publicacao) "
                "VALUES('bcb',1,1,'PRONTA',(now() AT TIME ZONE 'America/Sao_Paulo')::date)"
            )
        )
        quantidade = conexao.scalar(text("SELECT count(*) FROM core.fato_serie"))
        exigir(quantidade == 1_000_000, "Seed não produziu exatamente um milhão.")
    with motor.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text("VACUUM ANALYZE core.fato_serie"))
        conexao.execute(text("ANALYZE core.dim_serie"))
        tamanho = conexao.scalar(text("SELECT pg_database_size(current_database())"))
    return {
        "simulacao": True,
        "semente": SEMENTE,
        "series": SERIES_SINTETICAS,
        "dias_por_serie": DIAS_POR_SERIE,
        "observacoes": quantidade,
        "inicio": "2020-01-01",
        "fim": "2026-11-04",
        "banco_bytes": tamanho,
        "formula": "((codigo*17+dia*31+20261119)%100000)/100; numeric",
        "indices": "Somente os definidos nas migrações, sem ajuste para o ensaio.",
    }


def executar_http(url_api: str, segredo: str, pasta: Path, cache_url: str | None) -> dict:
    porta = porta_livre()
    ambiente = os.environ.copy()
    ambiente.update(
        URL_BANCO_API=url_api,
        SEGREDO_CURSOR=segredo,
        LIMITE_REQUISICOES_MINUTO="100000",
        CACHE_HABILITADO=str(bool(cache_url)).lower(),
    )
    ambiente.pop("URL_REDIS", None)
    if cache_url:
        ambiente["URL_REDIS"] = cache_url
    nome = "com_cache" if cache_url else "sem_cache"
    with (pasta / (nome + ".log")).open("x", encoding="utf-8") as registro:
        processo = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--servidor", str(porta)],
            cwd=RAIZ,
            env=ambiente,
            stdout=registro,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with httpx.Client(trust_env=False, timeout=5) as cliente:
                limite = time.monotonic() + 40
                while True:
                    try:
                        if cliente.get(f"http://127.0.0.1:{porta}/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    exigir(
                        processo.poll() is None and time.monotonic() < limite,
                        "API exclusiva do benchmark não iniciou.",
                    )
                    time.sleep(0.2)
            contadores = {}

            def observar(fase):
                with httpx.Client(trust_env=False, timeout=5) as cliente:
                    resposta = cliente.get(f"http://127.0.0.1:{porta}/benchmark/contadores")
                    resposta.raise_for_status()
                    contadores[fase] = resposta.json()

            resultado = medir_http(porta, observar_fase=observar)
            resultado["cache_na_medicao"] = {
                nome: contadores["concluida"][nome] - contadores["medicao"][nome]
                for nome in ("acertos", "calculos")
            }
            exigir(
                sum(resultado["cache_na_medicao"].values()) == resultado["total"]["requisicoes"],
                "Contagem das respostas da fase medida diverge do total HTTP.",
            )
            if cache_url:
                exigir(
                    resultado["cache_na_medicao"]["acertos"] > 0,
                    "Nenhuma resposta cacheada comprovada na fase medida.",
                )
            resultado["protocolo"]["cache_aplicacao"] = bool(cache_url)
            resultado["protocolo"]["meta_p95_ms"] = 250 if cache_url else 500
            for resumo in [resultado["total"], *resultado["por_cenario"].values()]:
                resumo["meta_local_atendida"] = avaliar_meta(resumo, bool(cache_url))
            for cenario in resultado["cenarios"]:
                cenario["nome"] = cenario["nome"].replace("selic_", "simulada_")
            resultado["por_cenario"] = {
                nome.replace("selic_", "simulada_"): resumo
                for nome, resumo in resultado["por_cenario"].items()
            }
            for amostra in resultado["amostras"]:
                amostra["cenario"] = amostra["cenario"].replace("selic_", "simulada_")
            return resultado
        finally:
            processo.terminate()
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)


def executar() -> int:
    instante = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    sufixo = secrets.token_hex(3)
    destino = "etl_benchmark_m2_" + instante + "_" + sufixo
    conferir_destino(destino)
    pasta = RAIZ / ".cache" / destino
    pasta.mkdir(parents=True)
    segredos = dotenv_values(RAIZ / ".env.banco", interpolate=False)
    docker = shutil.which("docker") or "C:/Program Files/Docker/Docker/resources/bin/docker.exe"
    nome_redis = "etl-benchmark-redis-" + instante.replace("_", "-") + "-" + sufixo
    motores = []
    redis_tentado = False
    cliente_redis = None
    relatorio = {
        "instante_utc": instante,
        "destino": destino,
        "simulacao": True,
        "situacao": "EM_EXECUCAO",
    }

    def motor_local(banco, papel):
        exigir(banco in {"etl", destino}, "Banco fora do escopo do ensaio.")
        chave = {"administrador": "ADMIN", "migracoes": "MIGRACOES", "api_leitura": "API"}[papel]
        url = URL.create(
            "postgresql+psycopg",
            username=papel,
            password=segredos["SENHA_BANCO_" + chave],
            host="127.0.0.1",
            port=55432,
            database=banco,
        )
        motor = criar_motor(SecretStr(url.render_as_string(hide_password=False)))
        motores.append(motor)
        return motor

    try:
        origem = motor_local("etl", "administrador")
        antes_origem = retratar(origem)
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
            conexao.execute(
                sql.SQL("CREATE DATABASE {} OWNER migracoes TEMPLATE template0").format(
                    sql.Identifier(destino)
                )
            )
            conexao.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(destino))
            )
            conexao.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO migracoes,api_leitura,publicador").format(
                    sql.Identifier(destino)
                )
            )
        sintetico = motor_local(destino, "migracoes")
        print("Preparando um milhão de observações SIMULADAS.", flush=True)
        relatorio["dataset"] = preparar_sintetico(sintetico, destino)
        with sintetico.begin() as conexao:
            conexao.execute(text("SET TRANSACTION READ ONLY"))
            relatorio["postgresql"] = conexao.scalar(text("SELECT version()"))
            relatorio["alembic"] = conexao.scalar(text("SELECT version_num FROM alembic_version"))
            relatorio["indices"] = [
                dict(linha)
                for linha in conexao.execute(
                    text(
                        "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes "
                        "WHERE schemaname IN ('core','ops','mart') ORDER BY 1,2,3"
                    )
                ).mappings()
            ]
        arquivos_codigo = [
            Path(__file__).resolve(),
            RAIZ / "scripts/medir_desempenho_local.py",
            RAIZ / "pyproject.toml",
            RAIZ / "uv.lock",
        ]
        arquivos_codigo.extend((RAIZ / "src").rglob("*.py"))
        arquivos_codigo.extend((RAIZ / "migracoes").rglob("*.py"))
        arquivos_codigo.extend((RAIZ / "migracoes").rglob("*.sql"))
        relatorio["sha256_fontes"] = {
            arquivo.relative_to(RAIZ).as_posix(): hashlib.sha256(arquivo.read_bytes()).hexdigest()
            for arquivo in sorted(arquivos_codigo)
        }
        antes = retratar_sintetico(sintetico)
        api = motor_local(destino, "api_leitura")
        segredo = secrets.token_hex(48)
        url_api = api.url.render_as_string(hide_password=False)
        print("Medição SEM cache: aquecimento 30s e medição 60s.", flush=True)
        relatorio["sem_cache"] = executar_http(url_api, segredo, pasta, None)
        senha_redis = secrets.token_hex(32)
        configuracao_redis = pasta / "redis.conf"
        configuracao_redis.write_text(
            "bind 0.0.0.0\nprotected-mode yes\nrequirepass "
            + senha_redis
            + '\nmaxmemory 64mb\nmaxmemory-policy allkeys-lru\nsave ""\n',
            encoding="utf-8",
        )
        porta = porta_livre()
        redis_tentado = True
        resultado = subprocess.run(
            [
                docker,
                "run",
                "-d",
                "--name",
                nome_redis,
                "--label",
                "pipeline_etl.benchmark=" + destino,
                "--publish",
                f"127.0.0.1:{porta}:6379",
                "--mount",
                f"type=bind,source={configuracao_redis},target=/etc/redis.conf,readonly",
                "redis:7.4.12-alpine3.22",
                "redis-server",
                "/etc/redis.conf",
            ],
            capture_output=True,
            check=False,
            timeout=60,
        )
        exigir(resultado.returncode == 0, "Redis exclusivo não iniciou.")
        cliente_redis = redis.Redis(
            host="127.0.0.1",
            port=porta,
            password=senha_redis,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        limite = time.monotonic() + 20
        while True:
            try:
                if cliente_redis.ping():
                    break
            except redis.RedisError:
                pass
            exigir(time.monotonic() < limite, "Redis exclusivo indisponível.")
            time.sleep(0.2)
        exigir(cliente_redis.dbsize() == 0, "Cache do ensaio deve iniciar vazio.")
        estatisticas_antes = cliente_redis.info("stats")
        print("Medição COM cache exclusivo: aquecimento 30s e medição 60s.", flush=True)
        relatorio["com_cache"] = executar_http(
            url_api, segredo, pasta, f"redis://:{senha_redis}@127.0.0.1:{porta}/0"
        )
        estatisticas = cliente_redis.info("stats")
        relatorio["redis"] = {
            "chaves": cliente_redis.dbsize(),
            "acertos": estatisticas["keyspace_hits"] - estatisticas_antes["keyspace_hits"],
            "ausencias": estatisticas["keyspace_misses"] - estatisticas_antes["keyspace_misses"],
            "expulsas": estatisticas["evicted_keys"],
            "exclusivo": True,
            "versao": cliente_redis.info("server")["redis_version"],
        }
        exigir(relatorio["redis"]["acertos"] > 0, "Não foi comprovado uso efetivo do cache.")
        relatorio["sql"] = comparar_planos(api)
        exigir(retratar_sintetico(sintetico) == antes, "Dataset mudou durante o benchmark.")
        exigir(retratar(origem) == antes_origem, "Origem mudou; benchmark não homologado.")
        relatorio.update(
            situacao="SUCESSO",
            dados_preservados=True,
            origem_preservada=True,
            retrato_sintetico=antes,
            python=sys.version,
            versoes={
                nome: version(nome)
                for nome in ("fastapi", "uvicorn", "sqlalchemy", "psycopg", "httpx", "redis")
            },
        )
        relatorio["docker"] = subprocess.run(
            [
                docker,
                "info",
                "--format",
                "{{json .NCPU}} {{json .MemTotal}} {{json .ServerVersion}}",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=15,
        ).stdout.strip()
        ambiente = RAIZ / ".cache/ambiente_desempenho.json"
        relatorio["ambiente_windows_registrado"] = (
            json.loads(ambiente.read_text(encoding="utf-8-sig")) if ambiente.is_file() else None
        )
    except Exception as erro:
        relatorio.update(situacao="FALHA", tipo_erro=type(erro).__name__)
        raise
    finally:
        if cliente_redis is not None:
            try:
                cliente_redis.close()
            except Exception:
                relatorio["fechamento_cliente_redis"] = False
        if redis_tentado:
            relatorio["limpeza_redis"] = limpar_redis_exclusivo(docker, destino)
            if not relatorio["limpeza_redis"]["confirmada"]:
                relatorio["situacao"] = "FALHA_LIMPEZA"
        for motor in motores:
            try:
                motor.dispose()
            except Exception:
                relatorio["descarte_motores"] = False
        relatorio["finalizado_em"] = datetime.now(UTC).isoformat()
        caminho = RAIZ / "dados/descoberta" / ("desempenho_m2_" + instante + "_" + sufixo + ".json")
        caminho.parent.mkdir(parents=True, exist_ok=True)
        with caminho.open("x", encoding="utf-8") as arquivo:
            json.dump(relatorio, arquivo, ensure_ascii=False, default=str, indent=2)
        print(
            json.dumps(
                {"situacao": relatorio["situacao"], "relatorio": str(caminho.relative_to(RAIZ))}
            )
        )
    return 0 if relatorio["situacao"] == "SUCESSO" else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--servidor":
        servir_ensaio(int(sys.argv[2]))
    else:
        raise SystemExit(executar())
