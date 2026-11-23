"""Adaptador Prefect IBGE: processo principal, parâmetros e falhas propagadas."""

import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("codigo", [0, 1])
def test_fluxo_ibge_respeita_resultado_do_processo(monkeypatch, tmp_path, codigo):
    falso = ModuleType("prefect")
    falso.flow = lambda **_: lambda funcao: funcao
    monkeypatch.setitem(sys.modules, "prefect", falso)
    caminho = Path(__file__).resolve().parents[2] / "orquestracao/fluxos.py"
    monkeypatch.syspath_prepend(str(caminho.parent))
    fluxo = runpy.run_path(str(caminho))["executar_fluxo_ibge"]
    monkeypatch.setitem(fluxo.__globals__, "RAIZ", tmp_path)
    monkeypatch.setitem(fluxo.__globals__, "_estado_agenda_vencida", lambda: None)
    executar = Mock(return_value=SimpleNamespace(returncode=codigo))
    monkeypatch.setattr(fluxo.__globals__["subprocess"], "run", executar)
    if codigo:
        with pytest.raises(RuntimeError, match="incompleto"):
            fluxo(modo="incremental", usar_s3=True)
    else:
        assert Path(fluxo(modo="incremental", usar_s3=True)).is_file()
    comando = executar.call_args.args[0]
    assert str(tmp_path / ".venv/Scripts/python.exe") == comando[0]
    assert comando[-2:] == ["--configuracao-s3", str(tmp_path / ".env.armazenamento")]
    assert executar.call_args.kwargs["timeout"] == 3600


def test_agenda_vencida_retorna_cancelamento_antes_do_subprocesso(monkeypatch, tmp_path):
    falso = ModuleType("prefect")
    falso.flow = lambda **_: lambda funcao: funcao
    monkeypatch.setitem(sys.modules, "prefect", falso)
    caminho = Path(__file__).resolve().parents[2] / "orquestracao/fluxos.py"
    monkeypatch.syspath_prepend(str(caminho.parent))
    fluxo = runpy.run_path(str(caminho))["executar_fluxo_ibge"]
    executar = Mock()
    cancelado = SimpleNamespace(tipo="CANCELLED")
    monkeypatch.setitem(fluxo.__globals__, "_estado_agenda_vencida", lambda: cancelado)
    monkeypatch.setattr(fluxo.__globals__["subprocess"], "run", executar)
    assert fluxo() is cancelado
    executar.assert_not_called()
