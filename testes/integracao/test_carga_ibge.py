"""Carga IBGE offline com amostras oficiais e PostgreSQL exclusivo."""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from pipeline_etl.processamento.armazenamento.objetos import SistemaArquivosObjetos
from pipeline_etl.processamento.carga_ibge import carregar_ibge, publicar_ibge
from pipeline_etl.processamento.clientes.ibge import ClienteIBGE

pytestmark = pytest.mark.integracao
AMOSTRAS = Path(__file__).resolve().parents[1] / "amostras" / "ibge"


def test_coordenador_ibge_vincula_auditoria_e_incremental_revisa_ultimo(banco, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from pipeline_etl.processamento.clientes.ibge import ler_coleta
    from pipeline_etl.processamento.pipeline_ibge import executar_ibge_coordenado

    armazenamento, manifestos = preparar(tmp_path)
    recursos = {
        (coleta.recurso, coleta.ano): manifesto
        for manifesto in manifestos
        for coleta in [ler_coleta(armazenamento, manifesto)]
    }
    coletor = Mock()
    coletor.coletar.side_effect = lambda recurso, ano=None: SimpleNamespace(
        situacao="COLETADA", manifesto=recursos[recurso, ano]
    )
    completo = executar_ibge_coordenado(coletor, armazenamento, banco, banco, "reconciliacao")
    assert completo.situacao == "SUCESSO"
    with banco.connect() as conexao:
        pai = conexao.execute(
            text("SELECT situacao,parametros FROM ops.execucao WHERE execucao_id=:id"),
            {"id": completo.execucao_id},
        ).one()
        assert pai.situacao == "SUCESSO" and len(pai.parametros["manifestos"]) == 10
        assert (
            conexao.scalar(
                text("SELECT count(*) FROM ops.execucao WHERE parametros->>'pai_pipeline_id'=:pai"),
                {"pai": str(completo.execucao_id)},
            )
            == 2
        )
    coletor.reset_mock()
    incremental = executar_ibge_coordenado(coletor, armazenamento, banco, banco, "incremental")
    assert incremental.situacao == "SUCESSO" and incremental.anos == (2026,)
    assert len(incremental.manifestos) == 6
    assert [
        chamada.args[1]
        for chamada in coletor.coletar.call_args_list
        if chamada.args[0] == "populacao"
    ] == [2026]


def test_falha_coleta_fica_auditada_sem_promocao(banco, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from pipeline_etl.processamento.pipeline_ibge import executar_ibge_coordenado

    armazenamento, manifestos = preparar(tmp_path)
    coletor = Mock()
    coletor.coletar.return_value = SimpleNamespace(situacao="FALHA", manifesto=manifestos[0])
    resumo = executar_ibge_coordenado(coletor, armazenamento, banco, banco)
    assert resumo.situacao == "FALHA"
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": resumo.execucao_id},
            )
            == "FALHA"
        )
        assert conexao.scalar(text("SELECT count(*) FROM core.fato_populacao")) == 0


def test_publicacao_coordenada_nao_faz_coleta(banco, tmp_path):
    from unittest.mock import Mock

    from pipeline_etl.processamento.pipeline_ibge import executar_ibge_coordenado

    armazenamento, manifestos = preparar(tmp_path)
    assert carregar_ibge(armazenamento, manifestos, banco).situacao == "SUCESSO"
    coletor = Mock()
    resumo = executar_ibge_coordenado(coletor, armazenamento, banco, banco, "publicacao")
    assert resumo.situacao == "SUCESSO"
    coletor.coletar.assert_not_called()


