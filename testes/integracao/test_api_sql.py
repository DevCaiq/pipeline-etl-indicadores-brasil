"""API com papel api_leitura, PostgreSQL real e transporte ASGI sem rede externa."""

import os
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, text

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.api.erros import ErroAPI
from pipeline_etl.api.repositorio import RepositorioLeitura
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.publicacao import publicar_bcb

pytestmark = pytest.mark.integracao


@pytest.fixture
def api(banco):
    with banco.begin() as conexao:
        conexao.execute(text("DELETE FROM core.fato_serie"))
        conexao.execute(text("DELETE FROM ops.publicacao"))
        execucao = conexao.scalar(
            text(
                "INSERT INTO ops.execucao(modo,erro,parametros) "
                "VALUES('carga_bcb','segredo-interno','{\"senha\":\"nao-expor\"}'::jsonb) "
                "RETURNING execucao_id"
            )
        )
        lote = conexao.scalar(
            text(
                "INSERT INTO "
                "ops.lote(execucao_id,fonte,chave,janela_inicio,janela_fim,manifesto) "
                "VALUES(:id,'bcb','432','2020-01-01','2020-01-31','arquivo-privado') "
                "RETURNING lote_id"
            ),
            {"id": execucao},
        )
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) "
                "VALUES(432,:data,:valor,:lote)"
            ),
            [
                {"data": date(2020, 1, dia), "valor": Decimal(valor), "lote": lote}
                for dia, valor in [(2, "4.1234565"), (3, "4.5"), (6, "5")]
            ],
        )
        conexao.execute(text("INSERT INTO ops.publicacao(dominio,versao_core) VALUES('bcb',1)"))
    endereco = banco.url.set(username="api_leitura", password=os.environ["SENHA_BANCO_API_TESTES"])
    motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
    configuracao = ConfiguracaoAplicacao(
        segredo_cursor=SecretStr("s" * 48), limite_requisicoes_minuto=10000
    )
    try:
        with TestClient(criar_aplicacao(configuracao, motor)) as cliente:
            yield cliente, motor
    finally:
        motor.dispose()
        with banco.begin() as conexao:
            conexao.execute(text("DELETE FROM core.fato_serie"))
            conexao.execute(text("DELETE FROM ops.publicacao"))


@pytest.mark.parametrize("codigo", [1, 432, 433, 999])
def test_resolver_serie_limita_linhas_sem_alterar_contrato(api, codigo):
    _, motor = api
    repositorio = RepositorioLeitura(motor, b"s" * 48)
    with repositorio.instantaneo() as conexao:
        referencia = next(
            (serie for serie in repositorio.catalogo(conexao) if serie.codigo == codigo), None
        )
        contagens = []

        def observar(conexao, cursor, comando, parametros, contexto, varios):
            if comando.lstrip().upper().startswith("SELECT"):
                contagens.append(cursor.rowcount)

        event.listen(motor, "after_cursor_execute", observar)
        try:
            if referencia is not None:
                assert repositorio.serie(conexao, codigo) == referencia
            else:
                with pytest.raises(ErroAPI) as erro:
                    repositorio.serie(conexao, codigo)
                assert erro.value.status == 404
        finally:
            event.remove(motor, "after_cursor_execute", observar)
        assert contagens == [1 if referencia is not None else 0]


def test_catalogo_observacoes_e_etag(api):
    cliente, motor = api
    assert cliente.get("/ready").status_code == 200
    catalogo = cliente.get("/api/v1/series")
    assert len(catalogo.json()["data"]) == 3
    assert cliente.get("/api/v1/series/999").status_code == 404
    detalhe = cliente.get("/api/v1/series/432").json()["data"]
    assert detalhe["cobertura"]["observacoes"] == 3
    primeira = cliente.get("/api/v1/series/432/observacoes", params={"limite": 2})
    assert primeira.status_code == 200, primeira.text
    corpo = primeira.json()
    assert corpo["data"][0] == {"data": "2020-01-02", "valor": "4.123456"}
    cursor = corpo["pagina"]["proximo_cursor"]
    proxima = cliente.get("/api/v1/series/432/observacoes", params={"limite": 2, "cursor": cursor})
    assert proxima.json()["data"] == [{"data": "2020-01-06", "valor": "5.000000"}]
    assert not proxima.json()["pagina"]["tem_mais"]
    assert (
        cliente.get(
            "/api/v1/series/1/observacoes", params={"limite": 2, "cursor": cursor}
        ).status_code
        == 422
    )
    completa = cliente.get("/api/v1/series/432/observacoes")
    assert (
        cliente.get(
            "/api/v1/series/432/observacoes", headers={"If-None-Match": completa.headers["ETag"]}
        ).status_code
        == 304
    )
    assert cliente.get("/api/v1/series/1/observacoes").json()["data"] == []


