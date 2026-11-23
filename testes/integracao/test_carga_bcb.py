"""Promoção atômica, repetível e protegida no PostgreSQL exclusivo de testes."""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Engine, event, text

from pipeline_etl.comandos import executar
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.carga import CHAVE_TRAVA_BCB, carregar_manifesto
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie

pytestmark = pytest.mark.integracao


@pytest.fixture(autouse=True)
def limpar_cargas(banco: Engine):
    def limpar():
        with banco.begin() as conexao:
            for tabela in (
                "core.fato_serie",
                "ops.preparacao_bcb",
                "ops.lote",
                "ops.watermark_bcb",
                "ops.publicacao",
            ):
                conexao.execute(text("DELETE FROM " + tabela))

    limpar()
    yield
    limpar()


def preparar(raiz: Path, valor: str = "4.5", invalido: bool = False) -> Path:
    registros = [{"data": "02/01/2020", "valor": valor}]
    if invalido:
        registros.append({"data": "03/01/2020", "valor": "invalido"})
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=httpx.ByteStream(json.dumps(registros).encode()))
        )
    ) as transporte:
        return coletar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(raiz),
            432,
            date(2020, 1, 1),
            date(2020, 1, 6),
        )


def retrato(banco):
    with banco.connect() as conexao:
        return conexao.execute(
            text("SELECT valor,lote_id,alterado_em,origem_coletada_em FROM core.fato_serie")
        ).all()


def test_repetir_preserva_valor_origem_e_instante(banco: Engine, tmp_path: Path):
    caminho = preparar(tmp_path)
    primeiro = carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    antes = retrato(banco)
    segundo = carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    assert primeiro.situacao == segundo.situacao == "SUCESSO"
    assert primeiro.inseridas == 1 and segundo.inalteradas == 1
    assert retrato(banco) == antes
    with banco.connect() as conexao:
        assert (
            conexao.scalar(text("SELECT versao_core FROM ops.publicacao WHERE dominio='bcb'")) == 1
        )
        assert conexao.scalar(
            text("SELECT fim_coberto FROM ops.watermark_bcb WHERE codigo_sgs=432")
        ) == date(2020, 1, 6)


def test_revisao_atualiza_e_bronze_antigo_divergente_bloqueia(banco: Engine, tmp_path: Path):
    antigo = preparar(tmp_path, "4.5")
    carregar_manifesto(ArmazenamentoBronze(tmp_path), antigo, banco)
    novo = preparar(tmp_path, "4.6")
    assert carregar_manifesto(ArmazenamentoBronze(tmp_path), novo, banco).alteradas == 1
    antes = retrato(banco)
    assert carregar_manifesto(ArmazenamentoBronze(tmp_path), antigo, banco).situacao == "FALHA"
    assert retrato(banco) == antes


def test_qualidade_incompleta_nao_promove(banco: Engine, tmp_path: Path):
    caminho = preparar(tmp_path, invalido=True)
    assert carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco).situacao == "FALHA"
    assert retrato(banco) == []


def test_falha_na_conclusao_reverte_todos_efeitos(banco: Engine, tmp_path: Path):
    caminho = preparar(tmp_path)

    def falhar(conexao, cursor, comando, parametros, contexto, muitos):
        if "INSERT INTO ops.watermark_bcb" in comando:
            raise RuntimeError("Falha injetada")

    event.listen(banco, "before_cursor_execute", falhar)
    try:
        assert carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco).situacao == "FALHA"
    finally:
        event.remove(banco, "before_cursor_execute", falhar)
    assert retrato(banco) == []
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM ops.lote")) == 0
        assert conexao.scalar(text("SELECT count(*) FROM ops.publicacao")) == 0
        assert conexao.scalar(text("SELECT count(*) FROM ops.preparacao_bcb")) == 1


def test_lock_ocupado_adia_sem_promover(banco: Engine, tmp_path: Path):
    caminho = preparar(tmp_path)
    with banco.begin() as conexao:
        conexao.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_BCB})
        resumo = carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco, espera_trava=0)
        assert resumo.situacao == "IGNORADA"
    assert retrato(banco) == []


