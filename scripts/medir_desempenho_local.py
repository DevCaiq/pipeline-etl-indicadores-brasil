"""Benchmark manual M1: HTTP loopback e planos SQL sobre o dataset real, sem ETL."""

import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from statistics import median

import httpx
from sqlalchemy import text

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor

RAIZ = Path(__file__).resolve().parents[1]
AQUECIMENTO_SEGUNDOS = 30
MEDICAO_SEGUNDOS = 60
CONCORRENCIA = 10
LIMITE_PAGINA = 100


def exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise RuntimeError(mensagem)


def resumir(amostras: list[dict], segundos: float) -> dict:
    """Percentis por posto mais próximo, incluindo respostas de erro na latência."""
    exigir(bool(amostras) and segundos > 0, "Medição sem amostras ou duração inválida.")
    tempos = sorted(item["milissegundos"] for item in amostras)
    estados = Counter(str(item["status"]) for item in amostras)
    erros_5xx = sum(500 <= item["status"] < 600 for item in amostras)
    return {
        "requisicoes": len(amostras),
        "segundos": segundos,
        "requisicoes_por_segundo": len(amostras) / segundos,
        "p50_ms": tempos[math.ceil(len(tempos) * 0.50) - 1],
        "p95_ms": tempos[math.ceil(len(tempos) * 0.95) - 1],
        "p99_ms": tempos[math.ceil(len(tempos) * 0.99) - 1],
        "estados_http": dict(estados),
        "erros_5xx": erros_5xx,
        "percentual_5xx": erros_5xx * 100 / len(amostras),
        "erros_transporte": sum(item["status"] == 0 for item in amostras),
        "erros_validacao": sum(item.get("erro_validacao", False) for item in amostras),
        "meta_local_atendida": tempos[math.ceil(len(tempos) * 0.95) - 1] <= 500
        and erros_5xx * 100 / len(amostras) < 1
        and all(item["status"] == 200 and not item.get("erro_validacao") for item in amostras),
    }


def retratar(motor) -> dict:
    """Checksum das tabelas/MVs BCB e versão pela view sanitizada permitida."""
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
        preparador = conexao.dialect.identifier_preparer
        for esquema, nome in relacoes:
            identificador = preparador.quote(esquema) + "." + preparador.quote(nome)
            linhas = (
                conexao.execute(text(f"SELECT to_jsonb(t)::text FROM {identificador} t ORDER BY 1"))
                .scalars()
                .all()
            )
            resultado[f"{esquema}.{nome}"] = {
                "linhas": len(linhas),
                "sha256": hashlib.sha256(json.dumps(linhas).encode()).hexdigest(),
            }
        resultado["esquema"] = conexao.scalar(text("SELECT version_num FROM ops.v_esquema_api"))
    return resultado


