"""Aplicação HTTP somente leitura e contratos M1."""

import hashlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from prometheus_client import CONTENT_TYPE_LATEST
from pydantic import BaseModel
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, Response

from pipeline_etl.api.cache import CacheLeitura, criar_chave_cache
from pipeline_etl.api.erros import CorpoErro, DetalheErro, ErroAPI, RespostaErro
from pipeline_etl.api.esquemas import (
    Agregado,
    EstadoServico,
    Execucao,
    Frescor,
    Observacao,
    RespostaDados,
    RespostaPaginada,
    Serie,
)
from pipeline_etl.api.filtros import FiltrosAgregados, FiltrosExecucoes, FiltrosPeriodo, hoje_brasil
from pipeline_etl.api.limites import LimitadorLocal
from pipeline_etl.api.metricas import EstatisticasPipeline, MetricasAPI, MiddlewareMetricas
from pipeline_etl.api.redis_local import criar_cliente_redis
from pipeline_etl.api.repositorio import ESQUEMA_ESPERADO, RepositorioLeitura
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao


def erro_publico(
    requisicao: Request,
    status: int,
    codigo: str,
    mensagem: str,
    detalhes: list[DetalheErro] | None = None,
) -> JSONResponse:
    erro = RespostaErro(
        erro=CorpoErro(
            codigo=codigo,
            mensagem=mensagem,
            requisicao_id=requisicao.state.requisicao_id,
            detalhes=detalhes or [],
        )
    )
    return JSONResponse(
        erro.model_dump(mode="json"), status_code=status, headers={"Cache-Control": "no-store"}
    )


def responder(
    requisicao: Request, modelo: BaseModel | bytes, *, cacheavel: bool = True
) -> Response:
    corpo = modelo if isinstance(modelo, bytes) else modelo.model_dump_json().encode()
    if not cacheavel:
        return Response(corpo, media_type="application/json", headers={"Cache-Control": "no-store"})
    etag = '"' + hashlib.sha256(corpo).hexdigest() + '"'
    cabecalhos = {"ETag": etag, "Cache-Control": "public, max-age=0, must-revalidate"}
    comparacoes = {
        item.strip().removeprefix("W/")
        for item in requisicao.headers.get("If-None-Match", "").split(",")
    }
    if etag in comparacoes or "*" in comparacoes:
        return Response(status_code=304, headers=cabecalhos)
    return Response(corpo, media_type="application/json", headers=cabecalhos)


def responder_sem_condicional(requisicao: Request, modelo: BaseModel) -> Response:
    """Serializa a representação para armazenamento antes da negociação HTTP."""
    return responder(requisicao, modelo, cacheavel=False)


def responder_cache(
    requisicao: Request,
    estado: dict[str, Any],
    camada: str,
    calcular: Callable[[], Response],
    *,
    dominio: str = "bcb",
    parametros: dict[str, object] | None = None,
    validade: int = 300,
) -> Response:
    """Reutiliza bytes após a leitura da autoridade SQL no snapshot vigente."""
    identidade = {
        "versao_core": estado["versao_core"],
        "versao_gold": estado["versao_gold"],
        "situacao": estado["situacao"],
        "data_publicacao": str(estado["data_publicacao"]),
        "hoje": hoje_brasil().isoformat(),
    }
    chave = criar_chave_cache(
        dominio,
        camada,
        identidade,
        identidade["data_publicacao"],
        requisicao.url.path,
        parametros or dict(requisicao.query_params),
    )
    cache: CacheLeitura = requisicao.app.state.cache_leitura
    corpo = cache.obter_ou_calcular(chave, lambda: bytes(calcular().body), validade)
    return responder(requisicao, corpo)