def preparar_janela(raiz, inicio, fim, registros, codigo=432, instante=None):
    def responder(requisicao):
        inicial = datetime.strptime(requisicao.url.params["dataInicial"], "%d/%m/%Y").date()
        final = datetime.strptime(requisicao.url.params["dataFinal"], "%d/%m/%Y").date()
        selecionados = [
            registro
            for registro in registros
            if inicial <= datetime.strptime(registro["data"], "%d/%m/%Y").date() <= final
        ]
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(selecionados).encode()))

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        cliente = ClienteBCB(
            transporte, agora=(lambda: instante) if instante else None, dormir=lambda _: None
        )
        return coletar_serie(cliente, ArmazenamentoBronze(raiz), codigo, inicio, fim)


def test_checkpoint_nao_salta_janela_e_ultima_observacao_respeita_cobertura(banco, tmp_path):
    futuro = preparar_janela(
        tmp_path, date(2020, 1, 10), date(2020, 1, 15), [{"data": "10/01/2020", "valor": "1"}]
    )
    assert carregar_manifesto(ArmazenamentoBronze(tmp_path), futuro, banco).situacao == "SUCESSO"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM ops.watermark_bcb")) == 0
    inicial = preparar(tmp_path)
    carregar_manifesto(ArmazenamentoBronze(tmp_path), inicial, banco)
    with banco.connect() as conexao:
        marcador = conexao.execute(
            text("SELECT fim_coberto,ultima_observacao FROM ops.watermark_bcb")
        ).one()
        assert marcador == (date(2020, 1, 6), date(2020, 1, 2))
    ponte = preparar_janela(
        tmp_path, date(2020, 1, 7), date(2020, 1, 9), [{"data": "07/01/2020", "valor": "1"}]
    )
    carregar_manifesto(ArmazenamentoBronze(tmp_path), ponte, banco)
    with banco.connect() as conexao:
        assert conexao.execute(
            text("SELECT fim_coberto,ultima_observacao FROM ops.watermark_bcb")
        ).one() == (date(2020, 1, 15), date(2020, 1, 10))


def test_ausencia_de_registro_alerta_sem_excluir(banco, tmp_path):
    primeiro = preparar_janela(
        tmp_path,
        date(2020, 1, 1),
        date(2020, 1, 6),
        [{"data": "02/01/2020", "valor": "4.5"}, {"data": "03/01/2020", "valor": "4.5"}],
    )
    carregar_manifesto(ArmazenamentoBronze(tmp_path), primeiro, banco)
    segundo = preparar(tmp_path)
    resumo = carregar_manifesto(ArmazenamentoBronze(tmp_path), segundo, banco)
    assert resumo.avisos == ("OBSERVACOES_AUSENTES_NA_JANELA",)
    assert len(retrato(banco)) == 2


def test_origem_nova_igual_bloqueia_revisao_intermediaria_antiga(banco, tmp_path):
    def criar(valor, ano):
        return preparar_janela(
            tmp_path,
            date(2020, 1, 1),
            date(2020, 1, 6),
            [{"data": "02/01/2020", "valor": valor}],
            instante=datetime(ano, 1, 1, tzinfo=UTC),
        )

    antigo = criar("1", 2023)
    intermediario = criar("2", 2024)
    recente = criar("1", 2025)
    carregar_manifesto(ArmazenamentoBronze(tmp_path), antigo, banco)
    carregar_manifesto(ArmazenamentoBronze(tmp_path), recente, banco)
    resumo = carregar_manifesto(ArmazenamentoBronze(tmp_path), intermediario, banco)
    assert resumo.situacao == "FALHA"
    assert resumo.motivo == "BRONZE_ANTIGO_DIVERGENTE"


