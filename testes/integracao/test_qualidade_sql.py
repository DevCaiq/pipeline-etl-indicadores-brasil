"""Auditoria e quarentena reais, sem escrever observações no core."""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import Engine, event, text

from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.comandos import executar
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.auditoria import ErroValidacao, coletar_e_validar, validar_manifesto
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie

pytestmark = pytest.mark.integracao


def preparar_manifesto(raiz: Path, registros: object) -> Path:
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
            date(2020, 1, 31),
        )


def test_registra_sucesso_e_revalidacao_sem_carregar_core(banco: Engine, tmp_path: Path) -> None:
    caminho = preparar_manifesto(tmp_path, [{"data": "02/01/2020", "valor": "4.5"}])
    armazenamento = ArmazenamentoBronze(tmp_path)
    primeiro = validar_manifesto(armazenamento, caminho, banco)
    segundo = validar_manifesto(armazenamento, caminho, banco)
    assert primeiro.situacao == segundo.situacao == "SUCESSO"
    assert primeiro.execucao_id != segundo.execucao_id
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT linhas_validas FROM ops.execucao WHERE execucao_id=:id"),
                {"id": primeiro.execucao_id},
            )
            == 1
        )
        assert (
            conexao.scalar(
                text(
                    "SELECT count(*) FROM ops.artefato a JOIN ops.etapa e USING(etapa_id) WHERE "
                    "e.execucao_id=:id"
                ),
                {"id": primeiro.execucao_id},
            )
            == 1
        )
        assert conexao.scalar(text("SELECT count(*) FROM core.fato_serie")) == 0


def test_quarentena_preserva_posicao_e_texto_impossivel_em_jsonb(
    banco: Engine, tmp_path: Path
) -> None:
    registros = [{"data": f"{dia:02d}/01/2020", "valor": "1"} for dia in range(1, 21)]
    registros[7]["valor"] = "\x00"
    caminho = preparar_manifesto(tmp_path, registros)
    resultado = validar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    assert resultado.situacao == "PARCIAL"
    assert resultado.contagens.validas == 19 and resultado.contagens.rejeitadas == 1
    with banco.connect() as conexao:
        linha = conexao.execute(
            text(
                "SELECT q.posicao,q.registro_original FROM ops.quarentena q JOIN ops.etapa e"
                " USING(etapa_id) WHERE e.execucao_id=:id"
            ),
            {"id": resultado.execucao_id},
        ).one()
        assert linha.posicao == 8
        assert json.loads(linha.registro_original["json_escapado"])["valor"] == "\x00"


def test_manifesto_corrompido_termina_execucao_com_falha(banco: Engine, tmp_path: Path) -> None:
    caminho = preparar_manifesto(tmp_path, [{"data": "01/01/2020", "valor": "1"}])
    next(tmp_path.rglob("*.body")).write_bytes(b"alterado")
    resultado = validar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    assert resultado.situacao == "FALHA"
    with banco.connect() as conexao:
        assert conexao.scalar(
            text("SELECT finalizado_em IS NOT NULL FROM ops.execucao WHERE execucao_id=:id"),
            {"id": resultado.execucao_id},
        )


def test_processamento_persiste_quarentena_sem_admin(banco: Engine, tmp_path: Path) -> None:
    senha = os.environ.get("SENHA_BANCO_PROCESSAMENTO_TESTES")
    assert senha
    motor = criar_motor(
        SecretStr(
            banco.url.set(username="processamento", password=senha).render_as_string(
                hide_password=False
            )
        )
    )
    try:
        caminho = preparar_manifesto(tmp_path, [{"data": "01/01/2020", "valor": "invalido"}])
        assert validar_manifesto(ArmazenamentoBronze(tmp_path), caminho, motor).situacao == "FALHA"
    finally:
        motor.dispose()


