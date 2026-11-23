"""Ferramentas portáveis e falhas de configuração antes de acessar o banco."""

import runpy
from pathlib import Path

import pytest

PASTA_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_reproducao_localiza_ferramenta_no_path(monkeypatch):
    modulo = runpy.run_path(str(PASTA_SCRIPTS / "verificar_reproducao_m1.py"))
    monkeypatch.setattr(modulo["shutil"], "which", lambda nome: "/ferramentas/" + nome)
    assert modulo["localizar_ferramenta"]("uv") == Path("/ferramentas/uv")


def test_reproducao_informa_ferramenta_ausente(monkeypatch):
    modulo = runpy.run_path(str(PASTA_SCRIPTS / "verificar_reproducao_m1.py"))
    monkeypatch.setattr(modulo["shutil"], "which", lambda nome: None)
    with pytest.raises(RuntimeError, match="docker.*PATH"):
        modulo["localizar_ferramenta"]("docker")


def test_testes_recusam_credenciais_sem_publicador_antes_de_conectar(monkeypatch, capsys):
    modulo = runpy.run_path(str(PASTA_SCRIPTS / "testar_banco.py"))
    contexto = modulo["executar"].__globals__
    monkeypatch.setitem(
        contexto,
        "dotenv_values",
        lambda caminho: {
            "SENHA_BANCO_" + nome: "senha-ficticia"
            for nome in ("ADMIN", "MIGRACOES", "API", "PROCESSAMENTO")
        },
    )

    def impedir_conexao(*argumentos, **opcoes):
        pytest.fail("Configuração incompleta não deve abrir conexão.")

    monkeypatch.setattr(modulo["psycopg"], "connect", impedir_conexao)
    assert modulo["executar"]() == 2
    assert "Preencha .env.banco" in capsys.readouterr().err
