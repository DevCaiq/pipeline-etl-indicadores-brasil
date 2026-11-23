"""Métricas persistentes M2 com cardinalidade limitada e ausência explícita."""

from datetime import UTC, datetime, timedelta

from prometheus_client.core import GaugeMetricFamily, Metric
from sqlalchemy import Connection, text

FASES = frozenset(
    {
        "pipeline_bcb",
        "carga_bcb",
        "coleta_validacao",
        "validacao_bronze",
        "coleta_atualizacao",
        "atualizacao_bcb",
        "publicacao_bcb",
        "pipeline_ibge",
        "carga_ibge",
        "publicacao_ibge",
    }
)
SITUACOES = frozenset({"SUCESSO", "PARCIAL", "FALHA", "IGNORADA"})


def avaliar_consulta(consulta: datetime | None, agora: datetime, limite_dias: int) -> int:
    """Retorna -1 para ausência ou relógio futuro, sem inventar sucesso."""
    if consulta is None or consulta.tzinfo is None or consulta > agora:
        return -1
    return int(agora - consulta > timedelta(days=limite_dias))


def avaliar_periodos(descoberto: int | None, carregado: int | None) -> int:
    if descoberto is None or (carregado is not None and carregado > descoberto):
        return -1
    return int(carregado is None or carregado < descoberto)


def coletar_operacionais(conexao: Connection) -> list[Metric]:
    """Retorna famílias completas; erro é tratado atomicamente pelo coletor chamador."""
    agora = datetime.now(UTC)
    linhas = GaugeMetricFamily(
        "pipeline_linhas",
        "Linhas auditadas por fase; fases não são somáveis entre si.",
        labels=["fonte", "fase", "situacao", "tipo"],
    )
    requisicoes = GaugeMetricFamily(
        "pipeline_http_requisicoes",
        "Tentativas HTTP na auditoria instrumentada retida.",
        labels=["fonte", "fase", "situacao"],
    )
    retentativas = GaugeMetricFamily(
        "pipeline_http_retentativas",
        "Tentativas adicionais na auditoria instrumentada retida.",
        labels=["fonte", "fase", "situacao"],
    )
    instrumentadas = GaugeMetricFamily(
        "pipeline_coletas_instrumentadas",
        "Execuções concluídas com contadores HTTP conhecidos.",
        labels=["fonte", "fase", "situacao"],
    )
    consultas = GaugeMetricFamily(
        "pipeline_ibge_consulta_segundos",
        "Instante Unix da última consulta confirmada; ausência não é zero.",
        labels=["conjunto"],
    )
    defasagem = GaugeMetricFamily(
        "pipeline_ibge_consulta_defasada",
        "Consulta: 1 atrasada, 0 recente, -1 desconhecida.",
        labels=["conjunto"],
    )
    periodos = GaugeMetricFamily(
        "pipeline_ibge_ano", "Último ano disponível descoberto ou carregado.", labels=["tipo"]
    )
    pendencia = GaugeMetricFamily(
        "pipeline_ibge_periodo_pendente",
        "Ano disponível não carregado: 1 sim, 0 não, -1 desconhecido.",
    )
    cobertura = GaugeMetricFamily(
        "pipeline_ibge_municipios",
        "Cobertura nacional publicada por ano e situação do valor.",
        labels=["ano", "tipo"],
    )
    publicacao = GaugeMetricFamily(
        "pipeline_publicacao_pendente",
        "Core à frente da gold ou publicação não pronta.",
        labels=["fonte"],
    )
    for linha in conexao.execute(text("SELECT * FROM ops.v_metricas_etapas_api")).mappings():
        if (
            linha["fonte"] not in {"bcb", "ibge"}
            or linha["fase"] not in FASES
            or linha["situacao"] not in SITUACOES
        ):
            continue
        rotulos = [linha["fonte"], linha["fase"], linha["situacao"]]
        for tipo in ("lidas", "validas", "rejeitadas", "duplicadas", "nao_processadas"):
            linhas.add_metric([*rotulos, tipo], float(linha["linhas_" + tipo]))
        instrumentadas.add_metric(rotulos, linha["execucoes_instrumentadas"])
        if linha["requisicoes"] is not None and linha["retentativas"] is not None:
            requisicoes.add_metric(rotulos, float(linha["requisicoes"]))
            retentativas.add_metric(rotulos, float(linha["retentativas"]))
    estado = conexao.execute(text("SELECT * FROM ops.v_monitoramento_ibge_api")).mappings().one()
    for conjunto, coluna, dias in (
        ("localidades", "ultima_localidades", 14),
        ("populacao", "ultima_consulta_populacao", 35),
    ):
        valor = estado[coluna]
        try:
            consulta = datetime.fromisoformat(valor) if isinstance(valor, str) else None
        except ValueError:
            consulta = None
        defasagem.add_metric([conjunto], avaliar_consulta(consulta, agora, dias))
        if consulta is not None and consulta.tzinfo is not None:
            consultas.add_metric([conjunto], consulta.timestamp())
    for tipo, coluna in (
        ("descoberto", "ultimo_ano_descoberto"),
        ("carregado", "ultimo_ano_carregado"),
    ):
        if estado[coluna] is not None:
            periodos.add_metric([tipo], estado[coluna])
    pendencia.add_metric(
        [], avaliar_periodos(estado["ultimo_ano_descoberto"], estado["ultimo_ano_carregado"])
    )
    for linha in conexao.execute(text("SELECT * FROM ops.v_cobertura_ibge_api")).mappings():
        for tipo in ("esperados", "recebidos", "disponiveis", "indisponiveis"):
            cobertura.add_metric([str(linha["ano"]), tipo], linha["municipios_" + tipo])
    for linha in conexao.execute(
        text("SELECT dominio,versao_core,versao_gold,situacao FROM ops.v_publicacao_api")
    ).mappings():
        if linha["dominio"] in {"bcb", "ibge"}:
            publicacao.add_metric(
                [linha["dominio"]],
                int(linha["versao_core"] > linha["versao_gold"] or linha["situacao"] != "PRONTA"),
            )
    return [
        linhas,
        requisicoes,
        retentativas,
        instrumentadas,
        consultas,
        defasagem,
        periodos,
        pendencia,
        cobertura,
        publicacao,
    ]
