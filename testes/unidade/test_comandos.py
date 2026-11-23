"""Comportamento público da interface de linha de comando."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from pipeline_etl.comandos import executar


def test_verifica_configuracao_com_saida_e_registro_separados(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert executar(["verificar-configuracao"]) == 0
    saidas = capsys.readouterr()
    resumo = json.loads(saidas.out)
    assert resumo["ambiente"] == "desenvolvimento"
    assert resumo["series_bcb"] == [432, 433, 1]
    assert json.loads(saidas.err)["mensagem"] == "Configuração verificada"


def test_configuracao_invalida_retorna_erro_sem_expor_valor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AMBIENTE", "valor-confidencial")
    assert executar(["verificar-configuracao"]) == 2
    saidas = capsys.readouterr()
    assert saidas.out == ""
    assert "Configuração inválida" in saidas.err
    assert "valor-confidencial" not in saidas.err


def test_ajuda_nao_exige_configuracao_valida(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AMBIENTE", "invalido")
    assert executar([]) == 0
    assert "verificar-configuracao" in capsys.readouterr().out


def test_comando_desconhecido_nao_executa(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as erro:
        executar(["comando-inexistente"])
    assert erro.value.code == 2
    assert capsys.readouterr().out == ""


def test_opcao_versao(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as erro:
        executar(["--versao"])
    assert erro.value.code == 0
    assert re.fullmatch(r"\d+\.\d+\.\d+\n", capsys.readouterr().out)


def test_modulo_preserva_acentos_em_terminal_com_codificacao_limitada() -> None:
    ambiente = {
        **os.environ,
        "PYTHONIOENCODING": "ascii",
        "CAMINHO_BRONZE": "dados/observações",
    }
    resultado = subprocess.run(
        [sys.executable, "-m", "pipeline_etl", "verificar-configuracao"],
        env=ambiente,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "observações" in json.loads(resultado.stdout)["caminho_bronze"]
    assert json.loads(resultado.stderr)["mensagem"] == "Configuração verificada"


@pytest.mark.parametrize("argumentos", [[], ["--ajuda"]])
def test_ajuda_funciona_em_terminal_com_codificacao_limitada(argumentos: list[str]) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "pipeline_etl", *argumentos],
        env={**os.environ, "PYTHONIOENCODING": "ascii"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "dados públicos brasileiros" in resultado.stdout


def test_comando_coletar_preserva_bronze_sem_banco(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    corpo = b"resposta bruta sem parse"
    transporte = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=httpx.ByteStream(corpo)))
    )
    monkeypatch.setattr("pipeline_etl.comandos.httpx.Client", lambda: transporte)
    monkeypatch.setenv("CAMINHO_BRONZE", str(tmp_path / "bronze"))
    assert (
        executar(
            ["coletar", "bcb", "--serie", "432", "--inicio", "2020-01-02", "--fim", "2020-01-06"]
        )
        == 0
    )
    saidas = capsys.readouterr()
    resumo = json.loads(saidas.out)
    assert resumo["situacao"] == "COLETADA"
    assert list((tmp_path / "bronze").rglob("*.body"))[0].read_bytes() == corpo
    assert "Consulta BCB iniciada" in saidas.err


def test_comando_coletar_falha_http_sem_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    transporte = httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(404, stream=httpx.ByteStream(b"")))
    )
    monkeypatch.setattr("pipeline_etl.comandos.httpx.Client", lambda: transporte)
    assert (
        executar(
            ["coletar", "bcb", "--serie", "1", "--inicio", "2020-01-02", "--fim", "2020-01-06"]
        )
        == 1
    )
    saidas = capsys.readouterr()
    resumo = json.loads(saidas.out)
    assert resumo["situacao"] == "INCOMPLETA"
    assert resumo["coletas"][0]["manifesto"]
    assert "Traceback" not in saidas.err


def test_comando_coletar_rejeita_data_malformada() -> None:
    with pytest.raises(SystemExit) as erro:
        executar(["coletar", "bcb", "--inicio", "02/01/2020", "--fim", "2020-01-06"])
    assert erro.value.code == 2


def test_comando_coletar_rejeita_periodo_invertido(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        executar(
            ["coletar", "bcb", "--serie", "1", "--inicio", "2021-01-01", "--fim", "2020-01-01"]
        )
        == 2
    )
    saidas = capsys.readouterr()
    assert saidas.out == ""
    assert "Período de coleta inválido" in saidas.err


def test_comando_coletar_informa_adiamento_sem_consultar_outra_serie(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chamadas: list[httpx.Request] = []

    def responder(requisicao: httpx.Request) -> httpx.Response:
        chamadas.append(requisicao)
        return httpx.Response(429, headers={"Retry-After": "3600"}, stream=httpx.ByteStream(b""))

    transporte = httpx.Client(transport=httpx.MockTransport(responder))
    monkeypatch.setattr("pipeline_etl.comandos.httpx.Client", lambda: transporte)
    assert (
        executar(
            [
                "coletar",
                "bcb",
                "--serie",
                "1",
                "--serie",
                "432",
                "--inicio",
                "2020-01-02",
                "--fim",
                "2020-01-06",
            ]
        )
        == 1
    )
    resumo = json.loads(capsys.readouterr().out)
    assert len(resumo["coletas"]) == 2
    assert all(item["proxima_tentativa_em"] for item in resumo["coletas"])
    assert len(chamadas) == 1


def test_validar_exige_credencial_sem_expor_segredos(capsys: pytest.CaptureFixture[str]) -> None:
    assert executar(["validar", "bcb", "--manifesto", "dados/bronze/manifest.json"]) == 2
    assert "credenciais" in capsys.readouterr().err.lower()


def test_coletar_com_validacao_exige_banco_antes_da_rede(
    capsys: pytest.CaptureFixture[str],
) -> None:
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
        == 2
    )
    assert "credenciais" in capsys.readouterr().err.lower()


@pytest.mark.parametrize(
    "argumentos",
    [
        ["--modo", "incremental", "--inicio", "2020-01-01"],
        ["--modo", "reconciliacao", "--fim", "2020-01-01"],
        ["--modo", "incremental", "--validar"],
        ["--inicio", "2020-01-01", "--fim", "2020-01-02", "--validar", "--carregar"],
        ["--inicio", "2020-01-01", "--fim", "2020-01-02", "--planejar"],
        [],
    ],
)
def test_rejeita_combinacoes_ambiguas_de_atualizacao(argumentos, capsys):
    with pytest.raises(SystemExit) as erro:
        executar(["coletar", "bcb", *argumentos])
    assert erro.value.code == 2
    assert not capsys.readouterr().out


def test_incremental_e_reconciliacao_aceitam_datas_automaticas_e_exigem_credenciais(capsys):
    for modo in ("incremental", "reconciliacao"):
        assert executar(["coletar", "bcb", "--modo", modo, "--planejar"]) == 2
        assert "Credenciais" in capsys.readouterr().err


def test_publicacao_exige_credenciais_sem_expor_segredos(capsys):
    assert executar(["publicar", "--dominio", "bcb"]) == 2
    assert "Credenciais" in capsys.readouterr().err


def test_servidor_exige_segredo_e_nao_publica_fora_loopback(tmp_path, monkeypatch, capsys):
    assert executar(["servir", "--configuracao-api", str(tmp_path / "ausente")]) == 2
    assert "SEGREDO_CURSOR" in capsys.readouterr().err
    arquivo = tmp_path / ".env.api"
    arquivo.write_text("SEGREDO_CURSOR=" + ("s" * 48) + "\n")
    chamadas = []
    monkeypatch.setattr(
        "pipeline_etl.comandos_api.uvicorn.run",
        lambda *argumentos, **opcoes: chamadas.append(opcoes),
    )
    assert executar(["servir", "--configuracao-api", str(arquivo), "--porta", "8123"]) == 0
    assert chamadas[0]["host"] == "127.0.0.1" and chamadas[0]["port"] == 8123
    assert not chamadas[0]["access_log"]
    assert chamadas[0]["proxy_headers"] is False
    assert executar(["servir", "--configuracao-api", str(arquivo), "--porta", "0"]) == 2
