"""Frescor usa calendário oficial arquivado, limites de vigência e fallback explícito."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline_etl.processamento.frescor import (
    avaliar_frescor,
    carregar_calendario,
)


def test_auditoria_nao_emite_aviso_heuristico_para_outubro_em_dia(monkeypatch) -> None:
    from pipeline_etl.processamento.auditoria import _avisos_qualidade

    sessao = Mock()
    sessao.scalar.return_value = None
    verificado = SimpleNamespace(
        manifesto=SimpleNamespace(codigo_serie=433),
        artefatos=[SimpleNamespace(inicio=date(2026, 1, 1), fim=date(2026, 11, 18))],
    )
    resultado = SimpleNamespace(
        contagens=SimpleNamespace(lidas=10), observacoes=[SimpleNamespace(data=date(2026, 10, 1))]
    )
    avisos = _avisos_qualidade(sessao, verificado, 0, resultado, date(2026, 11, 18))
    assert "FRESCOR_POTENCIALMENTE_DEFASADO" not in avisos


def test_outubro_esta_em_dia_pelo_calendario_oficial() -> None:
    calendario, motivo = carregar_calendario()
    assert calendario is not None and motivo is None
    avaliacao = avaliar_frescor(433, date(2026, 10, 1), date(2026, 11, 18), calendario)
    assert avaliacao.defasado is False
    assert avaliacao.politica == "CALENDARIO_IBGE"
    assert avaliacao.referencia_esperada == date(2026, 10, 1)
    assert avaliacao.data_limite == date(2026, 11, 13)
    assert avaliacao.versao_calendario == calendario.versao


@pytest.mark.parametrize("dia,defasado", [(10, False), (11, False), (12, False), (13, True)])
def test_divulgacao_e_um_dia_completo_de_tolerancia(dia: int, defasado: bool) -> None:
    calendario, _ = carregar_calendario()
    avaliacao = avaliar_frescor(433, date(2026, 10, 1), date(2026, 12, dia), calendario)
    assert avaliacao.defasado is defasado
    assert avaliacao.politica == "CALENDARIO_IBGE"


@pytest.mark.parametrize(
    "hoje,motivo",
    [
        (date(2026, 11, 17), "CALENDARIO_AINDA_NAO_VIGENTE"),
        (date(2026, 12, 19), "CALENDARIO_EXPIRADO"),
    ],
)
def test_calendario_nao_e_usado_fora_da_vigencia(hoje: date, motivo: str) -> None:
    calendario, _ = carregar_calendario()
    avaliacao = avaliar_frescor(433, date(2026, 10, 1), hoje, calendario)
    assert avaliacao.politica == "HEURISTICA_45_DIAS"
    assert avaliacao.motivo == motivo
    assert avaliacao.versao_calendario is None


def test_vigencia_inclui_o_trigesimo_dia() -> None:
    calendario, _ = carregar_calendario()
    assert avaliar_frescor(433, date(2026, 11, 1), date(2026, 12, 18), calendario).politica == (
        "CALENDARIO_IBGE"
    )


@pytest.mark.parametrize(
    "codigo,idade,esperado", [(433, 45, False), (433, 46, True), (432, 4, False), (1, 5, True)]
)
def test_heuristica_preserva_limites_anteriores(codigo: int, idade: int, esperado: bool) -> None:
    from datetime import timedelta

    hoje = date(2026, 11, 18)
    referencia = hoje - timedelta(days=idade)
    if codigo == 433:
        # O fallback mantém a regra por dias, mas o contrato mensal continua estrito.
        hoje = date(2026, 10, 1) + timedelta(days=idade)
        referencia = date(2026, 10, 1)
    avaliacao = avaliar_frescor(codigo, referencia, hoje)
    assert avaliacao.defasado is esperado
    assert avaliacao.politica == ("HEURISTICA_45_DIAS" if codigo == 433 else "HEURISTICA_4_DIAS")


@pytest.mark.parametrize("referencia", [None, date(2026, 12, 1), date(2026, 10, 2)])
def test_referencia_ausente_futura_ou_mensal_invalida_e_indeterminada(referencia) -> None:
    calendario, _ = carregar_calendario()
    avaliacao = avaliar_frescor(433, referencia, date(2026, 11, 18), calendario)
    assert avaliacao.defasado is None
    assert avaliacao.motivo in {"SEM_REFERENCIA", "REFERENCIA_INVALIDA"}


def test_calendario_ausente_ou_corrompido_nao_impede_a_leitura(tmp_path) -> None:
    caminho = tmp_path / "calendario.json"
    assert carregar_calendario(caminho) == (None, "CALENDARIO_AUSENTE")
    caminho.write_text("{}", encoding="utf-8")
    assert carregar_calendario(caminho) == (None, "CALENDARIO_INVALIDO")


@pytest.mark.parametrize(
    "alteracao", ["quantidade", "ordem", "id", "produto", "divulgacao", "fuso", "versao", "sha"]
)
def test_rejeita_calendario_inconsistente(tmp_path, alteracao):
    import json
    from importlib.resources import files

    conteudo = json.loads(files("pipeline_etl").joinpath("calendarios/ipca_2026.json").read_bytes())
    if alteracao == "quantidade":
        conteudo["divulgacoes"].pop()
    elif alteracao == "ordem":
        conteudo["divulgacoes"].reverse()
    elif alteracao == "id":
        conteudo["divulgacoes"][1]["identificador_origem"] = conteudo["divulgacoes"][0][
            "identificador_origem"
        ]
    elif alteracao == "produto":
        conteudo["produto_id"] = 9258
    elif alteracao == "divulgacao":
        conteudo["divulgacoes"][0]["data_divulgacao"] = "2026-01-01"
    elif alteracao == "fuso":
        conteudo["consultado_em"] = "2026-11-19T00:55:35"
    elif alteracao == "versao":
        conteudo["versao"] = "outra"
    else:
        conteudo["fonte_sha256"] = "invalido"
    caminho = tmp_path / "calendario.json"
    caminho.write_text(json.dumps(conteudo), encoding="utf-8")
    assert carregar_calendario(caminho) == (None, "CALENDARIO_INVALIDO")


@pytest.mark.parametrize(
    "inicio,fim,referencia,esperado",
    [
        (date(2026, 1, 1), date(2026, 11, 18), date(2026, 9, 1), True),
        (date(2026, 11, 1), date(2026, 11, 18), date(2026, 11, 1), False),
        (date(2020, 1, 1), date(2020, 12, 31), date(2020, 10, 1), False),
    ],
)
def test_aviso_de_atraso_so_abrange_janela_que_contem_referencia_esperada(
    inicio, fim, referencia, esperado
):
    from pipeline_etl.processamento.auditoria import _avisos_qualidade

    sessao = Mock()
    sessao.scalar.return_value = None
    verificado = SimpleNamespace(
        manifesto=SimpleNamespace(codigo_serie=433),
        artefatos=[SimpleNamespace(inicio=inicio, fim=fim)],
    )
    resultado = SimpleNamespace(
        contagens=SimpleNamespace(lidas=1), observacoes=[SimpleNamespace(data=referencia)]
    )
    avisos = _avisos_qualidade(sessao, verificado, 0, resultado, date(2026, 11, 18))
    assert ("FRESCOR_POTENCIALMENTE_DEFASADO" in avisos) is esperado
