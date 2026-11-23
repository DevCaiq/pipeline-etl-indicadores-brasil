"""Marco da retomada preserva rodadas manuais e agendas futuras."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "automatica,deslocamento,esperado",
    [
        (True, -60, True),
        (True, 60, False),
        (False, -60, False),
        (False, 60, False),
    ],
)
def test_somente_agenda_automatica_anterior_ao_marco_e_descartada(
    monkeypatch,
    tmp_path,
    automatica,
    deslocamento,
    esperado,
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "orquestracao"))
    from controle_agendas import agenda_vencida, registrar_marco

    marco = datetime(2026, 11, 19, 12, tzinfo=UTC)
    registrar_marco(tmp_path, marco)
    assert agenda_vencida(tmp_path, automatica, marco + timedelta(seconds=deslocamento)) is esperado
