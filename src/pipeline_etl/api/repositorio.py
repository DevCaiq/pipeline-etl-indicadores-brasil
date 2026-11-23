"""Consultas parametrizadas, limitadas, sob snapshot somente leitura."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, Engine, text

from pipeline_etl.api.cursores import assinar_cursor, ler_cursor, resumir_filtros
from pipeline_etl.api.erros import ErroAPI
from pipeline_etl.api.esquemas import (
    Agregado,
    Cobertura,
    Execucao,
    Frescor,
    Metadados,
    Observacao,
    Pagina,
    Serie,
)
from pipeline_etl.api.filtros import FiltrosAgregados, FiltrosExecucoes, FiltrosPeriodo, hoje_brasil
from pipeline_etl.processamento.carga import CHAVE_TRAVA_BCB
from pipeline_etl.processamento.frescor import avaliar_frescor_local

ESQUEMA_ESPERADO = "0010"


class RepositorioLeitura:
    def __init__(self, motor: Engine | None, segredo: bytes):
        self.motor = motor
        self.segredo = segredo

    @contextmanager
    def instantaneo(
        self, proteger_gold: bool = False, dominio: str = "bcb"
    ) -> Iterator[Connection]:
        if self.motor is None:
            raise ErroAPI(503, "BANCO_INDISPONIVEL", "Banco de consulta indisponível.")
        contexto = (
            self._conexao_compartilhada(self.motor, dominio)
            if proteger_gold
            else self.motor.connect()
        )
        with contexto as conexao:
            conexao.execution_options(isolation_level="REPEATABLE READ")
            with conexao.begin():
                conexao.execute(text("SET TRANSACTION READ ONLY"))
                conexao.execute(text("SET LOCAL statement_timeout='5s'"))
                conexao.execute(text("SET LOCAL lock_timeout='2s'"))
                yield conexao

    @contextmanager
    def _conexao_compartilhada(self, motor: Engine, dominio: str = "bcb") -> Iterator[Connection]:
        if dominio not in {"bcb", "ibge"}:
            raise ValueError("Domínio de publicação desconhecido.")
        chave_trava = CHAVE_TRAVA_BCB if dominio == "bcb" else 2026112001
        # A trava de sessão antecede o snapshot; esperar dentro de RR fixaria uma visão antiga.
        with motor.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
            adquirida = False
            try:
                limite = time.monotonic() + 2
                while not conexao.scalar(
                    text("SELECT pg_try_advisory_lock_shared(:chave)"), {"chave": chave_trava}
                ):
                    if time.monotonic() >= limite:
                        raise ErroAPI(
                            503, "PUBLICACAO_OCUPADA", "Publicação em andamento; tente novamente."
                        )
                    time.sleep(0.02)
                adquirida = True
                conexao.commit()
                yield conexao
            finally:
                if adquirida:
                    try:
                        conexao.rollback()
                        conexao.execution_options(isolation_level="AUTOCOMMIT")
                        conexao.execute(
                            text("SELECT pg_advisory_unlock_shared(:chave)"),
                            {"chave": chave_trava},
                        )
                        conexao.commit()
                    except Exception:
                        # Uma sessão com liberação incerta jamais retorna ao pool.
                        conexao.invalidate()
                else:
                    # O banco pode ter adquirido a trava antes de uma falha na leitura da resposta.
                    conexao.invalidate()

    def conferir_esquema(self, conexao: Connection) -> None:
        if conexao.scalar(text("SELECT version_num FROM ops.v_esquema_api")) != ESQUEMA_ESPERADO:
            raise ErroAPI(503, "ESQUEMA_INCOMPATIVEL", "Esquema de consulta incompatível.")

    def estado(self, conexao: Connection) -> dict[str, Any]:
        self.conferir_esquema(conexao)
        linha = (
            conexao.execute(text("SELECT * FROM ops.v_publicacao_api WHERE dominio='bcb'"))
            .mappings()
            .first()
        )
        return (
            dict(linha)
            if linha
            else {
                "versao_core": 0,
                "versao_gold": 0,
                "situacao": "PENDENTE",
                "data_publicacao": None,
            }
        )

    def meta(self, estado: dict[str, Any], camada: str, **campos: Any) -> Metadados:
        sem_gold = estado["versao_gold"] == 0
        return Metadados(
            camada=camada,
            versao_dados=estado["versao_gold"] if camada == "gold" else estado["versao_core"],
            versao_core=estado["versao_core"],
            versao_gold=estado["versao_gold"],
            data_publicacao=estado["data_publicacao"],
            desatualizado=camada == "gold"
            and (
                estado["situacao"] != "PRONTA"
                or estado["versao_core"] != estado["versao_gold"]
                or estado["data_publicacao"] != hoje_brasil()
            ),
            motivo="GOLD_NAO_PUBLICADA" if camada == "gold" and sem_gold else None,
            **campos,
        )

    def geracao(self, estado: dict[str, Any], camada: str) -> str:
        return (
            f"core:{estado['versao_core']}"
            if camada == "core"
            else (
                f"gold:{estado['versao_gold']}:{estado['versao_core']}:"
                f"{estado['situacao']}:{estado['data_publicacao']}"
            )
        )

    def _consultar_series(self, conexao: Connection, codigo: int | None = None) -> list[Serie]:
        consulta = (
            "SELECT s.codigo_sgs AS codigo,s.nome,s.periodicidade,s.unidade,s.inicio_publico, "
            "f.inicio,f.fim,f.observacoes FROM core.dim_serie s JOIN "
            "ops.v_frescor_api f USING(codigo_sgs) "
        )
        if codigo is not None:
            # A igualdade permite restringir a agregação da view à série pedida.
            consulta += "WHERE s.codigo_sgs=:codigo "
        consulta += "ORDER BY s.codigo_sgs"
        linhas = conexao.execute(text(consulta), {"codigo": codigo}).mappings()
        return [
            Serie(
                codigo=linha["codigo"],
                nome=linha["nome"],
                periodicidade=linha["periodicidade"],
                unidade=linha["unidade"],
                inicio_publico=linha["inicio_publico"],
                cobertura=Cobertura(
                    inicio=linha["inicio"], fim=linha["fim"], observacoes=linha["observacoes"]
                ),
                regra="Composição mensal com continuidade; apoio2019 não público."
                if linha["codigo"] == 433
                else "Estatísticas sobre observações publicadas; calendário não homologado.",
            )
            for linha in linhas
        ]

    def catalogo(self, conexao: Connection) -> list[Serie]:
        return self._consultar_series(conexao)

    def serie(self, conexao: Connection, codigo: int) -> Serie:
        series = self._consultar_series(conexao, codigo)
        if series:
            return series[0]
        raise ErroAPI(404, "SERIE_NAO_ENCONTRADA", "Série não encontrada.")

    def cobertura_gold(
        self, conexao: Connection, codigo: int, estado: dict[str, Any], tipo: str
    ) -> Cobertura:
        if estado["versao_gold"] == 0:
            return Cobertura(unidade_contagem="periodos", motivo="GOLD_NAO_PUBLICADA")
        consultas = {
            "mes": (
                "SELECT min(periodo) AS inicio,max(periodo) AS fim,count(*) AS "
                "observacoes FROM mart.mv_serie_mensal WHERE codigo_sgs=:codigo"
            ),
            "ano": (
                "SELECT min(periodo) AS inicio,max(periodo) AS fim,count(*) AS "
                "observacoes FROM mart.mv_serie_anual WHERE codigo_sgs=:codigo"
            ),
            "ipca12m": (
                "SELECT min(periodo) AS inicio,max(periodo) AS fim,count(*) AS "
                "observacoes FROM mart.mv_ipca_12m WHERE codigo_sgs=:codigo"
            ),
        }
        linha = conexao.execute(text(consultas[tipo]), {"codigo": codigo}).mappings().one()
        return Cobertura(
            inicio=linha["inicio"],
            fim=linha["fim"],
            observacoes=linha["observacoes"],
            unidade_contagem="periodos",
            motivo="PERIODOS_PUBLICADOS",
        )

    def validar_cursor_temporal(
        self,
        codigo: int,
        filtros: FiltrosPeriodo,
        estado: dict[str, Any],
        tipo: str,
    ) -> date | None:
        """Valida o cursor em toda requisição, inclusive antes de reutilizar cache."""
        camada = "core" if tipo == "observacoes" else "gold"
        rota = f"{tipo}:{codigo}"
        resumo_filtros = resumir_filtros(filtros.model_dump(exclude={"cursor"}))
        geracao = self.geracao(estado, camada)
        depois = None
        if filtros.cursor:
            conteudo = ler_cursor(filtros.cursor, self.segredo, rota, resumo_filtros, geracao)
            try:
                if len(conteudo.chaves) != 1 or conteudo.teto is not None:
                    raise ValueError()
                depois = date.fromisoformat(conteudo.chaves[0])
                if not filtros.de <= depois <= filtros.ate:
                    raise ValueError()
            except ValueError:
                raise ErroAPI(422, "CURSOR_INVALIDO", "Chave de cursor inválida.") from None
        return depois

    def temporal(
        self,
        conexao: Connection,
        codigo: int,
        filtros: FiltrosPeriodo,
        estado: dict[str, Any],
        tipo: str,
    ) -> tuple[list[Any], Pagina]:
        camada = "core" if tipo == "observacoes" else "gold"
        rota = f"{tipo}:{codigo}"
        resumo_filtros = resumir_filtros(filtros.model_dump(exclude={"cursor"}))
        geracao = self.geracao(estado, camada)
        depois = self.validar_cursor_temporal(codigo, filtros, estado, tipo)
        if camada == "gold" and estado["versao_gold"] == 0:
            return [], Pagina(limite=filtros.limite)
        if tipo == "observacoes":
            coluna = "data"
            consulta = (
                "SELECT data,valor FROM core.fato_serie WHERE codigo_sgs=:codigo AND "
                "data>=:de AND data<=:ate AND (CAST(:depois AS date) IS NULL OR "
                "data>:depois) ORDER BY data LIMIT :quantidade"
            )
        else:
            coluna = "periodo"
            granularidade = (
                filtros.granularidade if isinstance(filtros, FiltrosAgregados) else "mes"
            )
            consultas = {
                "mes": (
                    "SELECT * FROM mart.mv_serie_mensal WHERE codigo_sgs=:codigo AND "
                    "periodo>=:de AND periodo<=:ate AND (CAST(:depois AS date) IS NULL OR "
                    "periodo>:depois) ORDER BY periodo LIMIT :quantidade"
                ),
                "ano": (
                    "SELECT * FROM mart.mv_serie_anual WHERE codigo_sgs=:codigo AND "
                    "periodo>=:de AND periodo<=:ate AND (CAST(:depois AS date) IS NULL OR "
                    "periodo>:depois) ORDER BY periodo LIMIT :quantidade"
                ),
                "ipca12m": (
                    "SELECT * FROM mart.mv_ipca_12m WHERE codigo_sgs=:codigo AND "
                    "periodo>=:de AND periodo<=:ate AND (CAST(:depois AS date) IS NULL OR "
                    "periodo>:depois) ORDER BY periodo LIMIT :quantidade"
                ),
            }
            consulta = consultas["ipca12m" if tipo == "ipca12m" else granularidade]
        comando = text(consulta)
        linhas = (
            conexao.execute(
                comando,
                {
                    "codigo": codigo,
                    "de": filtros.de,
                    "ate": filtros.ate,
                    "depois": depois,
                    "quantidade": filtros.limite + 1,
                },
            )
            .mappings()
            .all()
        )
        tem_mais = len(linhas) > filtros.limite
        selecionadas = linhas[: filtros.limite]
        cursor = (
            assinar_cursor(
                self.segredo, rota, resumo_filtros, geracao, [str(selecionadas[-1][coluna])]
            )
            if tem_mais
            else None
        )
        dados = [
            Observacao.model_validate(linha)
            if tipo == "observacoes"
            else Agregado.model_validate(linha)
            for linha in selecionadas
        ]
        return dados, Pagina(limite=filtros.limite, proximo_cursor=cursor, tem_mais=tem_mais)

    def execucoes(
        self, conexao: Connection, filtros: FiltrosExecucoes
    ) -> tuple[list[Execucao], Pagina]:
        identidade = resumir_filtros(filtros.model_dump(exclude={"cursor"}))
        teto = conexao.scalar(text("SELECT CURRENT_TIMESTAMP"))
        inicio = identificador = None
        if filtros.cursor:
            conteudo = ler_cursor(
                filtros.cursor, self.segredo, "execucoes", identidade, "historico-v1"
            )
            try:
                if len(conteudo.chaves) != 2 or conteudo.teto is None:
                    raise ValueError()
                inicio = datetime.fromisoformat(conteudo.chaves[0])
                identificador = UUID(conteudo.chaves[1])
                teto = datetime.fromisoformat(conteudo.teto)
                if inicio.tzinfo is None or teto.tzinfo is None or inicio > teto:
                    raise ValueError()
            except ValueError:
                raise ErroAPI(422, "CURSOR_INVALIDO", "Chave de cursor inválida.") from None
        linhas = (
            conexao.execute(
                text(
                    "SELECT * FROM ops.v_execucoes_api WHERE iniciado_em<=:teto "
                    "AND (CAST(:fonte AS text) IS NULL OR fonte=:fonte) AND (CAST(:situacao"
                    " AS text) IS NULL OR situacao=:situacao) "
                    "AND (CAST(:inicio AS timestamptz) IS NULL OR "
                    "(iniciado_em,execucao_id)<(:inicio,:id)) "
                    "ORDER BY iniciado_em DESC,execucao_id DESC LIMIT :quantidade"
                ),
                {
                    "teto": teto,
                    "fonte": filtros.fonte,
                    "situacao": filtros.situacao,
                    "inicio": inicio,
                    "id": identificador,
                    "quantidade": filtros.limite + 1,
                },
            )
            .mappings()
            .all()
        )
        selecionadas = linhas[: filtros.limite]
        tem_mais = len(linhas) > filtros.limite
        cursor = (
            assinar_cursor(
                self.segredo,
                "execucoes",
                identidade,
                "historico-v1",
                [selecionadas[-1]["iniciado_em"].isoformat(), str(selecionadas[-1]["execucao_id"])],
                teto=teto.isoformat(),
            )
            if tem_mais
            else None
        )
        return [Execucao.model_validate(linha) for linha in selecionadas], Pagina(
            limite=filtros.limite, proximo_cursor=cursor, tem_mais=tem_mais
        )

    def frescor(self, conexao: Connection) -> list[Frescor]:
        series = {serie.codigo: serie for serie in self.catalogo(conexao)}
        linhas = conexao.execute(
            text("SELECT * FROM ops.v_frescor_api ORDER BY codigo_sgs")
        ).mappings()
        resultado = []
        hoje = hoje_brasil()
        for linha in linhas:
            avaliacao = avaliar_frescor_local(linha["codigo_sgs"], linha["fim"], hoje)
            resultado.append(
                Frescor(
                    codigo=linha["codigo_sgs"],
                    unidade=series[linha["codigo_sgs"]].unidade,
                    cobertura=series[linha["codigo_sgs"]].cobertura,
                    ultima_consulta=linha["ultima_consulta"],
                    ultima_referencia=linha["fim"],
                    ultima_publicacao=linha["ultima_publicacao"],
                    defasado=avaliacao.defasado,
                    politica=avaliacao.politica,
                    calendario_homologado=avaliacao.politica == "CALENDARIO_IBGE",
                    motivo=avaliacao.motivo,
                    referencia_esperada=avaliacao.referencia_esperada,
                    data_limite=avaliacao.data_limite,
                    versao_calendario=avaliacao.versao_calendario,
                )
            )
        return resultado
