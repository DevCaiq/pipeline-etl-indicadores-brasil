"""Destino de replay S3 não pode apontar para bancos operacionais."""

import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize("destino", ["etl", "etl_testes", "postgres", "etl_ensaio_objetos_"])
def test_replay_recusa_destino_fora_do_padrao(destino, monkeypatch):
    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    conferir = runpy.run_path(str(pasta / "verificar_s3_local.py"))["conferir_destino"]
    with pytest.raises(ValueError, match="exclusivo"):
        conferir(destino)