def documentar(exemplo: dict[str, Any]) -> dict[int | str, dict[str, Any]]:
    from copy import deepcopy

    codigos = {
        404: "RECURSO_NAO_ENCONTRADO",
        409: "CURSOR_EXPIRADO",
        422: "PARAMETRO_INVALIDO",
        429: "LIMITE_EXCEDIDO",
        500: "ERRO_INTERNO",
        503: "BANCO_INDISPONIVEL",
    }
    respostas: dict[int | str, dict[str, Any]] = {}
    for status, codigo in codigos.items():
        erro = {
            "erro": {
                "codigo": codigo,
                "mensagem": "Consulta não concluída.",
                "requisicao_id": "exemplo",
                "detalhes": [],
            }
        }
        respostas[status] = {
            "model": RespostaErro,
            "description": "Erro sanitizado.",
            "content": {"application/json": {"example": erro}},
        }
    exemplos = {"sucesso": {"value": exemplo}}
    if "data" in exemplo:
        vazio = deepcopy(exemplo)
        if isinstance(vazio["data"], list):
            vazio["data"] = []
        else:
            vazio["data"]["cobertura"] = {
                "inicio": None,
                "fim": None,
                "observacoes": 0,
                "completa": None,
            }
        vazio["meta"]["versao_dados"] = 0
        vazio["meta"]["versao_core"] = 0
        vazio["meta"]["versao_gold"] = 0
        exemplos["vazio"] = {"value": vazio}
    respostas[200] = {
        "description": "Consulta somente leitura.",
        "content": {"application/json": {"examples": exemplos}},
    }
    return respostas


