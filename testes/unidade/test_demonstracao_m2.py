"""Demonstração aborta sem replay quando a restauração não confirma sucesso."""

import json
import runpy
from pathlib import Path

import pytest


def test_falha_restauracao_registra_falha_sem_abrir_motor(monkeypatch, tmp_path):
    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    modulo = runpy.run_path(str(pasta / "demonstrar_m2_local.py"))
    executar = modulo["executar"]
    contexto = executar.__globals__
    monkeypatch.setitem(contexto, "RAIZ", tmp_path)
    monkeypatch.setitem(contexto, "restaurar", lambda: 1)

    def impedir_motor(*argumentos, **opcoes):
        pytest.fail("Falha da restauração não pode abrir conexão para replay.")

    monkeypatch.setitem(contexto, "criar_motor", impedir_motor)
    with pytest.raises(RuntimeError, match="Restauração M2 falhou"):
        executar()
    caminhos = list((tmp_path / "dados/descoberta").glob("demonstracao_m2_*.json"))
    assert len(caminhos) == 1
    relatorio = json.loads(caminhos[0].read_text(encoding="utf-8"))
    assert relatorio["situacao"] == "FALHA"
    assert relatorio["tipo_erro"] == "RuntimeError"
    assert "replay" not in relatorio


@pytest.mark.parametrize("destino", ["etl", "etl_testes", "postgres"])
def test_controle_publicacao_recusa_bancos_protegidos(monkeypatch, destino):
    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    modulo = runpy.run_path(str(pasta / "demonstrar_m2_local.py"))
    with pytest.raises(ValueError, match="destino"):
        modulo["marcar_publicacao_pendente"](None, destino)


def test_controle_publicacao_confere_banco_real_antes_de_alterar(monkeypatch):
    from contextlib import contextmanager

    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    modulo = runpy.run_path(str(pasta / "demonstrar_m2_local.py"))

    class ConexaoProtegida:
        def scalar(self, consulta):
            return "etl"

        def execute(self, consulta):
            pytest.fail("Banco real divergente não pode receber UPDATE.")

    class MotorProtegido:
        @contextmanager
        def begin(self):
            yield ConexaoProtegida()

    with pytest.raises(RuntimeError, match="Conexão"):
        modulo["marcar_publicacao_pendente"](
            MotorProtegido(), "etl_ensaio_m2_20261119_180000_a1b2c3"
        )
