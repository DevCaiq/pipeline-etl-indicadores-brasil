"""Consulta IBGE somente leitura, com paginação vinculada à geração do domínio."""

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Connection, text
from starlette.responses import Response

from pipeline_etl.api.aplicacao import documentar, responder_cache, responder_sem_condicional
from pipeline_etl.api.cursores import assinar_cursor, ler_cursor, resumir_filtros
from pipeline_etl.api.erros import ErroAPI
from pipeline_etl.api.esquemas import Pagina
from pipeline_etl.api.filtros import Paginacao, hoje_brasil
from pipeline_etl.api.repositorio import RepositorioLeitura

SIGLAS_UF = set(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)


class FiltrosMunicipios(Paginacao):
    uf: str | None = None
    q: str | None = Field(default=None, min_length=2, max_length=100)

    @field_validator("uf", mode="before")
    @classmethod
    def normalizar_uf(cls, valor: object) -> object:
        if valor is None:
            return None
        if not isinstance(valor, str) or valor.strip().upper() not in SIGLAS_UF:
            raise ValueError("Sigla de UF inválida.")
        return valor.strip().upper()

    @field_validator("q", mode="before")
    @classmethod
    def normalizar_busca(cls, valor: object) -> object:
        return valor.strip() if isinstance(valor, str) else valor


class FiltrosPopulacao(Paginacao):
    ano_de: int = Field(default=2020, ge=2020)
    ano_ate: int = Field(default_factory=lambda: hoje_brasil().year, ge=2020)
    indicador: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validar_periodo(self) -> "FiltrosPopulacao":
        if (
            not self.ano_de <= self.ano_ate <= hoje_brasil().year
            or self.ano_ate - self.ano_de >= 20
        ):
            raise ValueError("Período exige anos ordenados, não futuros e até vinte anos.")
        return self


class FiltrosTotais(Paginacao):
    ano: int = Field(default_factory=lambda: hoje_brasil().year, ge=2020)
    indicador: int = Field(default=1, ge=1)
    base_territorial: Literal["atual_na_coleta"] = "atual_na_coleta"

    @model_validator(mode="after")
    def validar_ano(self) -> "FiltrosTotais":
        if self.ano > hoje_brasil().year:
            raise ValueError("Ano futuro não permitido.")
        return self


class MetadadosIBGE(BaseModel):
    dominio: str = "ibge"
    camada: str
    versao_dados: int
    versao_core: int
    versao_gold: int
    desatualizado: bool
    data_publicacao: date | None
    natureza: str = "estimativa"
    unidade: str = "Pessoas"
    base_territorial: str = "atual_na_coleta"
    limitacao_territorial: str = (
        "Associação territorial atual na coleta; não representa malha histórica."
    )
    anos_carregados: list[int] = Field(default_factory=list)


class RespostaIBGE(BaseModel):
    data: list[dict[str, Any]] | dict[str, Any]
    pagina: Pagina | None = None
    meta: MetadadosIBGE


def _estado(repositorio: RepositorioLeitura, conexao: Connection) -> dict[str, Any]:
    repositorio.conferir_esquema(conexao)
    linha = (
        conexao.execute(text("SELECT * FROM ops.v_publicacao_api WHERE dominio='ibge'"))
        .mappings()
        .first()
    )
    return (
        dict(linha)
        if linha
        else {"versao_core": 0, "versao_gold": 0, "situacao": "PENDENTE", "data_publicacao": None}
    )


def _meta(estado: dict[str, Any], camada: str, anos: list[int] | None = None) -> MetadadosIBGE:
    return MetadadosIBGE(
        camada=camada,
        versao_dados=estado["versao_gold"] if camada == "gold" else estado["versao_core"],
        versao_core=estado["versao_core"],
        versao_gold=estado["versao_gold"],
        data_publicacao=estado["data_publicacao"],
        desatualizado=camada == "gold"
        and (estado["situacao"] != "PRONTA" or estado["versao_core"] != estado["versao_gold"]),
        anos_carregados=anos or [],
    )


def _publicar_linha(linha: dict[str, Any]) -> dict[str, Any]:
    resultado = dict(linha)
    for campo in ("populacao", "subtotal_disponivel", "populacao_total"):
        if resultado.get(campo) is not None:
            resultado[campo] = str(resultado[campo])
    if resultado.get("snapshot_id") is not None:
        resultado["snapshot_id"] = str(resultado["snapshot_id"])
    return resultado


