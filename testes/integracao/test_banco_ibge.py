"""Migração e integridade IBGE em PostgreSQL exclusivo de testes."""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pipeline_etl.banco.modelos_ibge import FatoPopulacao

pytestmark = pytest.mark.integracao


def test_catalogo_ibge_e_visoes_vazias_populadas(banco: Engine) -> None:
    assert FatoPopulacao.__tablename__ == "fato_populacao"
    with banco.connect() as conexao:
        assert conexao.execute(
            text(
                "SELECT fonte,tabela,variavel,natureza,unidade FROM core.dim_indicador "
                "WHERE indicador_id=1"
            )
        ).one() == ("IBGE", "6579", "9324", "estimativa", "Pessoas")
        for nome in ("uf", "regiao", "brasil"):
            assert (
                conexao.scalar(
                    text(
                        "SELECT ispopulated FROM pg_matviews "
                        "WHERE schemaname='mart' AND matviewname=:nome"
                    ),
                    {"nome": "mv_populacao_" + nome},
                )
                is True
            )
            assert (
                conexao.scalar(
                    text(
                        "SELECT pg_get_userbyid(relowner) FROM pg_class "
                        "WHERE oid=CAST(:nome AS regclass)"
                    ),
                    {"nome": "mart.mv_populacao_" + nome},
                )
                == "publicador"
            )


def test_restricoes_populacao_sao_explicitas_contra_nulos(banco: Engine) -> None:
    with banco.connect() as conexao:
        restricoes = (
            conexao.execute(
                text(
                    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid='core.fato_populacao'::regclass AND contype='c'"
                )
            )
            .scalars()
            .all()
        )
        assert any("DADO_NAO_DISPONIVEL" in restricao for restricao in restricoes)
        assert any("IS NOT NULL" in restricao for restricao in restricoes)
        assert any("2020" in restricao for restricao in restricoes)


def test_indicador_duplicado_nao_altera_seed(banco: Engine) -> None:
    with (
        banco.connect() as conexao,
        conexao.begin(),
        pytest.raises(IntegrityError),
        conexao.begin_nested(),
    ):
        conexao.execute(
            text(
                "INSERT INTO core.dim_indicador "
                "(indicador_id,fonte,tabela,variavel,natureza,unidade) "
                "VALUES (99999,'IBGE','6579','9324','estimativa','Pessoas')"
            )
        )


def test_cobertura_gold_ausencia_check_fk_e_snapshot_imutavel(banco: Engine) -> None:
    """Dados sintéticos isolados por rollback; nenhuma amostra oficial é alterada."""
    from uuid import uuid4

    from sqlalchemy.exc import DBAPIError

    with banco.connect() as conexao:
        transacao = conexao.begin()
        try:
            execucao, lote, snapshot = uuid4(), uuid4(), uuid4()
            conexao.execute(
                text("INSERT INTO ops.execucao(execucao_id,modo) VALUES (:id,'teste')"),
                {"id": execucao},
            )
            conexao.execute(
                text(
                    "INSERT INTO ops.lote(lote_id,execucao_id,fonte,chave,janela_inicio,janela_fim,"
                    "manifesto) VALUES "
                    "(:lote,:execucao,'IBGE','teste','2025-01-01','2025-12-31','teste')"
                ),
                {"lote": lote, "execucao": execucao},
            )
            conexao.execute(text("INSERT INTO core.dim_regiao VALUES (99,'TT','Teste')"))
            conexao.execute(text("INSERT INTO core.dim_uf VALUES (99,'TT','Teste',99)"))
            conexao.execute(
                text(
                    "INSERT INTO core.snapshot_localidades VALUES (:snapshot,:checksum,:lote,now())"
                ),
                {"snapshot": snapshot, "checksum": snapshot.hex * 2, "lote": lote},
            )
            for codigo in ("9999998", "9999999"):
                conexao.execute(
                    text(
                        "INSERT INTO core.municipio_snapshot "
                        "VALUES (:snapshot,:codigo,'Teste',99,99)"
                    ),
                    {"snapshot": snapshot, "codigo": codigo},
                )
                conexao.execute(
                    text(
                        "INSERT INTO core.dim_municipio VALUES (:codigo,'Teste',99,true,:snapshot)"
                    ),
                    {"snapshot": snapshot, "codigo": codigo},
                )
            inserir = text(
                "INSERT INTO core.fato_populacao(codigo_ibge,ano,indicador_id,populacao,marcador,"
                "motivo,uf_referencia,regiao_referencia,snapshot_id,lote_id,origem_coletada_em) "
                "VALUES (:codigo,2025,1,:populacao,:marcador,:motivo,99,99,:snapshot,:lote,now())"
            )
            parametros = {
                "codigo": "9999998",
                "populacao": 10,
                "marcador": None,
                "motivo": None,
                "snapshot": snapshot,
                "lote": lote,
            }
            conexao.execute(inserir, parametros)
            for nome in ("uf", "regiao", "brasil"):
                conexao.execute(text(f"REFRESH MATERIALIZED VIEW mart.mv_populacao_{nome}"))
                linha = conexao.execute(
                    text(
                        f"SELECT municipios_esperados,municipios_recebidos,municipios_disponiveis,"
                        "subtotal_disponivel,populacao_total,completo "
                        f"FROM mart.mv_populacao_{nome} "
                        "WHERE snapshot_id=:snapshot"
                    ),
                    {"snapshot": snapshot},
                ).one()
                assert tuple(linha) == (2, 1, 1, 10, None, False)
            for populacao, marcador, motivo in [
                (None, None, None),
                (None, "...", None),
                (None, None, "DADO_NAO_DISPONIVEL"),
                (-1, None, None),
                (10, "...", None),
            ]:
                with pytest.raises(IntegrityError), conexao.begin_nested():
                    conexao.execute(
                        inserir,
                        {
                            **parametros,
                            "codigo": "9999999",
                            "populacao": populacao,
                            "marcador": marcador,
                            "motivo": motivo,
                        },
                    )
            conexao.execute(
                inserir,
                {
                    **parametros,
                    "codigo": "9999999",
                    "populacao": None,
                    "marcador": "...",
                    "motivo": "DADO_NAO_DISPONIVEL",
                },
            )
            with pytest.raises(DBAPIError), conexao.begin_nested():
                conexao.execute(
                    text(
                        "UPDATE core.municipio_snapshot SET nome='Alterado' WHERE snapshot_id=:id"
                    ),
                    {"id": snapshot},
                )
            with pytest.raises(IntegrityError), conexao.begin_nested():
                conexao.execute(
                    text(
                        "UPDATE core.fato_populacao SET snapshot_id=:id WHERE snapshot_id=:snapshot"
                    ),
                    {"id": uuid4(), "snapshot": snapshot},
                )
            conexao.execute(
                text(
                    "UPDATE core.fato_populacao SET populacao=20,marcador=NULL,motivo=NULL "
                    "WHERE codigo_ibge='9999999' AND snapshot_id=:snapshot"
                ),
                {"snapshot": snapshot},
            )
            for nome in ("uf", "regiao", "brasil"):
                conexao.execute(
                    text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY mart.mv_populacao_{nome}")
                )
                assert conexao.execute(
                    text(
                        f"SELECT populacao_total,completo FROM mart.mv_populacao_{nome} "
                        "WHERE snapshot_id=:snapshot"
                    ),
                    {"snapshot": snapshot},
                ).one() == (30, True)
        finally:
            transacao.rollback()