def test_cli_carga_com_processamento_sem_privilegio_admin(banco, tmp_path, monkeypatch, capsys):
    senha = os.environ["SENHA_BANCO_PROCESSAMENTO_TESTES"]
    endereco = banco.url.set(username="processamento", password=senha)
    caminho = preparar(tmp_path)
    capsys.readouterr()
    monkeypatch.setenv("URL_BANCO_PROCESSAMENTO", endereco.render_as_string(hide_password=False))
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path))
    assert executar(["carregar", "bcb", "--manifesto", str(caminho)]) == 0
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["inseridas"] == 1


@pytest.mark.parametrize("espera", [-1, float("nan"), float("inf")])
def test_espera_invalida_nao_inicia_carga(banco, tmp_path, espera):
    with pytest.raises(ValueError, match="Espera"):
        carregar_manifesto(
            ArmazenamentoBronze(tmp_path), tmp_path / "ausente", banco, espera_trava=espera
        )


def test_ipca_preserva_apoio_de_2019_e_valor_negativo(banco, tmp_path):
    caminho = preparar_janela(
        tmp_path,
        date(2020, 1, 1),
        date(2020, 1, 31),
        [{"data": "01/02/2019", "valor": "0.1"}, {"data": "01/01/2020", "valor": "-0.1"}],
        codigo=433,
    )
    resumo = carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    assert resumo.situacao == "SUCESSO" and resumo.inseridas == 2
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT min(data) FROM core.fato_serie")) == date(2019, 2, 1)


def test_cli_carga_sem_credenciais_e_com_banco_indisponivel(banco, tmp_path, monkeypatch, capsys):
    assert executar(["carregar", "bcb", "--manifesto", "ausente"]) == 2
    assert "Credenciais" in capsys.readouterr().err
    monkeypatch.setenv(
        "URL_BANCO_PROCESSAMENTO", "postgresql+psycopg://teste:segredo@127.0.0.1:1/etl_testes"
    )
    assert executar(["carregar", "bcb", "--manifesto", "ausente"]) == 1
    saidas = capsys.readouterr()
    assert "segredo" not in saidas.err


def test_atualizacao_interrompe_na_falha_e_retomada_preserva_primeira_janela(banco, tmp_path):
    from pipeline_etl.processamento.atualizacao import atualizar_serie

    chamadas = []

    def responder(requisicao):
        inicio = requisicao.url.params["dataInicial"]
        chamadas.append(inicio)
        if inicio.endswith("2021"):
            return httpx.Response(404, stream=httpx.ByteStream(b"indisponivel"))
        return httpx.Response(
            200, stream=httpx.ByteStream(json.dumps([{"data": inicio, "valor": "1"}]).encode())
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resumo = atualizar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "carga-historica",
            inicio=date(2020, 1, 1),
            fim=date(2022, 1, 1),
        )
    assert resumo.situacao == "PARCIAL"
    assert chamadas == ["01/01/2020", "01/01/2021"]
    antes = retrato(banco)
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT fim_coberto FROM ops.watermark_bcb")) == date(
            2020, 12, 31
        )
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": resumo.execucao_id},
            )
            == "PARCIAL"
        )

    def responder_sucesso(requisicao):
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                json.dumps([{"data": requisicao.url.params["dataInicial"], "valor": "1"}]).encode()
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(responder_sucesso)) as transporte:
        retomada = atualizar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "carga-historica",
            inicio=date(2020, 1, 1),
            fim=date(2022, 1, 1),
        )
    assert retomada.situacao == "SUCESSO"
    assert retrato(banco)[0] == antes[0]
    assert retomada.resultados[0].carga.inalteradas == 1
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT fim_coberto FROM ops.watermark_bcb")) == date(2022, 1, 1)


def test_incremental_sem_marco_e_previa_nao_fazem_http_nem_gravam(banco, tmp_path):
    from pipeline_etl.processamento.atualizacao import atualizar_serie

    def impedir(requisicao):
        pytest.fail("Consulta HTTP indevida")

    with banco.connect() as conexao:
        antes = conexao.scalar(text("SELECT count(*) FROM ops.execucao"))
    with httpx.Client(transport=httpx.MockTransport(impedir)) as transporte:
        cliente = ClienteBCB(transporte)
        resumo = atualizar_serie(
            cliente, ArmazenamentoBronze(tmp_path), banco, 432, "incremental", somente_planejar=True
        )
        assert resumo.motivo == "SEM_CHECKPOINT"
        previa = atualizar_serie(
            cliente,
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "reconciliacao",
            somente_planejar=True,
        )
        assert previa.situacao == "PLANEJADA" and previa.execucao_id is None
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM ops.execucao")) == antes


