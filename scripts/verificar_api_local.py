"""Verificação manual com HTTP local; encerra somente o servidor que iniciou."""

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from pathlib import Path

import httpx
from dotenv import dotenv_values
from pydantic import SecretStr
from sqlalchemy import URL, text

from pipeline_etl.banco.credenciais import resolver_url_processamento
from pipeline_etl.banco.sessoes import criar_motor


def executar() -> int:
    if not __debug__:
        raise RuntimeError("Verificador exige Python sem otimizacao para preservar validacoes.")
    raiz = Path(__file__).resolve().parents[1]
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("--banco-ensaio", help="Banco exclusivo criado pelo ensaio local.")
    opcoes = argumentos.parse_args()
    banco_ensaio = opcoes.banco_ensaio
    endereco_api = None
    if banco_ensaio:
        if not re.fullmatch(r"etl_ensaio_(rest|replay)_\d{8}_\d{6}_[0-9a-f]{6}", banco_ensaio):
            argumentos.error("Nome fora do padrão dos bancos exclusivos de ensaio.")
        segredos = dotenv_values(raiz / ".env.banco", interpolate=False)

        def endereco(papel: str) -> SecretStr:
            url = URL.create(
                "postgresql+psycopg",
                username=papel,
                password=segredos[
                    "SENHA_BANCO_API" if papel == "api_leitura" else "SENHA_BANCO_PROCESSAMENTO"
                ],
                host="127.0.0.1",
                port=55432,
                database=banco_ensaio,
            )
            return SecretStr(url.render_as_string(hide_password=False))

        motor = criar_motor(endereco("processamento"))
        endereco_api = endereco("api_leitura")
    else:
        motor = criar_motor(resolver_url_processamento(None, raiz / ".env.banco"))

    def retrato():
        with motor.begin() as conexao:
            conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
            fatos = conexao.execute(
                text(
                    "SELECT codigo_sgs,data,valor,lote_id,alterado_em,origem_coletada_em "
                    "FROM core.fato_serie ORDER BY codigo_sgs,data"
                )
            ).all()
            estado = conexao.execute(text("SELECT * FROM ops.publicacao ORDER BY dominio")).all()
            auditoria = {}
            for nome in ("execucao", "lote", "preparacao_bcb"):
                linhas = (
                    conexao.execute(text(f"SELECT to_jsonb(t)::text FROM ops.{nome} t ORDER BY 1"))
                    .scalars()
                    .all()
                )
                auditoria[nome] = hashlib.sha256(json.dumps(linhas).encode()).hexdigest()
            visoes = {
                nome: [dict(linha) for linha in conexao.execute(text(consulta)).mappings()]
                for nome, consulta in {
                    "mes": "SELECT * FROM mart.mv_serie_mensal ORDER BY codigo_sgs,periodo",
                    "ano": "SELECT * FROM mart.mv_serie_anual ORDER BY codigo_sgs,periodo",
                    "ipca12m": "SELECT * FROM mart.mv_ipca_12m ORDER BY codigo_sgs,periodo",
                }.items()
            }
            return fatos, estado, auditoria, visoes

    antes = retrato()
    parametros_recorte = {"de": "2020-01-02", "ate": "2020-01-06"}
    esperadas = sum(
        linha[0] == 432 and date(2020, 1, 2) <= linha[1] <= date(2020, 1, 6) for linha in antes[0]
    )
    with socket.socket() as reserva:
        reserva.bind(("127.0.0.1", 0))
        porta = reserva.getsockname()[1]
    ambiente = os.environ.copy()
    for chave in ["URL_BANCO_API", "SEGREDO_CURSOR"]:
        ambiente.pop(chave, None)
    if endereco_api:
        ambiente["URL_BANCO_API"] = endereco_api.get_secret_value()
    ambiente["LIMITE_REQUISICOES_MINUTO"] = "100"
    (raiz / ".cache").mkdir(exist_ok=True)
    caminho_log = (
        raiz / ".cache" / ("api_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f") + ".log")
    )
    resultados = {}
    with caminho_log.open("x", encoding="utf-8") as registro:
        processo = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "pipeline_etl",
                "servir",
                "--configuracao-api",
                str(raiz / ".env.api"),
                "--porta",
                str(porta),
            ],
            cwd=raiz,
            env=ambiente,
            stdout=registro,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{porta}", timeout=5, trust_env=False
            ) as cliente:
                limite = time.monotonic() + 30
                while True:
                    try:
                        if cliente.get("/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if processo.poll() is not None or time.monotonic() > limite:
                        raise RuntimeError("API não iniciou; confira o log local de verificação.")
                    time.sleep(0.2)
                rotas = [
                    "/health",
                    "/ready",
                    "/api/v1/series",
                    "/api/v1/series/432",
                    "/api/v1/series/432/observacoes",
                    "/api/v1/series/432/agregados",
                    "/api/v1/series/432/agregados?granularidade=ano",
                    "/api/v1/indicadores/ipca-12m",
                    "/api/v1/pipeline/execucoes?limite=2",
                    "/api/v1/pipeline/frescor",
                    "/docs",
                    "/openapi.json",
                ]
                for rota in rotas:
                    resposta = cliente.get(rota)
                    assert resposta.status_code == 200, (rota, resposta.status_code)
                    assert resposta.headers.get("X-Request-ID")
                    resultados[rota] = resposta.status_code
                    if rota == "/api/v1/pipeline/frescor":
                        resultados["frescor"] = resposta.json()["data"]
                resultados["esquema"] = cliente.get("/ready").json()["esquema"]
                observacoes = cliente.get(
                    "/api/v1/series/432/observacoes", params=parametros_recorte
                )
                assert len(observacoes.json()["data"]) == esperadas
                assert (
                    cliente.get(
                        "/api/v1/series/432/observacoes",
                        headers={"If-None-Match": observacoes.headers["ETag"]},
                        params=parametros_recorte,
                    ).status_code
                    == 304
                )
                pagina = cliente.get(
                    "/api/v1/series/432/observacoes", params={**parametros_recorte, "limite": 2}
                ).json()
                datas = [item["data"] for item in pagina["data"]]
                while pagina["pagina"]["tem_mais"]:
                    pagina = cliente.get(
                        "/api/v1/series/432/observacoes",
                        params={
                            **parametros_recorte,
                            "limite": 2,
                            "cursor": pagina["pagina"]["proximo_cursor"],
                        },
                    ).json()
                    datas.extend(item["data"] for item in pagina["data"])
                assert len(datas) == len(set(datas)) == esperadas and datas == sorted(datas)
                quantidades_publicas = {}
                for codigo in (432, 433, 1):
                    with localcontext() as contexto:
                        contexto.prec = 500
                        esperadas_publicas = [
                            {
                                "data": str(linha[1]),
                                "valor": format(
                                    linha[2].quantize(
                                        Decimal("0.000001"), rounding=ROUND_HALF_EVEN
                                    ),
                                    "f",
                                ),
                            }
                            for linha in antes[0]
                            if linha[0] == codigo and linha[1] >= date(2020, 1, 1)
                        ]
                    recebidas = []
                    parametros = {"limite": 1000}
                    while True:
                        resposta = cliente.get(
                            f"/api/v1/series/{codigo}/observacoes", params=parametros
                        )
                        assert resposta.status_code == 200
                        conteudo = resposta.json()
                        recebidas.extend(conteudo["data"])
                        assert conteudo["meta"]["cobertura"]["observacoes"] == len(
                            esperadas_publicas
                        )
                        if not conteudo["pagina"]["tem_mais"]:
                            break
                        parametros = {
                            "limite": 1000,
                            "cursor": conteudo["pagina"]["proximo_cursor"],
                        }
                    assert recebidas == esperadas_publicas, "Dados públicos divergentes do core."
                    quantidades_publicas[str(codigo)] = len(recebidas)
                resultados["observacoes_publicas_verificadas"] = quantidades_publicas
                agregados_verificados = 0
                campos = [
                    "periodo",
                    "unidade",
                    "observacoes",
                    "media",
                    "minimo",
                    "maximo",
                    "ultimo",
                    "variacao",
                    "completo",
                    "parcial",
                    "motivo",
                    "data_referencia",
                ]
                for tipo, linhas in antes[3].items():
                    for codigo in (433,) if tipo == "ipca12m" else (432, 433, 1):
                        rota = (
                            "/api/v1/indicadores/ipca-12m"
                            if tipo == "ipca12m"
                            else f"/api/v1/series/{codigo}/agregados"
                        )
                        parametros = {"limite": 1000}
                        if tipo != "ipca12m":
                            parametros["granularidade"] = tipo
                        resposta = cliente.get(rota, params=parametros)
                        assert resposta.status_code == 200
                        esperadas_gold = []
                        for linha in linhas:
                            if linha["codigo_sgs"] != codigo:
                                continue
                            item = {}
                            for campo in campos:
                                valor = linha.get(campo)
                                if isinstance(valor, Decimal):
                                    with localcontext() as contexto:
                                        contexto.prec = 500
                                        valor = format(
                                            valor.quantize(
                                                Decimal("0.000001"), rounding=ROUND_HALF_EVEN
                                            ),
                                            "f",
                                        )
                                elif isinstance(valor, date):
                                    valor = str(valor)
                                item[campo] = valor
                            esperadas_gold.append(item)
                        assert resposta.json()["data"] == esperadas_gold, (
                            "Gold HTTP divergente da gold SQL."
                        )
                        agregados_verificados += len(esperadas_gold)
                resultados["agregados_http_verificados"] = agregados_verificados
                invalida = cliente.get("/api/v1/series/432/observacoes?de=2019-01-01")
                assert invalida.status_code == 422
                assert invalida.json()["erro"]["requisicao_id"] == invalida.headers["X-Request-ID"]
                assert cliente.post("/api/v1/series").status_code == 405
                historico = cliente.get("/api/v1/pipeline/execucoes?limite=2").text
                assert "parametros" not in historico and "://" not in historico
                respostas = [
                    cliente.get(
                        "/api/rota-inexistente", headers={"X-Forwarded-For": f"198.51.100.{indice}"}
                    ).status_code
                    for indice in range(101)
                ]
                assert 429 in respostas, (
                    "X-Forwarded-For não pode contornar limite por conexão real."
                )
                assert (
                    cliente.get("/health").status_code == cliente.get("/ready").status_code == 200
                )
                resultados.update(
                    {
                        "etag_304": True,
                        "paginacao_sem_duplicatas": True,
                        "limite_sem_confiar_proxy": True,
                    }
                )
        finally:
            processo.terminate()
            try:
                processo.wait(timeout=10)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=5)
    depois = retrato()
    assert antes == depois, "A API não pode alterar fatos, gerações ou auditoria."
    resultados.update(
        {"fatos_preservados": len(depois[0]), "servidor_encerrado": processo.poll() is not None}
    )
    nome_relatorio = "sondagem_api_" + banco_ensaio if banco_ensaio else "sondagem_api_bcb"
    resultados["banco"] = banco_ensaio or "etl"
    (raiz / "dados/descoberta" / (nome_relatorio + ".json")).write_text(
        json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    motor.dispose()
    print(
        "HTTP local verificado:12 consultas básicas, paginação, ETag304, rate limit e probes; "
        "dados preservados; servidor próprio encerrado."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(executar())
