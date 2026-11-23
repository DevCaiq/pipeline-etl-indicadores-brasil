"""Métricas locais com rótulos limitados e leitura sanitizada do pipeline."""

from collections.abc import Iterator
from time import perf_counter

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily, Metric
from sqlalchemy import Engine, text
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pipeline_etl.api.filtros import hoje_brasil
from pipeline_etl.api.metricas_operacionais import coletar_operacionais
from pipeline_etl.processamento.frescor import avaliar_frescor_local

EVENTOS_CACHE = frozenset(
    {
        "acerto",
        "calculo",
        "ausencia",
        "falha_backend",
        "circuito_aberto",
        "desativado",
        "trava_ocupada",
    }
)
METODOS_HTTP = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
FASES = {
    "pipeline_bcb": "bcb",
    "carga_bcb": "bcb",
    "coleta_validacao": "bcb",
    "validacao_bronze": "bcb",
    "coleta_atualizacao": "bcb",
    "atualizacao_bcb": "bcb",
    "publicacao_bcb": "bcb",
    "pipeline_ibge": "ibge",
    "carga_ibge": "ibge",
    "publicacao_ibge": "ibge",
}
SITUACOES = frozenset({"EM_EXECUCAO", "SUCESSO", "PARCIAL", "FALHA", "IGNORADA"})


class MetricasAPI:
    """Registro por processo; cada aplicação deve manter sua própria instância."""

    def __init__(self, registro: CollectorRegistry | None = None):
        self.registro = registro if registro is not None else CollectorRegistry()
        self.requisicoes = Counter(
            "http_requisicoes_total",
            "Requisições HTTP observadas.",
            ["rota", "metodo", "status"],
            registry=self.registro,
        )
        self.duracao = Histogram(
            "http_duracao_segundos",
            "Duração das requisições HTTP.",
            ["rota", "metodo", "status"],
            registry=self.registro,
        )

        self.cache_eventos = Counter(
            "cache_eventos_total",
            "Eventos do cache por processo; eventos não são exclusivos.",
            ["evento"],
            registry=self.registro,
        )

    def observar_cache(self, evento: str) -> None:
        if evento in EVENTOS_CACHE:
            self.cache_eventos.labels(evento).inc()

    def gerar(self) -> bytes:
        return generate_latest(self.registro)


class MiddlewareMetricas:
    """ASGI puro: observa a resposta e preserva exceções da aplicação."""

    def __init__(self, app: ASGIApp, metricas: MetricasAPI):
        self.aplicacao = app
        self.metricas = metricas

    async def __call__(self, escopo: Scope, receber: Receive, enviar: Send) -> None:
        if escopo["type"] != "http" or escopo.get("path") == "/metrics":
            await self.aplicacao(escopo, receber, enviar)
            return
        inicio = perf_counter()
        situacao_http = 500

        async def enviar_observado(mensagem: Message) -> None:
            nonlocal situacao_http
            if mensagem["type"] == "http.response.start":
                situacao_http = mensagem["status"]
            await enviar(mensagem)

        try:
            await self.aplicacao(escopo, receber, enviar_observado)
        finally:
            rota = getattr(escopo.get("route"), "path", "nao_encontrada")
            metodo = escopo.get("method", "")
            metodo = metodo if metodo in METODOS_HTTP else "OUTRO"
            rotulos = (
                rota,
                metodo,
                str(situacao_http) if 100 <= situacao_http <= 599 else "500",
            )
            self.metricas.requisicoes.labels(*rotulos).inc()
            self.metricas.duracao.labels(*rotulos).observe(perf_counter() - inicio)


class EstatisticasPipeline:
    """Coletor síncrono para /metrics em handler def; falhas não vazam detalhes."""

    def __init__(self, motor: Engine | None):
        self.motor = motor

    def describe(self) -> list[Metric]:
        # Evita consultar o banco durante o registro no Prometheus.
        return []

    def collect(self) -> Iterator[Metric]:
        disponibilidade = GaugeMetricFamily(
            "pipeline_coleta_disponivel", "Consulta das métricas operacionais bem-sucedida."
        )
        execucoes = GaugeMetricFamily(
            "pipeline_execucoes", "Execuções persistidas por situação.", labels=["situacao"]
        )
        defasagem = GaugeMetricFamily(
            "pipeline_serie_defasada",
            "Frescor: 1 atrasada, 0 em dia, -1 desconhecido.",
            labels=["serie"],
        )
        familias = {
            "quantidade": GaugeMetricFamily(
                "pipeline_fase_execucoes",
                "Execuções concluídas na auditoria retida.",
                labels=["fonte", "fase", "situacao"],
            ),
            "duracao_media": GaugeMetricFamily(
                "pipeline_fase_duracao_media_segundos",
                "Duração média histórica da fase.",
                labels=["fonte", "fase", "situacao"],
            ),
            "ultima_conclusao": GaugeMetricFamily(
                "pipeline_fase_ultima_conclusao_segundos",
                "Instante Unix da última conclusão.",
                labels=["fonte", "fase", "situacao"],
            ),
        }
        try:
            if self.motor is None:
                raise ValueError("Banco indisponível.")
            with self.motor.connect() as conexao, conexao.begin():
                conexao.execute(text("SET TRANSACTION READ ONLY"))
                conexao.execute(text("SET LOCAL statement_timeout='3s'"))
                conexao.execute(text("SET LOCAL lock_timeout='1s'"))
                totais = (
                    conexao.execute(
                        text(
                            "SELECT situacao,count(*) AS quantidade FROM ops.v_execucoes_api "
                            "GROUP BY situacao"
                        )
                    )
                    .mappings()
                    .all()
                )
                series = (
                    conexao.execute(text("SELECT codigo_sgs,fim FROM ops.v_frescor_api"))
                    .mappings()
                    .all()
                )
                fases = (
                    conexao.execute(
                        text(
                            "SELECT modo,situacao,count(*) AS quantidade,"
                            "avg(extract(epoch FROM finalizado_em-iniciado_em)) AS duracao_media,"
                            "extract(epoch FROM max(finalizado_em)) AS ultima_conclusao "
                            "FROM ops.v_execucoes_api WHERE finalizado_em >= iniciado_em "
                            "AND situacao IN ('SUCESSO','PARCIAL','FALHA','IGNORADA') "
                            "GROUP BY modo,situacao"
                        )
                    )
                    .mappings()
                    .all()
                )
                operacionais = coletar_operacionais(conexao)
            for linha in fases:
                modo, situacao = linha["modo"], linha["situacao"]
                if modo not in FASES or situacao not in SITUACOES - {"EM_EXECUCAO"}:
                    continue
                for coluna, familia in familias.items():
                    familia.add_metric([FASES[modo], modo, situacao], float(linha[coluna]))
            for linha in totais:
                situacao = linha["situacao"]
                if situacao in SITUACOES:
                    execucoes.add_metric([situacao], linha["quantidade"])
            for linha in series:
                codigo = linha["codigo_sgs"]
                if codigo not in (1, 432, 433):
                    continue
                avaliacao = avaliar_frescor_local(codigo, linha["fim"], hoje_brasil())
                defasagem.add_metric(
                    [str(codigo)], -1 if avaliacao.defasado is None else int(avaliacao.defasado)
                )
        except Exception:
            disponibilidade.add_metric([], 0)
            yield disponibilidade
            return
        disponibilidade.add_metric([], 1)
        yield disponibilidade
        yield execucoes
        yield defasagem
        yield from familias.values()
        yield from operacionais