def comparar_planos(motor) -> list[dict]:
    resultados = []
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        datas = (
            conexao.execute(
                text(
                    "SELECT data FROM core.fato_serie WHERE codigo_sgs=432 "
                    "AND data>='2020-01-01' ORDER BY data"
                )
            )
            .scalars()
            .all()
        )
        exigir(len(datas) > 200, "Selic insuficiente para comparar três posições.")
        posicoes = {
            "inicio": 0,
            "meio": (len(datas) // 2 // 100) * 100,
            "fim": ((len(datas) - 1) // 100) * 100,
        }
        base = (
            "SELECT data,valor FROM core.fato_serie WHERE codigo_sgs=:codigo "
            "AND data>=:de AND data<=:ate "
        )
        consultas = {
            "keyset": base + "AND (CAST(:depois AS date) IS NULL OR data>:depois) "
            "ORDER BY data LIMIT :quantidade",
            "offset": base + "ORDER BY data LIMIT :quantidade OFFSET :deslocamento",
        }
        for posicao, deslocamento in posicoes.items():
            parametros = {
                "codigo": 432,
                "de": date(2020, 1, 1),
                "ate": datas[-1],
                "depois": datas[deslocamento - 1] if deslocamento else None,
                "quantidade": 101,
                "deslocamento": deslocamento,
            }
            linhas = [
                conexao.execute(text(consulta), parametros).all() for consulta in consultas.values()
            ]
            exigir(linhas[0] == linhas[1], "Keyset/OFFSET divergiram nas linhas.")
            for estrategia, consulta in consultas.items():
                planos = [
                    conexao.scalar(
                        text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + consulta), parametros
                    )
                    for _ in range(10)
                ]
                tempos = [plano[0]["Execution Time"] for plano in planos]
                resultados.append(
                    {
                        "posicao": posicao,
                        "deslocamento": deslocamento,
                        "estrategia": estrategia,
                        "linhas": len(linhas[0]),
                        "execucao_mediana_ms": median(tempos),
                        "planos": planos,
                    }
                )
    return resultados


def medir_http(porta: int, observar_fase=None) -> dict:
    base = f"http://127.0.0.1:{porta}"
    with httpx.Client(base_url=base, trust_env=False, timeout=10) as cliente:
        paginas = []
        parametros = {"limite": 100}
        while True:
            resposta = cliente.get("/api/v1/series/432/observacoes", params=parametros)
            exigir(resposta.status_code == 200, "Preparação da paginação falhou.")
            corpo = resposta.json()
            paginas.append((dict(parametros), len(corpo["data"])))
            cursor = corpo["pagina"]["proximo_cursor"]
            if cursor is None:
                break
            parametros = {"limite": 100, "cursor": cursor}
        cenarios = [
            (nome, "/api/v1/series/432/observacoes", paginas[indice][0], paginas[indice][1])
            for nome, indice in [
                ("selic_inicio", 0),
                ("selic_meio", (len(paginas) - 1) // 2),
                ("selic_fim", len(paginas) - 1),
            ]
        ]
        resposta = cliente.get("/api/v1/series/432/agregados", params={"limite": 100})
        exigir(resposta.status_code == 200, "Preparação gold falhou.")
        cenarios.append(
            (
                "selic_mensal",
                "/api/v1/series/432/agregados",
                {"limite": 100},
                len(resposta.json()["data"]),
            )
        )
    barreira = threading.Barrier(CONCORRENCIA + 1, timeout=30)
    iniciar = threading.Event()
    marcos = {}

    def cliente_concorrente(indice: int):
        medidas = []
        aquecimento = []
        with httpx.Client(base_url=base, trust_env=False, timeout=10) as cliente:
            for fase in ("aquecimento", "medicao"):
                barreira.wait()
                iniciar.wait()
                destino = aquecimento if fase == "aquecimento" else medidas
                while time.perf_counter() < marcos[fase]:
                    nome, rota, parametros, quantidade = cenarios[indice % len(cenarios)]
                    indice += 1
                    comeco = time.perf_counter()
                    estado = 0
                    erro_validacao = False
                    try:
                        resposta = cliente.get(rota, params=parametros)
                        estado = resposta.status_code
                        if estado == 200:
                            corpo = resposta.json()
                            erro_validacao = len(corpo.get("data", [])) != quantidade
                    except (ValueError, KeyError):
                        erro_validacao = True
                    except httpx.HTTPError:
                        pass
                    destino.append(
                        {
                            "cenario": nome,
                            "status": estado,
                            "milissegundos": (time.perf_counter() - comeco) * 1000,
                            "erro_validacao": erro_validacao,
                        }
                    )
        return aquecimento, medidas

    resultados = []
    with ThreadPoolExecutor(max_workers=CONCORRENCIA) as executor:
        tarefas = [executor.submit(cliente_concorrente, indice) for indice in range(CONCORRENCIA)]
        duracoes = {}
        for fase, segundos in (
            ("aquecimento", AQUECIMENTO_SEGUNDOS),
            ("medicao", MEDICAO_SEGUNDOS),
        ):
            iniciar.clear()
            barreira.wait()
            if observar_fase is not None:
                observar_fase(fase)
            comeco = time.perf_counter()
            marcos[fase] = comeco + segundos
            iniciar.set()
            print(f"Fase {fase}: {segundos}s, {CONCORRENCIA} clientes.", flush=True)
            # Aguarda o prazo sem bloquear comunicação do processo com a ferramenta.
            threading.Event().wait(segundos)
            duracoes[fase] = time.perf_counter() - comeco
        resultados = [tarefa.result() for tarefa in tarefas]
        duracoes["medicao"] = time.perf_counter() - comeco
        if observar_fase is not None:
            observar_fase("concluida")
    aquecimento = [item for lote, _ in resultados for item in lote]
    medidas = [item for _, lote in resultados for item in lote]
    return {
        "protocolo": {
            "aquecimento_s": 30,
            "medicao_s": 60,
            "concorrencia": 10,
            "pagina_solicitada": 100,
            "workers": 1,
            "cache_aplicacao": False,
            "limite_minuto_processo_proprio": 100000,
            "carga": "concorrencia_fechada",
        },
        "cenarios": [
            {"nome": nome, "rota": rota, "itens": quantidade}
            for nome, rota, _, quantidade in cenarios
        ],
        "aquecimento": resumir(aquecimento, duracoes["aquecimento"]),
        "total": resumir(medidas, duracoes["medicao"]),
        "por_cenario": {
            nome: resumir(
                [item for item in medidas if item["cenario"] == nome], duracoes["medicao"]
            )
            for nome, _, _, _ in cenarios
        },
        "amostras": medidas,
    }


def executar() -> int:
    motor = criar_motor(resolver_url_processamento(None, RAIZ / ".env.banco"))
    instante = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    caminho = RAIZ / "dados/descoberta" / ("desempenho_" + instante + ".json")
    processo = None
    try:
        antes = retratar(motor)
        with motor.begin() as conexao:
            conexao.execute(text("SET TRANSACTION READ ONLY"))
            banco = conexao.scalar(text("SELECT version()"))
        with socket.socket() as reserva:
            reserva.bind(("127.0.0.1", 0))
            porta = reserva.getsockname()[1]
        ambiente = os.environ.copy()
        for nome in ("URL_BANCO_API", "SEGREDO_CURSOR"):
            ambiente.pop(nome, None)
        ambiente["LIMITE_REQUISICOES_MINUTO"] = "100000"
        with (RAIZ / ".cache" / ("api_desempenho_" + instante + ".log")).open("x") as registro:
            processo = subprocess.Popen(
                [sys.executable, "-m", "pipeline_etl", "servir", "--porta", str(porta)],
                cwd=RAIZ,
                env=ambiente,
                stdout=registro,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            with httpx.Client(trust_env=False, timeout=2) as cliente:
                limite = time.monotonic() + 30
                while True:
                    try:
                        if cliente.get(f"http://127.0.0.1:{porta}/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    exigir(
                        processo.poll() is None and time.monotonic() < limite,
                        "Servidor do ensaio não iniciou.",
                    )
                    time.sleep(0.2)
            http = medir_http(porta)
        planos = comparar_planos(motor)
        depois = retratar(motor)
        exigir(antes == depois, "Base mudou durante o ensaio; resultado não homologado.")
        relatorio = {
            "instante_utc": instante,
            "banco": banco,
            "python": sys.version,
            "versoes": {
                nome: version(nome)
                for nome in ["fastapi", "uvicorn", "sqlalchemy", "psycopg", "httpx"]
            },
            "retrato_preservado": antes,
            "http": http,
            "sql": planos,
            "dados_preservados": True,
            "ambiente": json.loads(
                (RAIZ / ".cache/ambiente_desempenho.json").read_text(encoding="utf-8-sig")
            )
            if (RAIZ / ".cache/ambiente_desempenho.json").is_file()
            else None,
            "pool_sqlalchemy": {
                "tamanho": motor.pool.size(),
                "maximo_excedente": getattr(motor.pool, "_max_overflow", None),
            },
        }
        with caminho.open("x", encoding="utf-8") as arquivo:
            json.dump(relatorio, arquivo, default=str, ensure_ascii=False, indent=2)
        print(json.dumps({"relatorio": str(caminho), "resumo": http["total"]}, ensure_ascii=False))
        return 0
    finally:
        if processo is not None:
            processo.terminate()
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)
        motor.dispose()


if __name__ == "__main__":
    raise SystemExit(executar())
