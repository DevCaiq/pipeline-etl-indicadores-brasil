"""O retrato de restauração distingue tipos SQL com tamanhos diferentes."""

import runpy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integracao


def test_retrato_detecta_alteracao_do_tamanho_varchar(banco, monkeypatch):
    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    retratar = runpy.run_path(str(pasta / "ensaiar_restauracao_m2.py"))["retratar_m2"]
    nome = "ensaio_tipo_m2_" + uuid4().hex
    with banco.begin() as conexao:
        conexao.execute(text(f"CREATE TABLE core.{nome}(valor varchar(2))"))
    try:
        antes = retratar(banco)
        with banco.begin() as conexao:
            conexao.execute(text(f"ALTER TABLE core.{nome} ALTER valor TYPE varchar(3)"))
        depois = retratar(banco)
        assert antes["tabelas"] == depois["tabelas"]
        assert antes["catalogo"]["tipos_completos"] != depois["catalogo"]["tipos_completos"]
    finally:
        with banco.begin() as conexao:
            conexao.execute(text(f"DROP TABLE core.{nome}"))