def preparar(tmp_path, marcador=None):
    corpos = {
        nome: (AMOSTRAS / (arquivo + ".body")).read_bytes()
        for nome, arquivo in {
            "regioes": "regioes",
            "ufs": "estados",
            "metadados": "metadados",
            "periodos": "periodos",
        }.items()
    }
    corpos["municipios"] = (
        b"[" + (AMOSTRAS / "municipio_hierarquia_opcional.body").read_bytes() + b"]"
    )
    populacao = json.loads((AMOSTRAS / "populacao_marcador.body").read_bytes())
    serie = populacao[0]["resultados"][0]["series"][0]["serie"]
    anos = tuple(map(int, serie))
    for ano in anos:
        copia = json.loads(json.dumps(populacao))
        copia[0]["resultados"][0]["series"][0]["serie"] = {str(ano): marcador or serie[str(ano)]}
        corpos[str(ano)] = json.dumps(copia).encode()

    def responder(requisicao):
        partes = requisicao.url.path.split("/")
        chave = partes[-1]
        if chave == "estados":
            chave = "ufs"
        if chave == "9324":
            chave = partes[-3]
        return httpx.Response(
            200,
            stream=httpx.ByteStream(corpos[chave]),
            headers={"Content-Type": "application/json"},
        )

    armazenamento = SistemaArquivosObjetos(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = ClienteIBGE(transporte, armazenamento, dormir=lambda _: None)
        manifestos = tuple(
            cliente.coletar(recurso).manifesto
            for recurso in ("regioes", "ufs", "municipios", "metadados", "periodos")
        )
        manifestos += tuple(cliente.coletar("populacao", ano).manifesto for ano in anos)
    return armazenamento, manifestos


@pytest.fixture(autouse=True)
def limpar(banco):
    with banco.begin() as conexao:
        conexao.execute(
            text(
                "TRUNCATE "
                "core.fato_populacao,core.dim_municipio,core.municipio_snapshot,"
                "core.snapshot_localidades,core.dim_uf,core.dim_regiao CASCADE"
            )
        )
        conexao.execute(text("DELETE FROM ops.publicacao WHERE dominio='ibge'"))
        conexao.execute(text("DELETE FROM ops.lote WHERE fonte='ibge'"))
    yield


def test_carga_idempotente_e_publicacao_com_ausencia(banco, tmp_path):
    armazenamento, manifestos = preparar(tmp_path)
    primeira = carregar_ibge(armazenamento, manifestos, banco)
    assert primeira.situacao == "SUCESSO"
    assert primeira.inseridas == 5
    with banco.connect() as conexao:
        antes = conexao.execute(text("SELECT * FROM core.fato_populacao ORDER BY ano")).all()
    segunda = carregar_ibge(armazenamento, manifestos, banco)
    assert segunda.inalteradas == 5
    assert segunda.snapshot_id == primeira.snapshot_id
    with banco.connect() as conexao:
        assert (
            conexao.execute(text("SELECT * FROM core.fato_populacao ORDER BY ano")).all() == antes
        )
        assert (
            conexao.scalar(text("SELECT versao_core FROM ops.publicacao WHERE dominio='ibge'")) == 1
        )
    assert publicar_ibge(banco).situacao == "SUCESSO"
    assert publicar_ibge(banco).motivo == "JA_PUBLICADA"
    with banco.connect() as conexao:
        assert conexao.execute(
            text(
                "SELECT subtotal_disponivel,populacao_total,completo FROM "
                "mart.mv_populacao_brasil WHERE ano=2020"
            )
        ).one() == (None, None, False)
        assert conexao.execute(
            text("SELECT populacao_total,completo FROM mart.mv_populacao_brasil WHERE ano=2025")
        ).one() == (5877, True)


def test_marcador_desconhecido_rejeita_lote_inteiro(banco, tmp_path):
    armazenamento, manifestos = preparar(tmp_path, "x")
    assert carregar_ibge(armazenamento, manifestos, banco).situacao == "FALHA"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM core.fato_populacao")) == 0
        assert (
            conexao.scalar(
                text(
                    "SELECT count(*) FROM ops.quarentena q JOIN ops.etapa e USING(etapa_id) "
                    "WHERE e.fonte='ibge'"
                )
            )
            > 0
        )


def test_bronze_antigo_divergente_preserva_fatos(banco, tmp_path):
    antigo, manifestos_antigos = preparar(tmp_path / "antigo", "100")
    atual, manifestos_atuais = preparar(tmp_path / "atual")
    assert carregar_ibge(atual, manifestos_atuais, banco).situacao == "SUCESSO"
    resumo = carregar_ibge(antigo, manifestos_antigos, banco)
    assert resumo.situacao == "FALHA"
    assert resumo.motivo == "BRONZE_ANTIGO_DIVERGENTE"
    with banco.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT populacao FROM core.fato_populacao WHERE ano=2025")) == 5877
        )


def test_falha_refresh_preserva_gold_anterior(banco, tmp_path):
    from sqlalchemy import event

    armazenamento, manifestos = preparar(tmp_path / "primeiro")
    assert carregar_ibge(armazenamento, manifestos, banco).situacao == "SUCESSO"
    assert publicar_ibge(banco).situacao == "SUCESSO"
    armazenamento, manifestos = preparar(tmp_path / "segundo", "123")
    assert carregar_ibge(armazenamento, manifestos, banco).situacao == "SUCESSO"

    def falhar(conexao, cursor, comando, parametros, contexto, varios):
        if comando == "REFRESH MATERIALIZED VIEW mart.mv_populacao_regiao":
            raise RuntimeError("Falha simulada após primeiro refresh")

    event.listen(banco, "before_cursor_execute", falhar)
    try:
        assert publicar_ibge(banco).situacao == "FALHA"
    finally:
        event.remove(banco, "before_cursor_execute", falhar)
    with banco.connect() as conexao:
        assert conexao.execute(
            text("SELECT versao_core,versao_gold,situacao FROM ops.publicacao WHERE dominio='ibge'")
        ).one() == (2, 1, "PENDENTE")
        assert (
            conexao.scalar(text("SELECT populacao_total FROM mart.mv_populacao_uf WHERE ano=2025"))
            == 5877
        )