def test_incremental_consulta_recuo_do_checkpoint_e_confirma_fim(banco, tmp_path):
    from pipeline_etl.processamento.atualizacao import atualizar_serie

    caminho = preparar(tmp_path)
    carregar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    chamadas = []

    def responder(requisicao):
        chamadas.append(dict(requisicao.url.params))
        return httpx.Response(
            200,
            stream=httpx.ByteStream(
                b'[{"data":"02/01/2020","valor":"4.5"},{"data":"07/01/2020","valor":"4.5"}]'
            ),
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resumo = atualizar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "incremental",
            hoje=date(2020, 1, 7),
        )
    assert resumo.situacao == "SUCESSO"
    assert chamadas == [{"formato": "json", "dataInicial": "01/01/2020", "dataFinal": "07/01/2020"}]
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT fim_coberto FROM ops.watermark_bcb")) == date(2020, 1, 7)


def test_atualizacao_qualidade_invalida_bloqueia_janelas_seguintes(banco, tmp_path):
    from pipeline_etl.processamento.atualizacao import atualizar_serie

    chamadas = []

    def responder(requisicao):
        chamadas.append(str(requisicao.url))
        return httpx.Response(
            200, stream=httpx.ByteStream(b'[{"data":"01/01/2020","valor":"invalido"}]')
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resumo = atualizar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "carga-historica",
            inicio=date(2020, 1, 1),
            fim=date(2021, 1, 1),
        )
    assert resumo.situacao == "FALHA" and len(chamadas) == 1
    assert resumo.resultados[0].carga.motivo == "QUALIDADE_INCOMPLETA"
    assert retrato(banco) == []