def test_falha_de_persistencia_reverte_etapas_e_nao_vira_sucesso(
    banco: Engine, tmp_path: Path
) -> None:
    caminho = preparar_manifesto(tmp_path, [{"data": "01/01/2020", "valor": "invalido"}])

    def impedir_quarentena(conexao, cursor, comando, parametros, contexto, muitos):
        if "INSERT INTO ops.quarentena" in comando:
            raise RuntimeError("Persistência interrompida")

    event.listen(banco, "before_cursor_execute", impedir_quarentena)
    try:
        with pytest.raises(ErroValidacao) as erro:
            validar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    finally:
        event.remove(banco, "before_cursor_execute", impedir_quarentena)
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": erro.value.execucao_id},
            )
            == "FALHA"
        )
        assert (
            conexao.scalar(
                text("SELECT count(*) FROM ops.etapa WHERE execucao_id=:id"),
                {"id": erro.value.execucao_id},
            )
            == 0
        )


def test_falha_http_registrada_antes_de_validar(banco: Engine, tmp_path: Path) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(404, stream=httpx.ByteStream(b"")))
    ) as transporte:
        resultado = coletar_e_validar(
            ClienteBCB(transporte),
            ArmazenamentoBronze(tmp_path),
            banco,
            432,
            date(2020, 1, 1),
            date(2020, 1, 31),
        )
    assert resultado.situacao == "FALHA"
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT modo FROM ops.execucao WHERE execucao_id=:id"),
                {"id": resultado.execucao_id},
            )
            == "coleta_validacao"
        )


def test_reuso_de_execucao_finalizada_nao_corrompe_historico(banco: Engine, tmp_path: Path) -> None:
    caminho = preparar_manifesto(tmp_path, [{"data": "01/01/2020", "valor": "1"}])
    armazenamento = ArmazenamentoBronze(tmp_path)
    resultado = validar_manifesto(armazenamento, caminho, banco)
    with pytest.raises(ErroValidacao):
        validar_manifesto(armazenamento, caminho, banco, execucao_id=resultado.execucao_id)
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": resultado.execucao_id},
            )
            == "SUCESSO"
        )


def test_percentual_global_preserva_resultado_de_cada_janela(banco: Engine, tmp_path: Path) -> None:
    def responder(requisicao: httpx.Request) -> httpx.Response:
        inicio = requisicao.url.params["dataInicial"]
        registros = (
            [{"data": "01/01/2020", "valor": "invalido"}]
            if inicio.endswith("2020")
            else [
                {
                    "data": (date(2021, 1, 1) + timedelta(days=dia)).strftime("%d/%m/%Y"),
                    "valor": "1",
                }
                for dia in range(100)
            ]
        )
        return httpx.Response(200, stream=httpx.ByteStream(json.dumps(registros).encode()))

    with httpx.Client(transport=httpx.MockTransport(responder)) as transporte:
        caminho = coletar_serie(
            ClienteBCB(transporte, dormir=lambda _: None),
            ArmazenamentoBronze(tmp_path),
            432,
            date(2020, 1, 1),
            date(2021, 12, 31),
        )
    resultado = validar_manifesto(ArmazenamentoBronze(tmp_path), caminho, banco)
    assert resultado.situacao == "PARCIAL"
    assert resultado.contagens.lidas == 101 and resultado.contagens.rejeitadas == 1
    with banco.connect() as conexao:
        etapas = (
            conexao.execute(
                text("SELECT situacao FROM ops.etapa WHERE execucao_id=:id"),
                {"id": resultado.execucao_id},
            )
            .scalars()
            .all()
        )
        assert set(etapas) == {"SUCESSO", "FALHA"}


