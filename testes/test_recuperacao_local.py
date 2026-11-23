"""Protege a comparação de SQL no verificador manual de recuperação."""

import importlib.util
import subprocess
import sys
from pathlib import Path

ESPECIFICACAO = importlib.util.spec_from_file_location(
    "ensaio_recuperacao",
    Path(__file__).resolve().parents[1] / "scripts/ensaiar_recuperacao_local.py",
)
assert ESPECIFICACAO is not None and ESPECIFICACAO.loader is not None
ENSAIO = importlib.util.module_from_spec(ESPECIFICACAO)
ESPECIFICACAO.loader.exec_module(ENSAIO)


def test_normalizar_cast_equivalente_de_array_textual() -> None:
    original = "CHECK (situacao = ANY ((ARRAY['SUCESSO'::character varying])::text[]))"
    restaurado = "CHECK (situacao = ANY (ARRAY[('SUCESSO'::character varying)::text]))"
    assert ENSAIO.normalizar_sql(original) == ENSAIO.normalizar_sql(restaurado)


def test_normalizacao_preserva_valores_e_expressoes_diferentes() -> None:
    original = "CHECK (situacao = ANY ((ARRAY['SUCESSO'::character varying])::text[]))"
    diferente = original.replace("SUCESSO", "FALHA")
    assert ENSAIO.normalizar_sql(original) != ENSAIO.normalizar_sql(diferente)
    numerico = "CHECK (valor::numeric(24,10) > 0)"
    assert ENSAIO.normalizar_sql(numerico) == numerico


def test_verificador_http_recusa_python_com_asserts_desativados() -> None:
    caminho = Path(__file__).resolve().parents[1] / "scripts/verificar_api_local.py"
    resultado = subprocess.run(
        [sys.executable, "-O", str(caminho), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert resultado.returncode != 0
    assert "otimizacao" in resultado.stderr