def test_gold_vazia_publicacao_pendente_e_cursor_expira(api, banco):
    cliente, _ = api
    vazia = cliente.get("/api/v1/series/432/agregados")
    assert vazia.status_code == 200 and vazia.json()["data"] == []
    assert vazia.json()["meta"]["motivo"] == "GOLD_NAO_PUBLICADA"
    publicar_bcb(banco)
    for granularidade in ["mes", "ano"]:
        resposta = cliente.get(
            "/api/v1/series/432/agregados", params={"granularidade": granularidade}
        )
        assert resposta.status_code == 200, resposta.text
        assert len(resposta.json()["data"]) == 1
        assert resposta.json()["data"][0]["completo"] is None
    assert cliente.get("/api/v1/indicadores/ipca-12m").json()["data"] == []
    primeira = cliente.get("/api/v1/series/432/observacoes", params={"limite": 1}).json()
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) SELECT "
                "432,'2021-01-04',5,lote_id FROM core.fato_serie LIMIT 1"
            )
        )
        conexao.execute(text("UPDATE ops.publicacao SET versao_core=2,situacao='PENDENTE'"))
    assert (
        cliente.get(
            "/api/v1/series/432/observacoes",
            params={"limite": 1, "cursor": primeira["pagina"]["proximo_cursor"]},
        ).status_code
        == 409
    )
    pendente = cliente.get("/api/v1/series/432/agregados").json()
    assert len(pendente["data"]) == 1 and pendente["meta"]["desatualizado"]
    assert pendente["meta"]["cobertura"]["fim"] == "2020-01-01"
    assert pendente["meta"]["cobertura"]["unidade_contagem"] == "periodos"


def test_historico_sanitizado_frescor_e_instantaneo_so_leitura(api):
    cliente, motor = api
    comandos = []

    def observar(conexao, cursor, comando, parametros, contexto, muitos):
        comandos.append(comando)

    event.listen(motor, "before_cursor_execute", observar)
    try:
        resposta = cliente.get("/api/v1/pipeline/execucoes", params={"limite": 1})
        assert resposta.status_code == 200, resposta.text
        cursor = resposta.json()["pagina"]["proximo_cursor"]
        assert cursor
        assert (
            cliente.get(
                "/api/v1/pipeline/execucoes", params={"limite": 1, "cursor": cursor}
            ).status_code
            == 200
        )
        assert "segredo-interno" not in resposta.text and "nao-expor" not in resposta.text
        assert resposta.json()["data"][0]["iniciado_em"].endswith("Z")
        assert resposta.headers["Cache-Control"] == "no-store"
        frescor = cliente.get("/api/v1/pipeline/frescor")
        assert frescor.status_code == 200 and len(frescor.json()["data"]) == 3
        assert any("SET TRANSACTION READ ONLY" in comando for comando in comandos)
    finally:
        event.remove(motor, "before_cursor_execute", observar)


@pytest.mark.parametrize(
    "consulta",
    [
        "de=2019-01-01",
        "ate=2099-01-01",
        "de=2021-01-02&ate=2020-01-01",
        "limite=0",
        "limite=1001",
        "cursor=INVALIDO",
        "extra=segredo",
    ],
)
def test_filtros_invalidos_sem_vazamento(api, consulta):
    cliente, _ = api
    resposta = cliente.get("/api/v1/series/432/observacoes?" + consulta)
    assert resposta.status_code == 422
    assert "segredo" not in resposta.text
    assert "erro" in resposta.json()


def test_api_nao_registra_escrita_e_documenta_rotas(api):
    cliente, _ = api
    assert cliente.post("/api/v1/series").status_code == 405
    assert cliente.get("/rota-inexistente").status_code == 404
    documento = cliente.get("/openapi.json").json()
    for rota in documento["paths"].values():
        assert set(rota) == {"get"}
        assert "examples" in rota["get"]["responses"]["200"]["content"]["application/json"]


def test_geracao_e_linhas_permanecem_no_mesmo_instantaneo(api, banco):
    cliente, motor = api
    alterado = False

    def alterar(conexao, cursor, comando, parametros, contexto, muitos):
        nonlocal alterado
        if "FROM ops.v_publicacao_api" in comando and not alterado:
            alterado = True
            with banco.begin() as escrita:
                escrita.execute(
                    text(
                        "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) SELECT "
                        "432,'2020-02-03',6,lote_id FROM core.fato_serie LIMIT 1"
                    )
                )
                escrita.execute(text("UPDATE ops.publicacao SET versao_core=2,situacao='PENDENTE'"))

    event.listen(motor, "after_cursor_execute", alterar)
    try:
        primeira = cliente.get("/api/v1/series/432/observacoes").json()
    finally:
        event.remove(motor, "after_cursor_execute", alterar)
    assert primeira["meta"]["versao_core"] == 1 and len(primeira["data"]) == 3
    segunda = cliente.get("/api/v1/series/432/observacoes").json()
    assert segunda["meta"]["versao_core"] == 2 and len(segunda["data"]) == 4
    from pipeline_etl.api.repositorio import RepositorioLeitura

    with RepositorioLeitura(motor, b"s" * 48).instantaneo() as conexao:
        assert conexao.scalar(text("SHOW transaction_read_only")) == "on"
        assert conexao.scalar(text("SHOW transaction_isolation")) == "repeatable read"


