"""Métricas do ensaio contam erros e usam percentil por posto mais próximo."""

import importlib.util
from pathlib import Path

import pytest

ESPECIFICACAO = importlib.util.spec_from_file_location(
    "ensaio_desempenho", Path(__file__).resolve().parents[1] / "scripts/medir_desempenho_local.py"
)
assert ESPECIFICACAO is not None and ESPECIFICACAO.loader is not None
ENSAIO = importlib.util.module_from_spec(ESPECIFICACAO)
ESPECIFICACAO.loader.exec_module(ENSAIO)


def test_percentis_e_vazao_com_amostra_conhecida():
    resumo = ENSAIO.resumir(
        [{"status": 200, "milissegundos": indice} for indice in range(1, 101)], 10
    )
    assert (resumo["p50_ms"], resumo["p95_ms"], resumo["p99_ms"]) == (50, 95, 99)
    assert resumo["requisicoes_por_segundo"] == 10
    assert resumo["meta_local_atendida"] is True


@pytest.mark.parametrize(
    "estado,erro_validacao", [(0, False), (429, False), (503, False), (200, True)]
)
def test_erro_nao_e_apresentado_como_meta_atendida(estado, erro_validacao):
    resumo = ENSAIO.resumir(
        [{"status": estado, "milissegundos": 1, "erro_validacao": erro_validacao}], 1
    )
    assert resumo["meta_local_atendida"] is False


def test_sem_requisicoes_nao_produz_resultado_positivo():
    with pytest.raises(RuntimeError):
        ENSAIO.resumir([], 60)
