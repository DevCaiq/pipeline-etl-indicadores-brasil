"""Adaptador Prefect; lógica de negócio continua no ambiente principal."""

import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from controle_agendas import agenda_vencida
from prefect import flow

RAIZ = Path(__file__).resolve().parents[1]


def _estado_agenda_vencida() -> Any:
    from prefect.context import get_run_context
    from prefect.states import Cancelled

    execucao = get_run_context().flow_run
    if agenda_vencida(RAIZ, execucao.auto_scheduled, execucao.expected_start_time):
        return Cancelled(
            name="CanceladoNaRetomada",
            message="Agenda automática antiga consolidada; nenhuma coleta iniciada.",
        )
    return None


@flow(name="pipeline-bcb-local", retries=0, persist_result=False)
def executar_fluxo_bcb(
    modo: Literal["incremental", "reconciliacao", "publicacao"] = "incremental",
) -> Any:
    """Uma execução CLI, sem retry adicional ao cliente BCB."""
    estado = _estado_agenda_vencida()
    if estado is not None:
        return estado
    diretorio = RAIZ / ".cache/execucoes"
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / ("pipeline_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f") + ".log")
    with caminho.open("x", encoding="utf-8") as registro:
        resultado = subprocess.run(
            [
                str(RAIZ / ".venv/Scripts/python.exe"),
                str(RAIZ / "scripts/executar_pipeline_local.py"),
                "--modo",
                modo,
            ],
            cwd=RAIZ,
            stdout=registro,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=3600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if resultado.returncode:
        raise RuntimeError("Pipeline incompleto: consulte o log local " + str(caminho))
    return str(caminho)


@flow(name="pipeline-ibge-local", retries=0, persist_result=False)
def executar_fluxo_ibge(
    modo: Literal["incremental", "localidades", "reconciliacao", "publicacao"] = "incremental",
    usar_s3: bool = True,
) -> Any:
    """Usa o ambiente principal e a configuração privada; não duplica retries HTTP."""
    estado = _estado_agenda_vencida()
    if estado is not None:
        return estado
    diretorio = RAIZ / ".cache/execucoes"
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / (
        "pipeline_ibge_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f") + ".log"
    )
    comando = [
        str(RAIZ / ".venv/Scripts/python.exe"),
        str(RAIZ / "scripts/executar_ibge_local.py"),
        "--modo",
        modo,
    ]
    if usar_s3:
        comando += ["--configuracao-s3", str(RAIZ / ".env.armazenamento")]
    with caminho.open("x", encoding="utf-8") as registro:
        resultado = subprocess.run(
            comando,
            cwd=RAIZ,
            stdout=registro,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=3600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if resultado.returncode:
        raise RuntimeError("Pipeline IBGE incompleto: consulte o log local " + str(caminho))
    return str(caminho)
