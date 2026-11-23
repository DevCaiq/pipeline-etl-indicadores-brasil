"""Coordenação independente por série e publicação sem repetir HTTP."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from pipeline_etl.processamento.atualizacao import ResumoAtualizacao
from pipeline_etl.processamento.pipeline import executar_pipeline
from pipeline_etl.processamento.publicacao import ResumoPublicacao


@pytest.mark.parametrize(
    "situacoes,publicacao,esperada",
    [
        (["SUCESSO"] * 3, "SUCESSO", "SUCESSO"),
        (["SUCESSO", "FALHA", "SUCESSO"], "SUCESSO", "PARCIAL"),
        (["FALHA"] * 3, "SUCESSO", "FALHA"),
        (["SUCESSO"] * 3, "FALHA", "PARCIAL"),
        (["IGNORADA"] * 3, "SUCESSO", "FALHA"),
        (["PARCIAL", "FALHA", "FALHA"], "FALHA", "PARCIAL"),
    ],
)
def test_estado_global_sem_retry(monkeypatch, situacoes, publicacao, esperada):
    atualizar = Mock(
        side_effect=[
            ResumoAtualizacao(codigo, situacao)
            for codigo, situacao in zip((432, 433, 1), situacoes, strict=True)
        ]
    )
    publicar = Mock(return_value=ResumoPublicacao(uuid4(), publicacao))
    monkeypatch.setattr("pipeline_etl.processamento.pipeline.atualizar_serie", atualizar)
    monkeypatch.setattr("pipeline_etl.processamento.pipeline.publicar_bcb", publicar)
    monkeypatch.setattr("pipeline_etl.processamento.pipeline._iniciar", lambda *_: uuid4())
    motor = MagicMock()
    assert executar_pipeline(Mock(), Mock(), motor, motor, "incremental").situacao == esperada
    assert atualizar.call_count == 3 and publicar.call_count == 1


def test_excecao_nao_bloqueia_outras_series(monkeypatch):
    atualizar = Mock(
        side_effect=[
            RuntimeError("falha"),
            ResumoAtualizacao(433, "SUCESSO"),
            ResumoAtualizacao(1, "SUCESSO"),
        ]
    )
    publicar = Mock(return_value=ResumoPublicacao(uuid4(), "IGNORADA", motivo="JA_PUBLICADA"))
    monkeypatch.setattr("pipeline_etl.processamento.pipeline.atualizar_serie", atualizar)
    monkeypatch.setattr("pipeline_etl.processamento.pipeline.publicar_bcb", publicar)
    monkeypatch.setattr("pipeline_etl.processamento.pipeline._iniciar", lambda *_: uuid4())
    motor = MagicMock()
    assert executar_pipeline(Mock(), Mock(), motor, motor, "incremental").situacao == "PARCIAL"
    assert atualizar.call_count == 3


def test_preserva_execucao_da_falha_tecnica(monkeypatch):
    from pipeline_etl.processamento.atualizacao import ErroAtualizacao

    identificador = uuid4()
    monkeypatch.setattr(
        "pipeline_etl.processamento.pipeline.atualizar_serie",
        Mock(
            side_effect=[
                ErroAtualizacao(identificador),
                ResumoAtualizacao(433, "SUCESSO"),
                ResumoAtualizacao(1, "SUCESSO"),
            ]
        ),
    )
    monkeypatch.setattr("pipeline_etl.processamento.pipeline._iniciar", lambda *_: uuid4())
    monkeypatch.setattr(
        "pipeline_etl.processamento.pipeline.publicar_bcb",
        Mock(return_value=ResumoPublicacao(uuid4(), "SUCESSO")),
    )
    motor = MagicMock()
    resultado = executar_pipeline(Mock(), Mock(), motor, motor, "incremental")
    assert resultado.atualizacoes[0].execucao_id == identificador


def test_progresso_auditado_nao_se_perde_apos_excecao(monkeypatch):
    monkeypatch.setattr(
        "pipeline_etl.processamento.pipeline.atualizar_serie",
        Mock(side_effect=RuntimeError("interrupção")),
    )
    monkeypatch.setattr("pipeline_etl.processamento.pipeline._iniciar", lambda *_: uuid4())
    monkeypatch.setattr(
        "pipeline_etl.processamento.pipeline.publicar_bcb",
        Mock(return_value=ResumoPublicacao(uuid4(), "FALHA")),
    )
    motor = MagicMock()
    motor.connect.return_value.__enter__.return_value.scalar.return_value = True
    assert executar_pipeline(Mock(), Mock(), motor, motor, "incremental").situacao == "PARCIAL"


def test_falha_ambigua_ao_obter_trava_invalida_conexao():
    from pipeline_etl.processamento.recuperacao import proteger_coordenacao

    motor = MagicMock()
    conexao = motor.connect.return_value.execution_options.return_value.__enter__.return_value
    conexao.scalar.side_effect = RuntimeError("resposta perdida")
    with pytest.raises(RuntimeError, match="resposta perdida"), proteger_coordenacao(motor):
        pass
    conexao.invalidate.assert_called_once()


@pytest.mark.parametrize("erro", [OSError("indisponível"), UnicodeError("codificação")])
def test_duvida_na_consulta_de_processo_preserva_auditoria(monkeypatch, erro):
    from types import SimpleNamespace

    from pipeline_etl.processamento import recuperacao

    monkeypatch.setattr(recuperacao, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(recuperacao, "_consultar_processo_windows", Mock(side_effect=erro))
    assert recuperacao.processo_presente(999999) is True
