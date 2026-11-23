"""Atomicidade e publicação defensiva em PostgreSQL exclusivo."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

from pipeline_etl.processamento.carga_ibge import carregar_ibge, publicar_ibge

pytestmark = pytest.mark.integracao

ESPECIFICACAO = importlib.util.spec_from_file_location(
    "apoio_carga_ibge_limites", Path(__file__).with_name("test_carga_ibge.py")
)
assert ESPECIFICACAO is not None and ESPECIFICACAO.loader is not None
APOIO = importlib.util.module_from_spec(ESPECIFICACAO)
ESPECIFICACAO.loader.exec_module(APOIO)


@pytest.fixture(autouse=True)
def limpar(banco):
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "TRUNCATE core.fato_populacao,core.dim_municipio,core.municipio_snapshot,"
                "core.snapshot_localidades,core.dim_uf,core.dim_regiao CASCADE"
            )
        )
        conexao.execute(text("DELETE FROM ops.publicacao WHERE dominio='ibge'"))
        conexao.execute(text("DELETE FROM ops.lote WHERE fonte='ibge'"))


@pytest.mark.parametrize("mutacao", ["duplicado", "incompleto", "sem_populacao"])
def test_pacote_invalido_nao_promove_dimensoes_nem_checkpoint(banco, tmp_path, mutacao):
    armazenamento, manifestos = APOIO.preparar(tmp_path)
    if mutacao == "duplicado":
        manifestos = (*manifestos, manifestos[0])
    elif mutacao == "incompleto":
        manifestos = manifestos[1:]
    else:
        manifestos = manifestos[:5]
    resumo = carregar_ibge(armazenamento, manifestos, banco)
    assert resumo.situacao == "FALHA"
    with banco.connect() as conexao:
        for tabela in ("core.dim_municipio", "core.fato_populacao", "core.snapshot_localidades"):
            assert conexao.scalar(text(f"SELECT count(*) FROM {tabela}")) == 0
        assert conexao.scalar(text("SELECT count(*) FROM ops.lote WHERE fonte='ibge'")) == 0
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": resumo.execucao_id},
            )
            == "FALHA"
        )


def test_publicacao_sem_core_nao_inventa_geracao(banco):
    resumo = publicar_ibge(banco)
    assert resumo.situacao == "IGNORADA"
    assert resumo.motivo == "SEM_GERACAO_CORE"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM ops.publicacao WHERE dominio='ibge'")) == 0


def test_publicacao_recusa_denominador_territorial_incompleto(banco, tmp_path):
    armazenamento, manifestos = APOIO.preparar(tmp_path)
    assert carregar_ibge(armazenamento, manifestos, banco).situacao == "SUCESSO"
    # Corrupção sintética administrativa: acrescenta membro sem fato populacional.
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO core.municipio_snapshot "
                "SELECT snapshot_id,'9999999',nome,uf_codigo,regiao_codigo "
                "FROM core.municipio_snapshot"
            )
        )
    resumo = publicar_ibge(banco)
    assert resumo.situacao == "FALHA"
    with banco.connect() as conexao:
        assert conexao.execute(
            text("SELECT versao_core,versao_gold,situacao FROM ops.publicacao WHERE dominio='ibge'")
        ).one() == (1, 0, "PENDENTE")
