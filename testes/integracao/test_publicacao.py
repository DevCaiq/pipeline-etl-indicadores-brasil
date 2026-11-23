"""Indicadores NUMERIC e publicação atômica com papéis reais."""

import os
from datetime import date
from decimal import Decimal

import pytest
from pydantic import SecretStr
from sqlalchemy import event, text

from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.processamento.carga import CHAVE_TRAVA_BCB
from pipeline_etl.processamento.publicacao import publicar_bcb

pytestmark = pytest.mark.integracao


@pytest.fixture(autouse=True)
def limpar(banco):
    def limpar():
        with banco.begin() as conexao:
            conexao.execute(text("DELETE FROM core.fato_serie"))
            conexao.execute(text("DELETE FROM ops.publicacao"))

    limpar()
    yield
    limpar()


def inserir(banco, linhas):
    with banco.begin() as conexao:
        execucao = conexao.scalar(
            text("INSERT INTO ops.execucao(modo) VALUES ('teste_gold') RETURNING execucao_id")
        )
        lote = conexao.scalar(
            text(
                "INSERT INTO "
                "ops.lote(execucao_id,fonte,chave,janela_inicio,janela_fim,manifesto) "
                "VALUES (:id,'bcb','teste','2019-02-01','2020-12-31','fixture') RETURNING"
                " lote_id"
            ),
            {"id": execucao},
        )
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) "
                "VALUES(:codigo,:data,:valor,:lote)"
            ),
            [
                {"codigo": codigo, "data": data, "valor": Decimal(valor), "lote": lote}
                for codigo, data, valor in linhas
            ],
        )
        conexao.execute(
            text(
                "INSERT INTO ops.publicacao(dominio,versao_core) VALUES('bcb',1) ON "
                "CONFLICT(dominio) DO UPDATE SET "
                "versao_core=ops.publicacao.versao_core+1,situacao='PENDENTE'"
            )
        )


def test_media_anual_usa_observacoes_e_nao_media_de_medias(banco):
    inserir(
        banco,
        [(432, date(2020, 1, 2), "2"), (432, date(2020, 1, 3), "4"), (432, date(2020, 2, 3), "9")],
    )
    assert publicar_bcb(banco).situacao == "SUCESSO"
    with banco.connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT media,minimo,maximo,ultimo,completo FROM mart.mv_serie_anual "
                "WHERE codigo_sgs=432"
            )
        ).one()
        assert linha.media == 5 and (linha.minimo, linha.maximo, linha.ultimo) == (2, 9, 9)
        assert linha.completo is None


def test_ipca_anual_e_12m_exigem_continuidade_e_apoio(banco):
    linhas = [(433, date(2019, mes, 1), "1") for mes in range(2, 13)]
    linhas += [(433, date(2020, mes, 1), "1") for mes in range(1, 13)]
    inserir(banco, linhas)
    publicar_bcb(banco)
    with banco.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT unidade FROM mart.mv_serie_anual WHERE codigo_sgs=433"))
            == "% no ano"
        )
        assert conexao.scalar(
            text("SELECT variacao FROM mart.mv_serie_anual WHERE codigo_sgs=433")
        ) == Decimal("12.682503013196972066120100")
        assert conexao.scalar(
            text("SELECT variacao FROM mart.mv_ipca_12m WHERE periodo='2020-01-01'")
        ) == Decimal("12.682503013196972066120100")
        assert conexao.scalar(text("SELECT min(periodo) FROM mart.mv_serie_mensal")) == date(
            2020, 1, 1
        )
    with banco.begin() as conexao:
        conexao.execute(text("DELETE FROM core.fato_serie WHERE data='2020-06-01'"))
        conexao.execute(text("UPDATE ops.publicacao SET versao_core=2,situacao='PENDENTE'"))
    publicar_bcb(banco)
    with banco.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT variacao FROM mart.mv_serie_anual WHERE codigo_sgs=433"))
            is None
        )
        assert (
            conexao.scalar(text("SELECT motivo FROM mart.mv_ipca_12m WHERE periodo='2020-12-01'"))
            == "MESES_AUSENTES"
        )