def test_cli_valida_bronze_e_retorna_resumo(
    banco: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caminho = preparar_manifesto(tmp_path, [{"data": "01/01/2020", "valor": "1"}])
    monkeypatch.setenv("URL_BANCO_PROCESSAMENTO", banco.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path))
    capsys.readouterr()  # Descarta registros da preparação anterior ao comando.
    assert executar(["validar", "bcb", "--manifesto", str(caminho)]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida["contagens"]["validas"] == 1
    assert saida["situacao"] == "SUCESSO"


def test_cli_falha_de_banco_impede_requisicao_http(
    banco: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from sqlalchemy.exc import OperationalError

    def impedir_inicio(*argumentos, **opcoes):
        raise OperationalError("falha", {}, Exception("segredo-simulado"))

    monkeypatch.setenv("URL_BANCO_PROCESSAMENTO", banco.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path))
    monkeypatch.setattr("pipeline_etl.processamento.auditoria._iniciar", impedir_inicio)

    def impedir_http(*argumentos, **opcoes):
        pytest.fail("HTTP não pode iniciar sem auditoria")

    monkeypatch.setattr(httpx.Client, "send", impedir_http)
    assert (
        executar(
            [
                "coletar",
                "bcb",
                "--validar",
                "--serie",
                "432",
                "--inicio",
                "2020-01-01",
                "--fim",
                "2020-01-31",
            ]
        )
        == 1
    )
    saidas = capsys.readouterr()
    assert "AUDITORIA_INDISPONIVEL" in saidas.out
    assert "segredo-simulado" not in saidas.out + saidas.err


def test_api_nao_recebe_acesso_a_quarentena(banco: Engine) -> None:
    with banco.connect() as conexao:
        for tabela in ("ops.quarentena", "ops.etapa", "ops.artefato"):
            assert not conexao.scalar(
                text("SELECT has_table_privilege('api_leitura', :tabela, 'SELECT')"),
                {"tabela": tabela},
            )


def test_cli_coleta_validada_correlaciona_bronze_e_auditoria(
    banco: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    transporte = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, stream=httpx.ByteStream(b'[{"data":"02/01/2020","valor":"4.5"}]')
            )
        )
    )
    monkeypatch.setenv("URL_BANCO_PROCESSAMENTO", banco.url.render_as_string(hide_password=False))
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path))
    monkeypatch.setattr(httpx, "Client", lambda: transporte)
    assert (
        executar(
            [
                "coletar",
                "bcb",
                "--validar",
                "--serie",
                "432",
                "--inicio",
                "2020-01-01",
                "--fim",
                "2020-01-31",
            ]
        )
        == 0
    )
    saida = json.loads(capsys.readouterr().out)
    assert saida["situacao"] == "SUCESSO"
    identificador = saida["coletas"][0]["execucao_id"]
    manifesto = json.loads(next(tmp_path.rglob("manifest.json")).read_text(encoding="utf-8"))
    assert manifesto["execucao_id"] == identificador
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": identificador},
            )
            == "SUCESSO"
        )


def test_nova_validacao_registra_politica_e_versao_do_calendario(banco, tmp_path, monkeypatch):
    from datetime import UTC, datetime

    class RelogioFixo(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 18, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("pipeline_etl.processamento.auditoria.datetime", RelogioFixo)
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, stream=httpx.ByteStream(b'[{"data":"01/10/2026","valor":"1"}]')
            )
        )
    ) as transporte:
        armazenamento = ArmazenamentoBronze(tmp_path)
        caminho = coletar_serie(
            ClienteBCB(transporte), armazenamento, 433, date(2026, 1, 1), date(2026, 11, 18)
        )
    resultado = validar_manifesto(armazenamento, caminho, banco)
    assert resultado.situacao == "SUCESSO"
    assert "FRESCOR_POTENCIALMENTE_DEFASADO" not in resultado.avisos
    with banco.connect() as conexao:
        parametros = conexao.scalar(
            text("SELECT parametros FROM ops.execucao WHERE execucao_id=:id"),
            {"id": resultado.execucao_id},
        )
        avaliacao = parametros["avaliacoes_frescor"][0]
        assert avaliacao["politica"] == "CALENDARIO_IBGE"
        assert avaliacao["defasado"] is False
        assert avaliacao["referencia_esperada"] == "2026-10-01"
        assert avaliacao["versao_calendario"].startswith("ibge-ipca-20261118-")