def criar_aplicacao(
    configuracao: ConfiguracaoAplicacao | None = None, motor: Engine | None = None
) -> FastAPI:
    configuracao = configuracao or ConfiguracaoAplicacao()
    segredo = (
        configuracao.segredo_cursor.get_secret_value().encode()
        if configuracao.segredo_cursor
        else b""
    )
    if len(segredo) < 32:
        raise ValueError("Defina SEGREDO_CURSOR com pelo menos32bytes para iniciar a API.")
    proprio = motor is None
    motor = motor or (
        criar_motor(configuracao.url_banco_api) if configuracao.url_banco_api else None
    )
    repositorio = RepositorioLeitura(motor, segredo)
    cliente_redis = criar_cliente_redis(configuracao)
    metricas = MetricasAPI()
    cache_leitura = CacheLeitura(cliente_redis, observar=metricas.observar_cache)
    limitador = LimitadorLocal(configuracao.limite_requisicoes_minuto)

    @asynccontextmanager
    async def ciclo_vida(aplicacao: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if cliente_redis is not None:
                cliente_redis.fechar()
            if proprio and repositorio.motor is not None:
                repositorio.motor.dispose()

    aplicacao = FastAPI(
        title="Pipeline ETL — BCB",
        version="1.0.0",
        lifespan=ciclo_vida,
        description=(
            "Consulta somente leitura. Cobertura histórica e calendários podem estar incompletos."
        ),
    )

    aplicacao.state.cache_leitura = cache_leitura
    metricas.registro.register(EstatisticasPipeline(motor))
    aplicacao.add_middleware(MiddlewareMetricas, metricas=metricas)

    @aplicacao.get("/metrics", include_in_schema=False)
    def consultar_metricas() -> Response:
        return Response(metricas.gerar(), headers={"Content-Type": CONTENT_TYPE_LATEST})

    @aplicacao.middleware("http")
    async def controlar(
        requisicao: Request, proximo: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        requisicao.state.requisicao_id = str(uuid4())
        inicio = time.monotonic()
        espera = (
            limitador.conferir(requisicao.client.host if requisicao.client else "local")
            if requisicao.url.path.startswith("/api/")
            else 0
        )
        resposta: Response
        if espera:
            resposta = erro_publico(
                requisicao, 429, "LIMITE_EXCEDIDO", "Limite local de requisições excedido."
            )
            resposta.headers["Retry-After"] = str(espera)
        else:
            try:
                resposta = await proximo(requisicao)
            except Exception:
                resposta = erro_publico(
                    requisicao, 500, "ERRO_INTERNO", "Não foi possível concluir a consulta."
                )
        resposta.headers["X-Request-ID"] = requisicao.state.requisicao_id
        structlog.get_logger(servico="api").info(
            "Requisição finalizada",
            requisicao_id=requisicao.state.requisicao_id,
            status=resposta.status_code,
            duracao_ms=round((time.monotonic() - inicio) * 1000, 2),
            rota=getattr(requisicao.scope.get("route"), "path", "nao_encontrada"),
        )
        return resposta

    @aplicacao.exception_handler(ErroAPI)
    async def tratar_api(requisicao: Request, erro: ErroAPI) -> Response:
        return erro_publico(requisicao, erro.status, erro.codigo, erro.mensagem)

    @aplicacao.exception_handler(SQLAlchemyError)
    async def tratar_banco(requisicao: Request, erro: SQLAlchemyError) -> Response:
        return erro_publico(
            requisicao, 503, "BANCO_INDISPONIVEL", "Banco ou esquema de consulta indisponível."
        )

    @aplicacao.exception_handler(RequestValidationError)
    async def tratar_validacao(requisicao: Request, erro: RequestValidationError) -> Response:
        campos = {"codigo", "de", "ate", "limite", "cursor", "granularidade", "fonte", "situacao"}
        detalhes = [
            DetalheErro(
                campo=str(item["loc"][-1])
                if item["loc"] and str(item["loc"][-1]) in campos
                else "consulta",
                tipo=item["type"],
            )
            for item in erro.errors()
        ]
        return erro_publico(
            requisicao, 422, "PARAMETRO_INVALIDO", "Confira os parâmetros da consulta.", detalhes
        )

    @aplicacao.exception_handler(HTTPException)
    async def tratar_http(requisicao: Request, erro: HTTPException) -> Response:
        return erro_publico(
            requisicao, erro.status_code, "RECURSO_INDISPONIVEL", "Rota ou método indisponível."
        )

    @aplicacao.get(
        "/health", response_model=EstadoServico, responses=documentar({"situacao": "vivo"})
    )
    def saude(requisicao: Request) -> Response:
        return responder(requisicao, EstadoServico(situacao="vivo"), cacheavel=False)

    @aplicacao.get(
        "/ready",
        response_model=EstadoServico,
        responses=documentar({"situacao": "pronto", "esquema": ESQUEMA_ESPERADO}),
    )
    def prontidao(requisicao: Request) -> Response:
        with repositorio.instantaneo() as conexao:
            repositorio.conferir_esquema(conexao)
            conexao.execute(text("SELECT codigo_sgs FROM core.dim_serie LIMIT 1"))
            quantidade = conexao.scalar(
                text(
                    "SELECT count(*) FROM pg_matviews WHERE schemaname='mart' AND "
                    "matviewname IN ('mv_serie_mensal','mv_serie_anual','mv_ipca_12m')"
                )
            )
            if quantidade != 3:
                raise ErroAPI(503, "ESQUEMA_INCOMPATIVEL", "Visões de consulta incompatíveis.")
        return responder(
            requisicao, EstadoServico(situacao="pronto", esquema=ESQUEMA_ESPERADO), cacheavel=False
        )

    @aplicacao.get(
        "/api/v1/series",
        response_model=RespostaDados[list[Serie]],
        responses=documentar(
            {
                "data": [
                    {
                        "codigo": 432,
                        "nome": "Meta Selic",
                        "periodicidade": "diaria",
                        "unidade": "% a.a.",
                        "inicio_publico": "2020-01-01",
                        "cobertura": {
                            "inicio": "2020-01-02",
                            "fim": "2020-01-06",
                            "observacoes": 5,
                            "completa": None,
                        },
                        "regra": "Observações publicadas; calendário não homologado.",
                    }
                ],
                "meta": {"camada": "core", "versao_dados": 1, "versao_core": 1, "versao_gold": 0},
            }
        ),
    )
    def listar_series(requisicao: Request) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = repositorio.estado(conexao)

            def calcular() -> Response:
                dados = repositorio.catalogo(conexao)
                return responder_sem_condicional(
                    requisicao, RespostaDados(data=dados, meta=repositorio.meta(estado, "core"))
                )

            return responder_cache(requisicao, estado, "core", calcular, validade=3600)

    @aplicacao.get(
        "/api/v1/series/{codigo}",
        response_model=RespostaDados[Serie],
        responses=documentar(
            {
                "data": {
                    "codigo": 432,
                    "nome": "Meta Selic",
                    "periodicidade": "diaria",
                    "unidade": "% a.a.",
                    "inicio_publico": "2020-01-01",
                    "cobertura": {
                        "inicio": "2020-01-02",
                        "fim": "2020-01-06",
                        "observacoes": 5,
                        "completa": None,
                    },
                    "regra": "Observações publicadas; calendário não homologado.",
                },
                "meta": {"camada": "core", "versao_dados": 1, "versao_core": 1, "versao_gold": 0},
            }
        ),
    )
    def detalhar_serie(codigo: int, requisicao: Request) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = repositorio.estado(conexao)

            def calcular() -> Response:
                serie = repositorio.serie(conexao, codigo)
                return responder_sem_condicional(
                    requisicao,
                    RespostaDados(
                        data=serie,
                        meta=repositorio.meta(
                            estado,
                            "core",
                            codigo=codigo,
                            unidade=serie.unidade,
                            cobertura=serie.cobertura,
                        ),
                    ),
                )

            return responder_cache(requisicao, estado, "core", calcular, validade=3600)

    @aplicacao.get(
        "/api/v1/series/{codigo}/observacoes",
        response_model=RespostaPaginada[Observacao],
        responses=documentar(
            {
                "data": [{"data": "2020-01-02", "valor": "4.500000"}],
                "pagina": {"limite": 100, "tem_mais": False, "proximo_cursor": None},
                "meta": {"camada": "core", "versao_dados": 1, "versao_core": 1, "versao_gold": 0},
            }
        ),
    )
    def listar_observacoes(
        codigo: int, requisicao: Request, filtros: Annotated[FiltrosPeriodo, Query()]
    ) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = repositorio.estado(conexao)
            repositorio.validar_cursor_temporal(codigo, filtros, estado, "observacoes")

            def calcular() -> Response:
                serie = repositorio.serie(conexao, codigo)
                dados, pagina = repositorio.temporal(
                    conexao, codigo, filtros, estado, "observacoes"
                )
                return responder_sem_condicional(
                    requisicao,
                    RespostaPaginada(
                        data=dados,
                        pagina=pagina,
                        meta=repositorio.meta(
                            estado,
                            "core",
                            codigo=codigo,
                            unidade=serie.unidade,
                            cobertura=serie.cobertura,
                            de=filtros.de,
                            ate=filtros.ate,
                        ),
                    ),
                )

            return responder_cache(requisicao, estado, "core", calcular, validade=300)

    @aplicacao.get(
        "/api/v1/series/{codigo}/agregados",
        response_model=RespostaPaginada[Agregado],
        responses=documentar(
            {
                "data": [
                    {
                        "periodo": "2020-01-01",
                        "unidade": "% a.a.",
                        "observacoes": 5,
                        "media": "4.500000",
                        "minimo": "4.500000",
                        "maximo": "4.500000",
                        "ultimo": "4.500000",
                        "variacao": None,
                        "completo": None,
                        "parcial": False,
                        "motivo": "CALENDARIO_NAO_HOMOLOGADO",
                        "data_referencia": "2026-11-18",
                    }
                ],
                "pagina": {"limite": 100, "tem_mais": False},
                "meta": {
                    "camada": "gold",
                    "versao_dados": 1,
                    "versao_core": 1,
                    "versao_gold": 1,
                    "data_publicacao": "2026-11-18",
                },
            }
        ),
    )
    def listar_agregados(
        codigo: int, requisicao: Request, filtros: Annotated[FiltrosAgregados, Query()]
    ) -> Response:
        with repositorio.instantaneo(proteger_gold=True) as conexao:
            estado = repositorio.estado(conexao)
            repositorio.validar_cursor_temporal(codigo, filtros, estado, "agregados")

            def calcular() -> Response:
                serie = repositorio.serie(conexao, codigo)
                dados, pagina = repositorio.temporal(conexao, codigo, filtros, estado, "agregados")
                unidade = (
                    "% no ano"
                    if codigo == 433 and filtros.granularidade == "ano"
                    else serie.unidade
                )
                return responder_sem_condicional(
                    requisicao,
                    RespostaPaginada(
                        data=dados,
                        pagina=pagina,
                        meta=repositorio.meta(
                            estado,
                            "gold",
                            codigo=codigo,
                            unidade=unidade,
                            cobertura=repositorio.cobertura_gold(
                                conexao, codigo, estado, filtros.granularidade
                            ),
                            de=filtros.de,
                            ate=filtros.ate,
                        ),
                    ),
                )

            return responder_cache(requisicao, estado, "gold", calcular, validade=900)

    @aplicacao.get(
        "/api/v1/indicadores/ipca-12m",
        response_model=RespostaPaginada[Agregado],
        responses=documentar(
            {
                "data": [
                    {
                        "periodo": "2020-01-01",
                        "unidade": "% no periodo",
                        "observacoes": 5,
                        "media": None,
                        "minimo": None,
                        "maximo": None,
                        "ultimo": None,
                        "variacao": None,
                        "completo": False,
                        "parcial": False,
                        "motivo": "MESES_AUSENTES",
                        "data_referencia": "2026-11-18",
                    }
                ],
                "pagina": {"limite": 100, "tem_mais": False},
                "meta": {
                    "camada": "gold",
                    "versao_dados": 1,
                    "versao_core": 1,
                    "versao_gold": 1,
                    "data_publicacao": "2026-11-18",
                },
            }
        ),
    )
    def listar_ipca(requisicao: Request, filtros: Annotated[FiltrosPeriodo, Query()]) -> Response:
        with repositorio.instantaneo(proteger_gold=True) as conexao:
            estado = repositorio.estado(conexao)
            repositorio.validar_cursor_temporal(433, filtros, estado, "ipca12m")

            def calcular() -> Response:
                repositorio.serie(conexao, 433)
                dados, pagina = repositorio.temporal(conexao, 433, filtros, estado, "ipca12m")
                return responder_sem_condicional(
                    requisicao,
                    RespostaPaginada(
                        data=dados,
                        pagina=pagina,
                        meta=repositorio.meta(
                            estado,
                            "gold",
                            codigo=433,
                            unidade="% no periodo",
                            cobertura=repositorio.cobertura_gold(conexao, 433, estado, "ipca12m"),
                            de=filtros.de,
                            ate=filtros.ate,
                        ),
                    ),
                )

            return responder_cache(requisicao, estado, "gold", calcular, validade=900)

    @aplicacao.get(
        "/api/v1/pipeline/execucoes",
        response_model=RespostaPaginada[Execucao],
        responses=documentar(
            {
                "data": [
                    {
                        "execucao_id": "00000000-0000-0000-0000-000000000001",
                        "modo": "carga_bcb",
                        "fonte": "bcb",
                        "situacao": "SUCESSO",
                        "iniciado_em": "2026-11-18T12:00:00Z",
                        "finalizado_em": "2026-11-18T12:01:00Z",
                    }
                ],
                "pagina": {"limite": 100, "tem_mais": False},
                "meta": {
                    "camada": "operacional",
                    "versao_dados": 0,
                    "versao_core": 0,
                    "versao_gold": 0,
                },
            }
        ),
    )
    def listar_execucoes(
        requisicao: Request, filtros: Annotated[FiltrosExecucoes, Query()]
    ) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = repositorio.estado(conexao)
            dados, pagina = repositorio.execucoes(conexao, filtros)
            return responder(
                requisicao,
                RespostaPaginada(
                    data=dados, pagina=pagina, meta=repositorio.meta(estado, "operacional")
                ),
                cacheavel=False,
            )

    @aplicacao.get(
        "/api/v1/pipeline/frescor",
        response_model=RespostaDados[list[Frescor]],
        responses=documentar(
            {
                "data": [
                    {
                        "codigo": 432,
                        "unidade": "% a.a.",
                        "cobertura": {
                            "inicio": "2020-01-02",
                            "fim": "2020-01-06",
                            "observacoes": 5,
                            "completa": None,
                        },
                        "ultima_consulta": "2026-11-18T12:00:00Z",
                        "ultima_referencia": "2020-01-06",
                        "ultima_publicacao": "2026-11-18T12:01:00Z",
                        "defasado": True,
                        "politica": "HEURISTICA_4_DIAS",
                        "calendario_homologado": False,
                    }
                ],
                "meta": {
                    "camada": "operacional",
                    "versao_dados": 1,
                    "versao_core": 1,
                    "versao_gold": 0,
                },
            }
        ),
    )
    def consultar_frescor(requisicao: Request) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = repositorio.estado(conexao)
            return responder(
                requisicao,
                RespostaDados(
                    data=repositorio.frescor(conexao), meta=repositorio.meta(estado, "gold")
                ),
                cacheavel=False,
            )

    from pipeline_etl.api.ibge import criar_rotas_ibge

    aplicacao.include_router(criar_rotas_ibge(repositorio))
    return aplicacao
