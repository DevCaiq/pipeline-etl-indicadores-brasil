"""Views operacionais sanitizadas e privilégios reais no banco exclusivo."""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integracao


def test_view_agrega_contagens_sem_expor_parametros(banco):
    identificador = uuid4()
    with banco.begin() as conexao:
        antes = (
            conexao.execute(
                text(
                    "SELECT * FROM ops.v_metricas_etapas_api "
                    "WHERE fase='carga_ibge' AND situacao='SUCESSO'"
                )
            )
            .mappings()
            .first()
        )
        quantidade_antes = antes["linhas_lidas"] if antes else 0
        conexao.execute(
            text(
                "INSERT INTO ops.execucao(execucao_id,modo,situacao,finalizado_em,"
                "linhas_lidas,linhas_validas,linhas_rejeitadas,linhas_duplicadas,parametros) "
                "VALUES(:id,'carga_ibge','SUCESSO',now(),10,7,2,1,"
                "CAST(:parametros AS jsonb))"
            ),
            {
                "id": identificador,
                "parametros": json.dumps(
                    {
                        "senha": "segredo",
                        "metricas_coleta": {"requisicoes": "invalido", "retentativas": True},
                    }
                ),
            },
        )
    motor = create_engine(
        banco.url.set(username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"])
    )
    try:
        with motor.connect() as conexao:
            linha = (
                conexao.execute(
                    text(
                        "SELECT * FROM ops.v_metricas_etapas_api "
                        "WHERE fase='carga_ibge' AND situacao='SUCESSO'"
                    )
                )
                .mappings()
                .one()
            )
            assert linha["linhas_lidas"] == quantidade_antes + 10
            assert "parametros" not in linha and "senha" not in linha
            assert linha["requisicoes"] is None
        with pytest.raises(DBAPIError), motor.begin() as conexao:
            conexao.execute(text("UPDATE ops.v_metricas_etapas_api SET linhas_lidas=0"))
        with pytest.raises(DBAPIError), motor.connect() as conexao:
            conexao.execute(text("SELECT parametros FROM ops.execucao"))
    finally:
        motor.dispose()
        with banco.begin() as conexao:
            conexao.execute(
                text("DELETE FROM ops.execucao WHERE execucao_id=:id"), {"id": identificador}
            )


def test_estado_ibge_sem_dados_nao_inventa_frescor(banco):
    with banco.connect() as conexao:
        linha = conexao.execute(text("SELECT * FROM ops.v_monitoramento_ibge_api")).mappings().one()
        assert set(linha) == {
            "ultima_localidades",
            "ultima_consulta_populacao",
            "ultimo_ano_descoberto",
            "ultimo_ano_carregado",
        }
        assert conexao.scalar(
            text("SELECT has_table_privilege('api_leitura','ops.v_cobertura_ibge_api','SELECT')")
        )
        assert not conexao.scalar(
            text(
                "SELECT has_table_privilege('processamento',"
                "'ops.v_monitoramento_ibge_api','UPDATE')"
            )
        )


def test_exporter_completo_consulta_com_papel_api(banco):
    from pipeline_etl.api.metricas import EstatisticasPipeline, MetricasAPI

    motor = create_engine(
        banco.url.set(username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"])
    )
    try:
        metricas = MetricasAPI()
        metricas.registro.register(EstatisticasPipeline(motor))
        conteudo = metricas.gerar().decode()
        assert "pipeline_coleta_disponivel 1.0" in conteudo
        assert "pipeline_ibge_periodo_pendente" in conteudo
        assert "pipeline_linhas" in conteudo
    finally:
        motor.dispose()


def test_descoberta_confirmada_sobrevive_a_falha_posterior(banco):
    from datetime import UTC, datetime

    agora = datetime.now(UTC)
    with banco.connect() as conexao:
        transacao = conexao.begin()
        try:
            conexao.execute(
                text(
                    "UPDATE ops.execucao SET parametros=parametros-'anos_disponiveis'"
                    "-'consulta_periodos_em' WHERE modo='pipeline_ibge'"
                )
            )
            conexao.execute(
                text(
                    "INSERT INTO ops.execucao(modo,situacao,finalizado_em,parametros) "
                    "VALUES('pipeline_ibge','FALHA',now(),CAST(:parametros AS jsonb))"
                ),
                {
                    "parametros": json.dumps(
                        {
                            "anos_disponiveis": [agora.year],
                            "consulta_periodos_em": agora.isoformat(),
                        }
                    )
                },
            )
            estado = (
                conexao.execute(text("SELECT * FROM ops.v_monitoramento_ibge_api")).mappings().one()
            )
            assert estado["ultimo_ano_descoberto"] == agora.year
            assert estado["ultima_consulta_populacao"] == agora.isoformat()
        finally:
            transacao.rollback()