def test_snapshot_novo_preserva_membros_anteriores(banco, tmp_path):
    armazenamento, manifestos = preparar(tmp_path / "anterior")
    primeiro = carregar_ibge(armazenamento, manifestos, banco)
    assert primeiro.situacao == "SUCESSO"
    armazenamento, manifestos = preparar(tmp_path / "atual")
    # Variação sintética explicitamente isolada, sem alterar amostras oficiais.
    from pipeline_etl.processamento.clientes.ibge import ler_coleta

    coleta = ler_coleta(armazenamento, manifestos[2])
    municipios = json.loads(coleta.corpo)
    municipios[0]["nome"] += " (variante de teste)"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda requisicao: httpx.Response(
                200, stream=httpx.ByteStream(json.dumps(municipios).encode())
            )
        )
    ) as transporte:
        novo = (
            ClienteIBGE(transporte, armazenamento, dormir=lambda _: None)
            .coletar("municipios")
            .manifesto
        )
    manifestos = (*manifestos[:2], novo, *manifestos[3:])
    segundo = carregar_ibge(armazenamento, manifestos, banco)
    assert segundo.situacao == "SUCESSO"
    assert primeiro.snapshot_id != segundo.snapshot_id
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM core.municipio_snapshot")) == 2
        assert (
            conexao.scalar(text("SELECT count(DISTINCT snapshot_id) FROM core.fato_populacao")) == 1
        )


def test_carga_e_publicacao_com_papeis_reais(banco, tmp_path):
    import os

    from pydantic import SecretStr

    from pipeline_etl.banco.sessoes import criar_motor

    armazenamento, manifestos = preparar(tmp_path)
    motores = []
    try:
        for papel in ("processamento", "publicador"):
            senha = os.environ["SENHA_BANCO_" + papel.upper() + "_TESTES"]
            motores.append(
                criar_motor(
                    SecretStr(
                        banco.url.set(username=papel, password=senha).render_as_string(
                            hide_password=False
                        )
                    )
                )
            )
        assert carregar_ibge(armazenamento, manifestos, motores[0]).situacao == "SUCESSO"
        assert publicar_ibge(motores[1]).situacao == "SUCESSO"
    finally:
        for motor in motores:
            motor.dispose()


def test_recoleta_igual_avanca_evidencia_sem_alterar_fato(banco, tmp_path):
    base, base_manifestos = preparar(tmp_path / "base")
    antigo, antigo_manifestos = preparar(tmp_path / "antigo", "100")
    recente, recente_manifestos = preparar(tmp_path / "recente")
    assert carregar_ibge(base, base_manifestos, banco).situacao == "SUCESSO"
    assert carregar_ibge(recente, recente_manifestos, banco).inalteradas == 5
    assert carregar_ibge(antigo, antigo_manifestos, banco).motivo == "BRONZE_ANTIGO_DIVERGENTE"


@pytest.mark.parametrize("recoleta_igual", [False, True])
def test_municipios_antigos_nao_sao_atualizados_por_ufs_recentes(banco, tmp_path, recoleta_igual):
    armazenamento = SistemaArquivosObjetos(tmp_path)
    municipios = json.loads(
        b"[" + (AMOSTRAS / "municipio_hierarquia_opcional.body").read_bytes() + b"]"
    )
    municipios[0]["nome"] += " (variante antiga de teste)"
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda requisicao: httpx.Response(
                200, stream=httpx.ByteStream(json.dumps(municipios).encode())
            )
        )
    ) as transporte:
        municipio_antigo = (
            ClienteIBGE(transporte, armazenamento, dormir=lambda _: None)
            .coletar("municipios")
            .manifesto
        )
    armazenamento, atuais = preparar(tmp_path)
    primeira = carregar_ibge(armazenamento, atuais, banco)
    assert primeira.situacao == "SUCESSO"
    if recoleta_igual:
        # Esta divergência é posterior à carga inicial, mas anterior à recoleta igual.
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda requisicao: httpx.Response(
                    200, stream=httpx.ByteStream(json.dumps(municipios).encode())
                )
            )
        ) as transporte:
            municipio_antigo = (
                ClienteIBGE(transporte, armazenamento, dormir=lambda _: None)
                .coletar("municipios")
                .manifesto
            )
        armazenamento, iguais = preparar(tmp_path)
        assert carregar_ibge(armazenamento, iguais, banco).inalteradas == 5
    armazenamento, recentes = preparar(tmp_path)
    misturados = (*recentes[:2], municipio_antigo, *recentes[3:])
    with banco.connect() as conexao:
        fatos_antes = conexao.execute(text("SELECT * FROM core.fato_populacao ORDER BY ano")).all()
    rejeicao = carregar_ibge(armazenamento, misturados, banco)
    assert rejeicao.situacao == "FALHA"
    assert rejeicao.motivo == "SNAPSHOT_ANTIGO_DIVERGENTE"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM core.snapshot_localidades")) == 1
        assert (
            conexao.execute(text("SELECT * FROM core.fato_populacao ORDER BY ano")).all()
            == fatos_antes
        )
        assert (
            conexao.scalar(text("SELECT versao_core FROM ops.publicacao WHERE dominio='ibge'")) == 1
        )