def _recurso(existe: object) -> None:
    if not existe:
        raise ErroAPI(404, "RECURSO_NAO_ENCONTRADO", "Recurso IBGE não encontrado.")


def _chaves(
    repositorio: RepositorioLeitura,
    filtros: Paginacao,
    estado: dict[str, Any],
    rota: str,
    camada: str,
    identidade: dict[str, Any],
) -> list[str] | None:
    if not filtros.cursor:
        return None
    return ler_cursor(
        filtros.cursor,
        repositorio.segredo,
        rota,
        resumir_filtros(identidade),
        "ibge:" + repositorio.geracao(estado, camada),
    ).chaves


def _pagina(
    repositorio: RepositorioLeitura,
    linhas: list[dict[str, Any]],
    filtros: Paginacao,
    estado: dict[str, Any],
    rota: str,
    camada: str,
    identidade: dict[str, Any],
    campos: tuple[str, ...],
) -> tuple[list[dict[str, Any]], Pagina]:
    mais = len(linhas) > filtros.limite
    linhas = linhas[: filtros.limite]
    cursor = (
        assinar_cursor(
            repositorio.segredo,
            rota,
            resumir_filtros(identidade),
            "ibge:" + repositorio.geracao(estado, camada),
            [str(linhas[-1][campo]) for campo in campos],
        )
        if mais
        else None
    )
    return [_publicar_linha(linha) for linha in linhas], Pagina(
        limite=filtros.limite, tem_mais=mais, proximo_cursor=cursor
    )