def test_gold_paginada_ipca_incompleto_e_historico_com_teto(api, banco):
    cliente, _ = api
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) SELECT "
                "432,'2020-02-03',6,lote_id FROM core.fato_serie LIMIT 1"
            )
        )
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) SELECT "
                "433,'2020-01-01',0.2,lote_id FROM core.fato_serie LIMIT 1"
            )
        )
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) SELECT "
                "433,'2020-02-01',-0.1,lote_id FROM core.fato_serie LIMIT 1"
            )
        )
    publicar_bcb(banco)
    primeira = cliente.get("/api/v1/series/432/agregados", params={"limite": 1}).json()
    cursor = primeira["pagina"]["proximo_cursor"]
    assert cursor
    assert (
        cliente.get("/api/v1/series/432/agregados", params={"limite": 1, "cursor": cursor}).json()[
            "data"
        ][0]["periodo"]
        == "2020-02-01"
    )
    ipca = cliente.get("/api/v1/indicadores/ipca-12m", params={"limite": 1}).json()
    assert ipca["data"][0]["variacao"] is None and not ipca["data"][0]["completo"]
    assert ipca["pagina"]["proximo_cursor"]
    assert (
        cliente.get(
            "/api/v1/indicadores/ipca-12m",
            params={"limite": 1, "cursor": ipca["pagina"]["proximo_cursor"]},
        ).status_code
        == 200
    )
    historico = cliente.get(
        "/api/v1/pipeline/execucoes",
        params={"limite": 1, "fonte": "bcb", "situacao": "EM_EXECUCAO"},
    ).json()
    with banco.begin() as conexao:
        novo = conexao.scalar(
            text("INSERT INTO ops.execucao(modo) VALUES('carga_bcb') RETURNING execucao_id")
        )
    # O teto temporal é mantido nos cursores; a nova execução só aparece ao reiniciar.
    if historico["pagina"]["proximo_cursor"]:
        proxima = cliente.get(
            "/api/v1/pipeline/execucoes",
            params={
                "limite": 1,
                "fonte": "bcb",
                "situacao": "EM_EXECUCAO",
                "cursor": historico["pagina"]["proximo_cursor"],
            },
        ).json()
        assert str(novo) not in {item["execucao_id"] for item in proxima["data"]}


def test_gold_protege_leitura_antes_do_refresh_e_libera_depois(api, banco):
    cliente, motor = api
    publicar_bcb(banco)
    tentativas = []
    alterado = False

    def alterar(conexao, cursor, comando, parametros, contexto, muitos):
        nonlocal alterado
        if "FROM ops.v_publicacao_api" in comando and not alterado:
            alterado = True
            with banco.begin() as escrita:
                escrita.execute(
                    text(
                        "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) SELECT "
                        "432,'2020-02-03',6,lote_id FROM core.fato_serie LIMIT 1"
                    )
                )
                escrita.execute(text("UPDATE ops.publicacao SET versao_core=2,situacao='PENDENTE'"))
            tentativas.append(publicar_bcb(banco, espera_trava=0))

    event.listen(motor, "after_cursor_execute", alterar)
    try:
        resposta = cliente.get("/api/v1/series/432/agregados")
    finally:
        event.remove(motor, "after_cursor_execute", alterar)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["meta"]["versao_gold"] == 1
    assert sum(item["observacoes"] for item in resposta.json()["data"]) == 3
    assert tentativas[0].motivo == "TRAVA_OCUPADA"
    assert publicar_bcb(banco).situacao == "SUCESSO"
    atual = cliente.get("/api/v1/series/432/agregados").json()
    assert (
        atual["meta"]["versao_gold"] == 2
        and sum(item["observacoes"] for item in atual["data"]) == 4
    )


