"""Recuperação exige ausência do processo local e aquisição da trava exclusiva."""

import os
import socket

import pytest
from sqlalchemy import text

from pipeline_etl.processamento.recuperacao import proteger_coordenacao

pytestmark = pytest.mark.integracao


def test_recupera_somente_processo_local_ausente(banco):
    with banco.begin() as conexao:
        identificadores = []
        for processo in (os.getpid(), 2147483646):
            identificadores.append(
                conexao.scalar(
                    text(
                        "INSERT INTO ops.execucao(modo,parametros) VALUES('pipeline_bcb',"
                        "jsonb_build_object('maquina',CAST(:maquina AS text),"
                        "'processo_id',CAST(:pid AS int))) "
                        "RETURNING execucao_id"
                    ),
                    {"maquina": socket.gethostname(), "pid": processo},
                )
            )
    with proteger_coordenacao(banco):
        pass
    with banco.connect() as conexao:
        estados = [
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"),
                {"id": identificador},
            )
            for identificador in identificadores
        ]
    assert estados == ["EM_EXECUCAO", "FALHA"]


def test_nao_inicia_dois_coordenadores_e_libera_trava(banco):
    with (
        proteger_coordenacao(banco),
        pytest.raises(RuntimeError, match="Outro coordenador"),
        proteger_coordenacao(banco),
    ):
        pass
    with proteger_coordenacao(banco):
        pass


def test_recupera_filho_aberto_de_pai_ja_finalizado(banco):
    with banco.begin() as conexao:
        pai = conexao.scalar(
            text(
                "INSERT INTO ops.execucao(modo,situacao,parametros) "
                "VALUES('pipeline_bcb','FALHA',jsonb_build_object('maquina',CAST(:maquina AS text),"
                "'processo_id',2147483646)) RETURNING execucao_id"
            ),
            {"maquina": socket.gethostname()},
        )
        filho = conexao.scalar(
            text(
                "INSERT INTO ops.execucao(modo,parametros) VALUES('carga_bcb',"
                "jsonb_build_object('pai_pipeline_id',CAST(:pai AS text))) RETURNING execucao_id"
            ),
            {"pai": str(pai)},
        )
    with proteger_coordenacao(banco):
        pass
    with banco.connect() as conexao:
        assert (
            conexao.scalar(
                text("SELECT situacao FROM ops.execucao WHERE execucao_id=:id"), {"id": filho}
            )
            == "FALHA"
        )


def test_coordenacao_ibge_e_exclusiva_e_independente_do_bcb(banco):
    with (
        proteger_coordenacao(banco),
        proteger_coordenacao(banco, dominio="ibge"),
        pytest.raises(RuntimeError, match="Outro coordenador"),
        proteger_coordenacao(banco, dominio="ibge"),
    ):
        pass