def test_falha_no_segundo_refresh_preserva_gold_e_permite_recuperar(banco):
    inserir(banco, [(1, date(2020, 1, 2), "4")])
    publicar_bcb(banco)
    inserir(banco, [(1, date(2020, 1, 3), "6")])

    def falhar(conexao, cursor, comando, parametros, contexto, muitos):
        if "REFRESH MATERIALIZED VIEW mart.mv_serie_anual" in comando:
            raise RuntimeError("falha simulada")

    event.listen(banco, "before_cursor_execute", falhar)
    try:
        assert publicar_bcb(banco).situacao == "FALHA"
    finally:
        event.remove(banco, "before_cursor_execute", falhar)
    with banco.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT media FROM mart.mv_serie_mensal WHERE codigo_sgs=1")) == 4
        )
        assert conexao.execute(
            text("SELECT versao_core,versao_gold,situacao FROM ops.publicacao")
        ).one() == (2, 1, "PENDENTE")
    assert publicar_bcb(banco).situacao == "SUCESSO"
    with banco.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT media FROM mart.mv_serie_mensal WHERE codigo_sgs=1")) == 5
        )


def test_publicador_real_e_repeticao_sem_regravar(banco):
    inserir(banco, [(432, date(2020, 1, 2), "4.5")])
    senha = os.environ["SENHA_BANCO_PUBLICADOR_TESTES"]
    motor = criar_motor(
        SecretStr(
            banco.url.set(username="publicador", password=senha).render_as_string(
                hide_password=False
            )
        )
    )
    try:
        assert publicar_bcb(motor).situacao == "SUCESSO"
        assert publicar_bcb(motor).situacao == "IGNORADA"
    finally:
        motor.dispose()


def test_trava_e_ausencia_de_core_nao_publicam(banco):
    assert publicar_bcb(banco).motivo == "SEM_GERACAO_CORE"
    inserir(banco, [(432, date(2020, 1, 2), "4.5")])
    with banco.begin() as conexao:
        conexao.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB})
        assert publicar_bcb(banco, espera_trava=0).motivo == "TRAVA_OCUPADA"


def test_periodo_aberto_nao_parece_ano_completo_e_referencia_se_renova(banco):
    with banco.connect() as conexao:
        hoje = conexao.scalar(
            text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date")
        )
    inserir(banco, [(432, hoje, "4"), (433, hoje.replace(day=1), "0.5")])
    publicar_bcb(banco)
    with banco.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT codigo_sgs,parcial,completo,data_referencia "
                "FROM mart.mv_serie_mensal ORDER BY codigo_sgs"
            )
        ).all()
        assert linhas == [(432, True, None, hoje), (433, True, False, hoje)]
        assert (
            conexao.scalar(text("SELECT variacao FROM mart.mv_serie_anual WHERE codigo_sgs=433"))
            is None
        )
    with banco.begin() as conexao:
        conexao.execute(text("UPDATE ops.publicacao SET data_publicacao=data_publicacao-1"))
    resumo = publicar_bcb(banco)
    assert resumo.situacao == "SUCESSO" and resumo.data_publicacao == hoje
    assert resumo.versao_core == resumo.versao_gold == 1


@pytest.mark.parametrize("espera", [-1, float("nan"), float("inf")])
def test_publicacao_rejeita_espera_invalida(banco, espera):
    with pytest.raises(ValueError):
        publicar_bcb(banco, espera_trava=espera)


def test_geracao_zero_e_produto_incompleto(banco):
    with banco.begin() as conexao:
        conexao.execute(text("INSERT INTO ops.publicacao(dominio) VALUES('bcb')"))
        assert conexao.scalar(text("SELECT mart.compor_taxas_bcb(ARRAY[]::numeric[])")) is None
        assert (
            conexao.scalar(text("SELECT mart.compor_taxas_bcb(ARRAY[1,NULL]::numeric[])")) is None
        )
    assert publicar_bcb(banco).motivo == "SEM_GERACAO_CORE"