def test_chaves_de_cursor_assinadas_invalidas_sao_422(api):
    from pipeline_etl.api.cursores import assinar_cursor, resumir_filtros
    from pipeline_etl.api.filtros import FiltrosExecucoes, FiltrosPeriodo

    cliente, _ = api
    identidade = resumir_filtros(FiltrosPeriodo(limite=1).model_dump(exclude={"cursor"}))
    for chaves, teto in [
        (["invalida"], None),
        (["2020-01-02", "extra"], None),
        (["2019-01-01"], None),
        (["2020-01-02"], "teto"),
    ]:
        token = assinar_cursor(
            b"s" * 48, "observacoes:432", identidade, "core:1", chaves, teto=teto
        )
        assert (
            cliente.get(
                "/api/v1/series/432/observacoes", params={"limite": 1, "cursor": token}
            ).status_code
            == 422
        )
    identidade = resumir_filtros(FiltrosExecucoes(limite=1).model_dump(exclude={"cursor"}))
    for chaves, teto in [
        (["invalido"], "2026-01-01T00:00:00Z"),
        (["2020-01-01T00:00:00", "nao-uuid"], "2026-01-01T00:00:00Z"),
        (["2020-01-01T00:00:00", "00000000-0000-0000-0000-000000000001"], "2026-01-01T00:00:00"),
    ]:
        token = assinar_cursor(
            b"s" * 48, "execucoes", identidade, "historico-v1", chaves, teto=teto
        )
        assert (
            cliente.get(
                "/api/v1/pipeline/execucoes", params={"limite": 1, "cursor": token}
            ).status_code
            == 422
        )


def test_gold_tem_espera_limitada_e_nao_deixa_trava_no_pool(api, banco):
    from pipeline_etl.processamento.carga import CHAVE_TRAVA_BCB

    cliente, _ = api
    publicar_bcb(banco)
    with banco.begin() as conexao:
        conexao.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB})
        resposta = cliente.get("/api/v1/series/432/agregados")
        assert (
            resposta.status_code == 503
            and resposta.json()["erro"]["codigo"] == "PUBLICACAO_OCUPADA"
        )
    assert cliente.get("/api/v1/series/432/agregados").status_code == 200
    assert publicar_bcb(banco, espera_trava=0).motivo == "JA_PUBLICADA"


def test_visoes_publicas_nao_permitam_escrita_herdada_no_esquema(banco):
    with banco.connect() as conexao:
        for papel in ["api_leitura", "processamento"]:
            for visao in ["v_esquema_api", "v_publicacao_api", "v_execucoes_api", "v_frescor_api"]:
                for privilegio in ["INSERT", "UPDATE", "DELETE"]:
                    assert not conexao.scalar(
                        text("SELECT has_table_privilege(:papel,:relacao,:privilegio)"),
                        {"papel": papel, "relacao": "ops." + visao, "privilegio": privilegio},
                    )


def test_falha_apos_adquirir_trava_nao_retorna_sessao_presa_ao_pool(api, banco):
    cliente, motor = api
    publicar_bcb(banco)

    def interromper(conexao, cursor, comando, parametros, contexto, muitos):
        if "pg_try_advisory_lock_shared" in comando:
            raise RuntimeError("Falha após resposta do banco")

    event.listen(motor, "after_cursor_execute", interromper)
    try:
        assert cliente.get("/api/v1/series/432/agregados").status_code == 500
    finally:
        event.remove(motor, "after_cursor_execute", interromper)
    assert publicar_bcb(banco, espera_trava=0).motivo == "JA_PUBLICADA"


def test_frescor_ipca_expoe_calendario_sem_homologar_cobertura(api, banco, monkeypatch):
    cliente, _ = api
    monkeypatch.setattr("pipeline_etl.api.repositorio.hoje_brasil", lambda: date(2026, 11, 18))
    with banco.begin() as conexao:
        lote = conexao.scalar(text("SELECT lote_id FROM core.fato_serie LIMIT 1"))
        conexao.execute(
            text(
                "INSERT INTO core.fato_serie(codigo_sgs,data,valor,lote_id) "
                "VALUES(433,'2026-10-01',0.14,:lote)"
            ),
            {"lote": lote},
        )
    resposta = cliente.get("/api/v1/pipeline/frescor")
    assert resposta.status_code == 200
    ipca = next(item for item in resposta.json()["data"] if item["codigo"] == 433)
    assert ipca["defasado"] is False
    assert ipca["politica"] == "CALENDARIO_IBGE" and ipca["calendario_homologado"] is True
    assert ipca["referencia_esperada"] == "2026-10-01"
    assert ipca["data_limite"] == "2026-11-13"
    assert ipca["versao_calendario"].startswith("ibge-ipca-20261118-")
    assert ipca["cobertura"]["completa"] is None
    assert ipca["cobertura"]["motivo"] == "CALENDARIO_NAO_HOMOLOGADO"
    monkeypatch.setattr("pipeline_etl.api.repositorio.hoje_brasil", lambda: date(2026, 12, 19))
    ipca = next(
        item
        for item in cliente.get("/api/v1/pipeline/frescor").json()["data"]
        if item["codigo"] == 433
    )
    assert ipca["politica"] == "HEURISTICA_45_DIAS"
    assert ipca["calendario_homologado"] is False and ipca["motivo"] == "CALENDARIO_EXPIRADO"
    assert ipca["versao_calendario"] is None
