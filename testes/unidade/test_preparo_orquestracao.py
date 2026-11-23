"""Falha de disco não pode criar recursos com senha perdida."""

import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


def test_falha_de_persistencia_acontece_antes_de_alterar_banco(tmp_path, monkeypatch):
    caminho = Path(__file__).resolve().parents[2] / "scripts/preparar_orquestracao_local.py"
    especificacao = importlib.util.spec_from_file_location("preparo_orquestracao", caminho)
    modulo = importlib.util.module_from_spec(especificacao)
    especificacao.loader.exec_module(modulo)
    monkeypatch.setattr(modulo, "__file__", str(tmp_path / "scripts/preparar.py"))
    conectar = Mock(side_effect=AssertionError("Banco não deve ser acessado."))
    monkeypatch.setattr(modulo.psycopg, "connect", conectar)
    monkeypatch.setattr(modulo.os, "fsync", Mock(side_effect=OSError("Disco indisponível.")))
    with pytest.raises(OSError, match="Disco"):
        modulo.executar()
    conectar.assert_not_called()
