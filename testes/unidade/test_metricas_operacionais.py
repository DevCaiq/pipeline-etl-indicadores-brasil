"""Políticas operacionais e cobertura sem consultar a rede."""

from datetime import UTC, datetime, timedelta

from pipeline_etl.api.metricas_operacionais import avaliar_consulta, avaliar_periodos


def test_consulta_recente_antiga_ausente_e_futura():
    agora = datetime(2026, 11, 19, tzinfo=UTC)
    assert avaliar_consulta(agora - timedelta(days=14), agora, 14) == 0
    assert avaliar_consulta(agora - timedelta(days=14, seconds=1), agora, 14) == 1
    assert avaliar_consulta(None, agora, 14) == -1
    assert avaliar_consulta(agora + timedelta(seconds=1), agora, 14) == -1


def test_periodos_nao_confundem_ano_atual_com_ano_disponivel():
    assert avaliar_periodos(2025, 2025) == 0
    assert avaliar_periodos(2026, 2025) == 1
    assert avaliar_periodos(None, 2025) == -1
    assert avaliar_periodos(2026, None) == 1
    assert avaliar_periodos(2025, 2026) == -1


def test_familias_complementares_preservam_ausencia_e_contagens():
    from unittest.mock import MagicMock

    from prometheus_client import CollectorRegistry, generate_latest

    from pipeline_etl.api.metricas_operacionais import coletar_operacionais

    conexao = MagicMock()
    etapas, estado, cobertura, publicacao = [MagicMock() for _ in range(4)]
    etapas.mappings.return_value = [
        {
            "fonte": "ibge",
            "fase": "pipeline_ibge",
            "situacao": "SUCESSO",
            "linhas_lidas": 10,
            "linhas_validas": 8,
            "linhas_rejeitadas": 2,
            "linhas_duplicadas": 0,
            "linhas_nao_processadas": 0,
            "requisicoes": 12,
            "retentativas": 2,
            "execucoes_instrumentadas": 1,
        }
    ]
    estado.mappings.return_value.one.return_value = {
        "ultima_localidades": "z",
        "ultima_consulta_populacao": None,
        "ultimo_ano_descoberto": 2025,
        "ultimo_ano_carregado": 2025,
    }
    cobertura.mappings.return_value = [
        {
            "ano": 2025,
            "municipios_esperados": 5,
            "municipios_recebidos": 5,
            "municipios_disponiveis": 4,
            "municipios_indisponiveis": 1,
        }
    ]
    publicacao.mappings.return_value = [
        {"dominio": "ibge", "versao_core": 2, "versao_gold": 1, "situacao": "PENDENTE"},
        {"dominio": "privado", "versao_core": 2, "versao_gold": 1, "situacao": "PENDENTE"},
    ]
    conexao.execute.side_effect = [etapas, estado, cobertura, publicacao]
    familias = coletar_operacionais(conexao)

    class Coletor:
        def collect(self):
            return iter(familias)

    registro = CollectorRegistry()
    registro.register(Coletor())
    conteudo = generate_latest(registro).decode()
    assert (
        'pipeline_http_retentativas{fase="pipeline_ibge",fonte="ibge",situacao="SUCESSO"} 2.0'
        in conteudo
    )
    assert 'pipeline_ibge_municipios{ano="2025",tipo="indisponiveis"} 1.0' in conteudo
    assert 'pipeline_ibge_consulta_defasada{conjunto="localidades"} -1.0' in conteudo
    assert "pipeline_ibge_consulta_segundos{" not in conteudo
    assert "pipeline_ibge_periodo_pendente 0.0" in conteudo
    assert 'pipeline_publicacao_pendente{fonte="ibge"} 1.0' in conteudo
    assert "privado" not in conteudo
