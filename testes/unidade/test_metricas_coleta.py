"""Auditoria de tentativas por execução, sem consultar o bronze novamente."""

import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from pipeline_etl.processamento import pipeline, pipeline_ibge


@pytest.mark.parametrize("ibge", [False, True])
@pytest.mark.parametrize("interromper", [False, True])
def test_persiste_delta_no_pai_inclusive_interrupcao(monkeypatch, ibge, interromper):
    modulo = pipeline_ibge if ibge else pipeline
    identificador = uuid4()
    cliente = SimpleNamespace(metricas_coleta={"requisicoes": 10, "retentativas": 4})
    motor = MagicMock()
    monkeypatch.setattr(modulo, "proteger_coordenacao", lambda *_, **__: nullcontext())
    monkeypatch.setattr(modulo, "_iniciar", lambda *_: identificador)
    monkeypatch.setattr(modulo, "_finalizar_falha", lambda *_: None)

    def coordenar(*_):
        cliente.metricas_coleta = {"requisicoes": 13, "retentativas": 6}
        if interromper:
            raise ValueError("interrupção simulada")
        if ibge:
            return pipeline_ibge.ResumoPipelineIBGE("SUCESSO", ())
        return pipeline.ResumoPipeline("SUCESSO", (), None)

    monkeypatch.setattr(modulo, "executar_ibge" if ibge else "_coordenar", coordenar)
    executar = modulo.executar_ibge_coordenado if ibge else modulo.executar_pipeline
    if interromper:
        with pytest.raises(ValueError, match="interrupção simulada"):
            executar(cliente, Mock(), motor, motor, "incremental")
    else:
        assert executar(cliente, Mock(), motor, motor, "incremental").situacao == "SUCESSO"
    chamadas = motor.begin.return_value.__enter__.return_value.execute.call_args_list
    registros = [
        chamada.args[1] for chamada in chamadas if "metricas_coleta" in str(chamada.args[0])
    ]
    assert len(registros) == 1
    assert registros[0]["id"] == identificador
    assert json.loads(registros[0]["metricas"]) == {"requisicoes": 3, "retentativas": 2}


@pytest.mark.parametrize("valor", [Mock(), {}, {"requisicoes": True, "retentativas": 0}])
def test_cliente_sem_instrumentacao_nao_inventa_zero_observado(valor):
    assert pipeline._obter_metricas_coleta(SimpleNamespace(metricas_coleta=valor)) is None


def test_falha_ao_persistir_metricas_nao_substitui_etl():
    motor = MagicMock()
    motor.begin.side_effect = RuntimeError("senha=segredo")
    pipeline._persistir_metricas_coleta(motor, uuid4(), {"requisicoes": 1, "retentativas": 0})


def test_registra_periodos_validos_sem_reler_bronze(monkeypatch):
    cliente = Mock()
    cliente.coletar.return_value = SimpleNamespace(situacao="COLETADA", manifesto="manifesto")
    monkeypatch.setattr(pipeline_ibge, "ler_coleta", lambda *_: SimpleNamespace(corpo=b"[]"))
    monkeypatch.setattr(pipeline_ibge, "descobrir_periodos", lambda _: (2020, 2025))
    monkeypatch.setattr(
        pipeline_ibge, "carregar_ibge", lambda *_: SimpleNamespace(situacao="FALHA", motivo="carga")
    )
    periodos = []
    pipeline_ibge.executar_ibge(cliente, Mock(), Mock(), Mock(), registrar_periodos=periodos.append)
    assert periodos == [(2020, 2025)]


def test_coordenador_persiste_periodos_e_instante_utc(monkeypatch):
    from datetime import datetime

    identificador = uuid4()
    motor = MagicMock()
    monkeypatch.setattr(pipeline_ibge, "proteger_coordenacao", lambda *_, **__: nullcontext())
    monkeypatch.setattr(pipeline_ibge, "_iniciar", lambda *_: identificador)

    def executar(*argumentos):
        argumentos[6]((2020, 2025))
        return pipeline_ibge.ResumoPipelineIBGE("FALHA", (), motivo="COLETA_INCOMPLETA")

    monkeypatch.setattr(pipeline_ibge, "executar_ibge", executar)
    pipeline_ibge.executar_ibge_coordenado(Mock(), Mock(), motor, motor)
    chamadas = motor.begin.return_value.__enter__.return_value.execute.call_args_list
    registros = [chamada.args[1] for chamada in chamadas if "periodos" in chamada.args[1]]
    assert registros[0]["id"] == identificador
    parametros = json.loads(registros[0]["periodos"])
    assert parametros["anos_disponiveis"] == [2020, 2025]
    assert (
        datetime.fromisoformat(parametros["consulta_periodos_em"]).utcoffset().total_seconds() == 0
    )


def test_telemetria_nao_suprime_interrupcao_do_processo():
    motor = MagicMock()
    motor.begin.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        pipeline._persistir_metricas_coleta(motor, uuid4(), {"requisicoes": 1, "retentativas": 0})