def test_falha_de_auditoria_dupla_nao_anuncia_sucesso(banco, monkeypatch, capsys):
    from pipeline_etl.processamento import publicacao

    inserir(banco, [(432, date(2020, 1, 2), "4.5")])

    def falhar(*argumentos, **opcoes):
        raise RuntimeError("detalhe-confidencial")

    monkeypatch.setattr(publicacao, "_registrar", falhar)
    resumo = publicacao.publicar_bcb(banco)
    assert resumo.situacao == "FALHA"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT versao_gold FROM ops.publicacao")) == 0
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": resumo.execucao_id},
            )
            == "EM_EXECUCAO"
        )
    saidas = capsys.readouterr()
    assert "detalhe-confidencial" not in saidas.out + saidas.err


def test_cli_publica_com_papel_proprio_e_leitura_nao_pode_promover(banco, monkeypatch, capsys):
    from sqlalchemy.exc import DBAPIError

    from pipeline_etl.comandos import executar

    inserir(banco, [(432, date(2020, 1, 2), "4.5")])
    endereco = banco.url.set(
        username="publicador", password=os.environ["SENHA_BANCO_PUBLICADOR_TESTES"]
    )
    monkeypatch.setenv("URL_BANCO_PUBLICADOR", endereco.render_as_string(hide_password=False))
    assert executar(["publicar", "--dominio", "bcb"]) == 0
    assert "SUCESSO" in capsys.readouterr().out
    assert executar(["publicar", "--dominio", "bcb"]) == 0
    assert "JA_PUBLICADA" in capsys.readouterr().out
    leitura = criar_motor(
        SecretStr(
            banco.url.set(
                username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"]
            ).render_as_string(hide_password=False)
        )
    )
    try:
        with leitura.connect() as conexao:
            assert conexao.scalar(text("SELECT count(*) FROM mart.mv_serie_mensal")) == 1
        with pytest.raises(DBAPIError), leitura.begin() as conexao:
            conexao.execute(text("REFRESH MATERIALIZED VIEW mart.mv_serie_mensal"))
    finally:
        leitura.dispose()
    with banco.connect() as conexao:
        assert not conexao.scalar(
            text("SELECT has_table_privilege('publicador','core.fato_serie','UPDATE')")
        )
        assert not conexao.scalar(
            text("SELECT has_table_privilege('processamento','mart.mv_serie_mensal','UPDATE')")
        )
    monkeypatch.setenv(
        "URL_BANCO_PUBLICADOR", "postgresql+psycopg://teste:segredo@127.0.0.1:1/etl_testes"
    )
    assert executar(["publicar", "--dominio", "bcb"]) == 1
    assert "segredo" not in capsys.readouterr().err


def test_refresh_reconstroi_data_de_referencia_arquivada(banco):
    inserir(banco, [(1, date(2020, 1, 2), "4")])
    assert publicar_bcb(banco).situacao == "SUCESSO"
    with banco.begin() as conexao:
        conexao.execute(
            text("UPDATE ops.publicacao SET data_publicacao=DATE '2020-01-15' WHERE dominio='bcb'")
        )
        # Equivale à recomputação feita pelo pg_restore, sem mudar o relógio do banco.
        for nome in ("mv_serie_mensal", "mv_serie_anual", "mv_ipca_12m"):
            conexao.execute(text(f"REFRESH MATERIALIZED VIEW mart.{nome}"))
        linha = conexao.execute(
            text("SELECT data_referencia,parcial FROM mart.mv_serie_mensal WHERE codigo_sgs=1")
        ).one()
        assert linha.data_referencia == date(2020, 1, 15)
        assert linha.parcial is True


