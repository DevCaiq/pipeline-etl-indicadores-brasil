"""Proteções e critérios do benchmark sintético isolado."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture
def ensaio(monkeypatch):
    pasta = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(pasta))
    return runpy.run_path(str(pasta / "medir_desempenho_m2.py"))


@pytest.mark.parametrize("banco", ["etl", "etl_testes", "postgres", "etl_benchmark_m2_"])
def test_benchmark_recusa_destinos_operacionais(ensaio, banco):
    with pytest.raises(ValueError, match="exclusivo"):
        ensaio["conferir_destino"](banco)


def test_benchmark_aceita_apenas_destino_gerado(ensaio):
    ensaio["conferir_destino"]("etl_benchmark_m2_20261119_180000_a1b2c3")


def test_meta_com_cache_usa_250ms_e_recusa_qualquer_erro(ensaio):
    avaliar = ensaio["avaliar_meta"]
    resumo = {
        "p95_ms": 300,
        "percentual_5xx": 0,
        "estados_http": {"200": 10},
        "erros_transporte": 0,
        "erros_validacao": 0,
    }
    assert avaliar(resumo, False)
    assert not avaliar(resumo, True)
    resumo["p95_ms"] = 200
    assert avaliar(resumo, True)
    resumo["estados_http"] = {"200": 9, "429": 1}
    assert not avaliar(resumo, True)


def test_seed_define_um_milhao_sem_observacoes_futuras(ensaio):
    from datetime import date, timedelta

    assert ensaio["SERIES_SINTETICAS"] * ensaio["DIAS_POR_SERIE"] == 1_000_000
    assert date(2020, 1, 1) + timedelta(days=ensaio["DIAS_POR_SERIE"] - 1) == date(2026, 11, 4)


def test_medidor_distingue_resposta_cacheada_de_calculo(ensaio):
    class CacheFalso:
        def __init__(self):
            self.valor = None

        def obter_ou_calcular(self, chave, calcular, validade):
            if self.valor is None:
                self.valor = calcular()
            return self.valor

    medidor = ensaio["MedidorCache"](CacheFalso())
    assert medidor.obter_ou_calcular("chave", lambda: b"corpo") == b"corpo"
    assert medidor.obter_ou_calcular("chave", lambda: b"outro") == b"corpo"
    assert medidor.retratar() == {"acertos": 1, "calculos": 1}


def test_limpeza_confirma_rotulo_e_relata_falha_sem_lancar(ensaio, monkeypatch):
    from types import SimpleNamespace

    chamadas = []

    def executar(comando, **opcoes):
        chamadas.append(comando)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    limpar = ensaio["limpar_redis_exclusivo"]
    monkeypatch.setattr(limpar.__globals__["subprocess"], "run", executar)
    assert limpar("docker", "ensaio-unico")["confirmada"] is True
    assert "label=pipeline_etl.benchmark=ensaio-unico" in chamadas[0]

    def falhar(*_, **opcoes):
        raise TimeoutError()

    monkeypatch.setattr(limpar.__globals__["subprocess"], "run", falhar)
    assert limpar("docker", "ensaio-unico")["confirmada"] is False