def criar_rotas_ibge(repositorio: RepositorioLeitura) -> APIRouter:
    rotas = APIRouter(
        prefix="/api/v1",
        tags=["IBGE"],
        responses=documentar(
            {
                "data": [],
                "pagina": None,
                "meta": MetadadosIBGE(
                    camada="core",
                    versao_dados=0,
                    versao_core=0,
                    versao_gold=0,
                    desatualizado=True,
                    data_publicacao=None,
                ).model_dump(mode="json"),
            }
        ),
    )

    def catalogo(requisicao: Request, tipo: str) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = _estado(repositorio, conexao)

            def calcular() -> Response:
                consultas = {
                    "regioes": "SELECT codigo,sigla,nome FROM core.dim_regiao ORDER BY codigo",
                    "ufs": (
                        "SELECT codigo,sigla,nome,regiao_codigo FROM core.dim_uf ORDER BY codigo"
                    ),
                }
                linhas = (
                    [dict(linha) for linha in conexao.execute(text(consultas[tipo])).mappings()]
                    if estado["versao_core"]
                    else []
                )
                return responder_sem_condicional(
                    requisicao, RespostaIBGE(data=linhas, meta=_meta(estado, "core"))
                )

            return responder_cache(
                requisicao, estado, "core", calcular, dominio="ibge", validade=3600
            )

    @rotas.get("/regioes", response_model=RespostaIBGE)
    def listar_regioes(requisicao: Request) -> Response:
        return catalogo(requisicao, "regioes")

    @rotas.get("/ufs", response_model=RespostaIBGE)
    def listar_ufs(requisicao: Request) -> Response:
        return catalogo(requisicao, "ufs")

    @rotas.get("/municipios", response_model=RespostaIBGE)
    def listar_municipios(
        requisicao: Request, filtros: Annotated[FiltrosMunicipios, Query()]
    ) -> Response:
        identidade = filtros.model_dump(exclude={"cursor"}, mode="json")
        with repositorio.instantaneo() as conexao:
            estado = _estado(repositorio, conexao)
            chaves = _chaves(repositorio, filtros, estado, "ibge:municipios", "core", identidade)
            if chaves is not None and (
                len(chaves) != 1
                or len(chaves[0]) != 7
                or not chaves[0].isascii()
                or not chaves[0].isdigit()
            ):
                raise ErroAPI(422, "CURSOR_INVALIDO", "Chave municipal inválida.")

            def calcular() -> Response:
                busca = (
                    None
                    if filtros.q is None
                    else "%"
                    + filtros.q.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                    + "%"
                )
                linhas = (
                    [
                        dict(linha)
                        for linha in conexao.execute(
                            text(
                                "SELECT m.codigo_ibge,m.nome,m.uf_codigo,u.sigla AS uf,"
                                "u.regiao_codigo,m.ativo,m.snapshot_id "
                                "FROM core.dim_municipio m JOIN core.dim_uf u "
                                "ON u.codigo=m.uf_codigo WHERE m.ativo "
                                "AND (CAST(:uf AS text) IS NULL OR u.sigla=:uf) "
                                "AND (CAST(:q AS text) IS NULL OR m.nome ILIKE :q ESCAPE '!') "
                                "AND (CAST(:depois AS text) IS NULL OR m.codigo_ibge>:depois) "
                                "ORDER BY m.codigo_ibge LIMIT :limite"
                            ),
                            {
                                "uf": filtros.uf,
                                "q": busca,
                                "depois": chaves[0] if chaves else None,
                                "limite": filtros.limite + 1,
                            },
                        ).mappings()
                    ]
                    if estado["versao_core"]
                    else []
                )
                dados, pagina = _pagina(
                    repositorio,
                    linhas,
                    filtros,
                    estado,
                    "ibge:municipios",
                    "core",
                    identidade,
                    ("codigo_ibge",),
                )
                return responder_sem_condicional(
                    requisicao, RespostaIBGE(data=dados, pagina=pagina, meta=_meta(estado, "core"))
                )

            return responder_cache(
                requisicao,
                estado,
                "core",
                calcular,
                dominio="ibge",
                parametros=filtros.model_dump(mode="json"),
                validade=3600,
            )

    @rotas.get("/municipios/{codigo_ibge}", response_model=RespostaIBGE)
    def detalhar_municipio(
        requisicao: Request, codigo_ibge: Annotated[str, Path(pattern=r"^[0-9]{7}$")]
    ) -> Response:
        with repositorio.instantaneo() as conexao:
            estado = _estado(repositorio, conexao)

            def calcular() -> Response:
                linha = (
                    conexao.execute(
                        text(
                            "SELECT m.codigo_ibge,m.nome,m.uf_codigo,u.sigla AS uf,"
                            "u.regiao_codigo,m.ativo,m.snapshot_id FROM core.dim_municipio m "
                            "JOIN core.dim_uf u ON u.codigo=m.uf_codigo WHERE m.codigo_ibge=:codigo"
                        ),
                        {"codigo": codigo_ibge},
                    )
                    .mappings()
                    .first()
                )
                if linha is None:
                    raise ErroAPI(404, "RECURSO_NAO_ENCONTRADO", "Município não encontrado.")
                return responder_sem_condicional(
                    requisicao,
                    RespostaIBGE(data=_publicar_linha(dict(linha)), meta=_meta(estado, "core")),
                )

            return responder_cache(
                requisicao, estado, "core", calcular, dominio="ibge", validade=3600
            )

    @rotas.get("/municipios/{codigo_ibge}/populacao", response_model=RespostaIBGE)
    def consultar_populacao(
        requisicao: Request,
        codigo_ibge: Annotated[str, Path(pattern=r"^[0-9]{7}$")],
        filtros: Annotated[FiltrosPopulacao, Query()],
    ) -> Response:
        identidade = {**filtros.model_dump(exclude={"cursor"}, mode="json"), "codigo": codigo_ibge}
        with repositorio.instantaneo() as conexao:
            estado = _estado(repositorio, conexao)
            chaves = _chaves(repositorio, filtros, estado, "ibge:populacao", "core", identidade)
            try:
                depois = int(chaves[0]) if chaves is not None and len(chaves) == 1 else None
                if chaves is not None and (
                    depois is None or not filtros.ano_de <= depois <= filtros.ano_ate
                ):
                    raise ValueError()
            except ValueError:
                raise ErroAPI(422, "CURSOR_INVALIDO", "Chave de ano inválida.") from None

            def calcular() -> Response:
                _recurso(
                    conexao.scalar(
                        text("SELECT 1 FROM core.dim_municipio WHERE codigo_ibge=:codigo"),
                        {"codigo": codigo_ibge},
                    )
                )
                _recurso(
                    conexao.scalar(
                        text("SELECT 1 FROM core.dim_indicador WHERE indicador_id=:indicador"),
                        {"indicador": filtros.indicador},
                    )
                )
                anos = list(
                    conexao.execute(
                        text(
                            "SELECT DISTINCT ano FROM core.fato_populacao "
                            "WHERE indicador_id=:indicador ORDER BY ano"
                        ),
                        {"indicador": filtros.indicador},
                    ).scalars()
                )
                linhas = [
                    dict(linha)
                    for linha in conexao.execute(
                        text(
                            "SELECT codigo_ibge,ano,indicador_id,populacao,marcador,motivo,"
                            "uf_referencia,"
                            "regiao_referencia,base_territorial,snapshot_id "
                            "FROM core.fato_populacao "
                            "WHERE codigo_ibge=:codigo AND indicador_id=:indicador "
                            "AND ano BETWEEN :inicio AND :fim "
                            "AND (CAST(:depois AS integer) IS NULL OR ano>:depois) "
                            "ORDER BY ano LIMIT :limite"
                        ),
                        {
                            "codigo": codigo_ibge,
                            "indicador": filtros.indicador,
                            "inicio": filtros.ano_de,
                            "fim": filtros.ano_ate,
                            "depois": depois,
                            "limite": filtros.limite + 1,
                        },
                    ).mappings()
                ]
                dados, pagina = _pagina(
                    repositorio,
                    linhas,
                    filtros,
                    estado,
                    "ibge:populacao",
                    "core",
                    identidade,
                    ("ano",),
                )
                return responder_sem_condicional(
                    requisicao,
                    RespostaIBGE(data=dados, pagina=pagina, meta=_meta(estado, "core", anos)),
                )

            return responder_cache(
                requisicao,
                estado,
                "core",
                calcular,
                dominio="ibge",
                parametros=filtros.model_dump(mode="json"),
            )

    def total(requisicao: Request, filtros: FiltrosTotais, nivel: str) -> Response:
        identidade = filtros.model_dump(exclude={"cursor"}, mode="json")
        rota = "ibge:total:" + nivel
        with repositorio.instantaneo(proteger_gold=True, dominio="ibge") as conexao:
            estado = _estado(repositorio, conexao)
            chaves = _chaves(repositorio, filtros, estado, rota, "gold", identidade)
            try:
                codigo = int(chaves[0]) if chaves is not None and len(chaves) == 2 else None
                snapshot = UUID(chaves[1]) if chaves is not None and len(chaves) == 2 else None
                if chaves is not None and (codigo is None or snapshot is None or codigo <= 0):
                    raise ValueError()
            except (ValueError, TypeError):
                raise ErroAPI(422, "CURSOR_INVALIDO", "Chave territorial inválida.") from None

            def calcular() -> Response:
                coluna = {
                    "ufs": "uf_codigo",
                    "regioes": "regiao_codigo",
                    "brasil": "brasil_codigo",
                }[nivel]
                visao = {
                    "ufs": "mv_populacao_uf",
                    "regioes": "mv_populacao_regiao",
                    "brasil": "mv_populacao_brasil",
                }[nivel]
                linhas = (
                    [
                        dict(linha)
                        for linha in conexao.execute(
                            text(
                                # Visão/coluna vêm dos mapas constantes acima; valores são binds.
                                f"SELECT * FROM mart.{visao} "  # nosec B608
                                "WHERE ano=:ano AND indicador_id=:indicador "
                                "AND base_territorial=:base AND (CAST(:codigo AS int) IS NULL OR "
                                f"({coluna},snapshot_id)>(:codigo,CAST(:snapshot AS uuid))) "
                                f"ORDER BY {coluna},snapshot_id LIMIT :limite"
                            ),
                            {
                                "ano": filtros.ano,
                                "indicador": filtros.indicador,
                                "base": filtros.base_territorial,
                                "codigo": codigo,
                                "snapshot": str(snapshot) if snapshot else None,
                                "limite": filtros.limite + 1,
                            },
                        ).mappings()
                    ]
                    if estado["versao_gold"]
                    else []
                )
                dados, pagina = _pagina(
                    repositorio,
                    linhas,
                    filtros,
                    estado,
                    rota,
                    "gold",
                    identidade,
                    (coluna, "snapshot_id"),
                )
                return responder_sem_condicional(
                    requisicao, RespostaIBGE(data=dados, pagina=pagina, meta=_meta(estado, "gold"))
                )

            return responder_cache(
                requisicao,
                estado,
                "gold",
                calcular,
                dominio="ibge",
                parametros=filtros.model_dump(mode="json"),
                validade=900,
            )

    @rotas.get("/populacao/ufs", response_model=RespostaIBGE)
    def totais_ufs(requisicao: Request, filtros: Annotated[FiltrosTotais, Query()]) -> Response:
        return total(requisicao, filtros, "ufs")

    @rotas.get("/populacao/regioes", response_model=RespostaIBGE)
    def totais_regioes(requisicao: Request, filtros: Annotated[FiltrosTotais, Query()]) -> Response:
        return total(requisicao, filtros, "regioes")

    @rotas.get("/populacao/brasil", response_model=RespostaIBGE)
    def totais_brasil(requisicao: Request, filtros: Annotated[FiltrosTotais, Query()]) -> Response:
        return total(requisicao, filtros, "brasil")

    return rotas