def test_cli_atualizacao_isola_series_e_previa_e_somente_leitura(
    banco, tmp_path, monkeypatch, capsys
):
    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao.url.path)
        if ".1/" in requisicao.url.path:
            return httpx.Response(404, stream=httpx.ByteStream(b"ausente"))
        return httpx.Response(
            200, stream=httpx.ByteStream(b'[{"data":"02/01/2020","valor":"4.5"}]')
        )

    cliente_http_original = httpx.Client
    transporte = httpx.Client(transport=httpx.MockTransport(responder))
    monkeypatch.setenv("URL_BANCO_PROCESSAMENTO", banco.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path))
    monkeypatch.setattr(httpx, "Client", lambda: transporte)
    assert (
        executar(
            [
                "coletar",
                "bcb",
                "--carregar",
                "--inicio",
                "2020-01-01",
                "--fim",
                "2020-01-06",
                "--serie",
                "432",
                "--serie",
                "1",
            ]
        )
        == 1
    )
    resumo = json.loads(capsys.readouterr().out)
    assert resumo["situacao"] == "PARCIAL"
    assert [item["situacao"] for item in resumo["atualizacoes"]] == ["SUCESSO", "FALHA"]
    assert len(chamadas) == 2
    with banco.connect() as conexao:
        antes = conexao.scalar(text("SELECT count(*) FROM ops.execucao"))
    # Nova instância, pois a CLI encerra o transporte ao terminar.
    monkeypatch.setattr(httpx, "Client", cliente_http_original)
    monkeypatch.setenv("URL_BANCO_PROCESSAMENTO", banco.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path))

    def impedir(*argumentos, **opcoes):
        pytest.fail("Prévia não pode chamar HTTP")

    monkeypatch.setattr(httpx.Client, "send", impedir)
    assert (
        executar(["coletar", "bcb", "--modo", "incremental", "--planejar", "--serie", "432"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["situacao"] == "PLANEJADA"
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT count(*) FROM ops.execucao")) == antes


def test_cli_atualizacao_sem_banco_impede_http(banco, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(
        "URL_BANCO_PROCESSAMENTO", "postgresql+psycopg://teste:segredo@127.0.0.1:1/etl_testes"
    )

    def impedir(*argumentos, **opcoes):
        pytest.fail("HTTP não pode anteceder auditoria SQL")

    monkeypatch.setattr(httpx.Client, "send", impedir)
    assert (
        executar(
            [
                "coletar",
                "bcb",
                "--carregar",
                "--inicio",
                "2020-01-01",
                "--fim",
                "2020-01-02",
                "--serie",
                "432",
            ]
        )
        == 1
    )
    saidas = capsys.readouterr()
    assert "BANCO_OU_AUDITORIA_INDISPONIVEL" in saidas.out
    assert "segredo" not in saidas.out + saidas.err


def test_falha_tecnica_intermediaria_preserva_janela_confirmada(banco, tmp_path, monkeypatch):
    from pipeline_etl.processamento import atualizacao

    original = atualizacao._coletar_janela

    def interromper(cliente, armazenamento, motor, pai, codigo, inicio, fim):
        if inicio.year == 2021:
            raise RuntimeError("Falha técnica simulada")
        return original(cliente, armazenamento, motor, pai, codigo, inicio, fim)

    monkeypatch.setattr(atualizacao, "_coletar_janela", interromper)
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, stream=httpx.ByteStream(b'[{"data":"01/01/2020","valor":"1"}]')
                )
            )
        ) as transporte,
        pytest.raises(atualizacao.ErroAtualizacao) as erro,
    ):
        atualizacao.atualizar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "carga-historica",
            inicio=date(2020, 1, 1),
            fim=date(2022, 1, 1),
        )
    with banco.connect() as conexao:
        assert conexao.scalar(text("SELECT fim_coberto FROM ops.watermark_bcb")) == date(
            2020, 12, 31
        )
        registro = conexao.execute(
            text("SELECT situacao,parametros FROM ops.execucao WHERE execucao_id=:id"),
            {"id": erro.value.execucao_id},
        ).one()
        assert registro.situacao == "FALHA"
        assert len(registro.parametros["resultados"]) == 1


def test_retry_after_longo_interrompe_atualizacao_e_preserva_retomada(banco, tmp_path):
    from pipeline_etl.processamento.atualizacao import atualizar_serie

    chamadas = []

    def responder(requisicao):
        chamadas.append(requisicao)
        return httpx.Response(
            429, headers={"Retry-After": "3600"}, stream=httpx.ByteStream(b"limite")
        )

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        resumo = atualizar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "carga-historica",
            inicio=date(2020, 1, 1),
            fim=date(2021, 1, 1),
        )
    assert resumo.situacao == "FALHA" and len(chamadas) == 1
    assert resumo.resultados[0].manifesto.exists()
    with banco.connect() as conexao:
        parametros = conexao.scalar(
            text("SELECT parametros FROM ops.execucao WHERE execucao_id=:id"),
            {"id": resumo.resultados[0].coleta_id},
        )
        assert parametros["proxima_tentativa_em"]
    assert retrato(banco) == []


def test_indisponibilidade_ao_registrar_falha_nao_anuncia_sucesso(
    banco, tmp_path, monkeypatch, capsys
):
    from pipeline_etl.processamento import atualizacao

    def interromper(*argumentos, **opcoes):
        raise RuntimeError("detalhe-confidencial")

    monkeypatch.setattr(atualizacao, "_coletar_janela", interromper)
    monkeypatch.setattr(atualizacao, "_finalizar_falha", interromper)
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: pytest.fail("HTTP indevido"))
        ) as transporte,
        pytest.raises(atualizacao.ErroAtualizacao) as erro,
    ):
        atualizacao.atualizar_serie(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            "carga-historica",
            inicio=date(2020, 1, 1),
            fim=date(2020, 1, 2),
        )
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": erro.value.execucao_id},
            )
            == "EM_EXECUCAO"
        )
    saidas = capsys.readouterr()
    assert "detalhe-confidencial" not in saidas.out + saidas.err