def test_publicacao_avanca_referencia_duravel_na_mesma_transacao(banco):
    inserir(banco, [(1, date(2020, 1, 2), "4")])
    with banco.begin() as conexao:
        conexao.execute(
            text("UPDATE ops.publicacao SET data_publicacao=DATE '2020-01-15' WHERE dominio='bcb'")
        )
    assert publicar_bcb(banco).situacao == "SUCESSO"
    with banco.connect() as conexao:
        hoje = conexao.scalar(
            text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date")
        )
        referencia = conexao.scalar(
            text("SELECT data_referencia FROM mart.mv_serie_mensal WHERE codigo_sgs=1")
        )
        assert referencia == hoje
        assert (
            conexao.scalar(text("SELECT data_publicacao FROM ops.publicacao WHERE dominio='bcb'"))
            == hoje
        )


def test_falha_refresh_reverte_avanco_da_referencia_duravel(banco):
    inserir(banco, [(1, date(2020, 1, 2), "4")])
    assert publicar_bcb(banco).situacao == "SUCESSO"
    with banco.begin() as conexao:
        conexao.execute(
            text("UPDATE ops.publicacao SET data_publicacao=DATE '2020-01-15' WHERE dominio='bcb'")
        )
        conexao.execute(text("REFRESH MATERIALIZED VIEW mart.mv_serie_mensal"))

    def falhar(conexao, cursor, comando, parametros, contexto, multiplas):
        if comando == "REFRESH MATERIALIZED VIEW mart.mv_serie_anual":
            raise RuntimeError("Falha simulada entre materializadas.")

    event.listen(banco, "before_cursor_execute", falhar)
    try:
        assert publicar_bcb(banco).situacao == "FALHA"
    finally:
        event.remove(banco, "before_cursor_execute", falhar)
    with banco.connect() as conexao:
        assert conexao.scalar(
            text("SELECT data_publicacao FROM ops.publicacao WHERE dominio='bcb'")
        ) == date(2020, 1, 15)
        assert conexao.scalar(
            text("SELECT data_referencia FROM mart.mv_serie_mensal WHERE codigo_sgs=1")
        ) == date(2020, 1, 15)


def test_migracao_referencia_recusa_core_pendente_sem_trocar_gold(banco):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    inserir(banco, [(1, date(2020, 1, 2), "4")])
    assert publicar_bcb(banco).situacao == "SUCESSO"
    inserir(banco, [(1, date(2020, 1, 3), "8")])
    caminho = Path(__file__).resolve().parents[2] / "migracoes/versions/0010_referencia_duravel.py"
    especificacao = importlib.util.spec_from_file_location("migracao_referencia", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    with banco.begin() as conexao:
        antes = conexao.execute(
            text("SELECT to_jsonb(t) FROM mart.mv_serie_mensal t ORDER BY 1::text")
        ).all()
        with (
            Operations.context(MigrationContext.configure(conexao)),
            pytest.raises(RuntimeError, match="publicação BCB pendente"),
        ):
            modulo.upgrade()
        assert (
            conexao.execute(
                text("SELECT to_jsonb(t) FROM mart.mv_serie_mensal t ORDER BY 1::text")
            ).all()
            == antes
        )
        assert (
            conexao.scalar(text("SELECT versao_gold FROM ops.publicacao WHERE dominio='bcb'")) == 1
        )


def test_migracao_referencia_respeita_trava_da_carga(banco):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    inserir(banco, [(1, date(2020, 1, 2), "4")])
    assert publicar_bcb(banco).situacao == "SUCESSO"
    caminho = Path(__file__).resolve().parents[2] / "migracoes/versions/0010_referencia_duravel.py"
    especificacao = importlib.util.spec_from_file_location("migracao_referencia_trava", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    with banco.begin() as ocupada:
        ocupada.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB})
        with banco.begin() as conexao:
            with (
                Operations.context(MigrationContext.configure(conexao)),
                pytest.raises(RuntimeError, match="em andamento"),
            ):
                modulo.upgrade()
            assert conexao.scalar(text("SELECT count(*) FROM mart.mv_serie_mensal")) == 1
