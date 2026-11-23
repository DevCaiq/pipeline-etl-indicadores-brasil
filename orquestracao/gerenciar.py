"""Comandos locais do servidor, worker e deployments do projeto."""

import argparse
import asyncio
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx
from ambiente import RAIZ, configurar_ambiente
from controle_agendas import registrar_marco

NOMES_DEPLOYMENTS = {
    "bcb-incremental",
    "bcb-reconciliacao",
    "bcb-publicacao",
    "ibge-incremental",
    "ibge-localidades",
    "ibge-reconciliacao",
}


def aguardar_servidor() -> None:
    limite = time.monotonic() + 300
    with httpx.Client(trust_env=False, timeout=3) as cliente:
        while time.monotonic() < limite:
            try:
                if cliente.get("http://127.0.0.1:4200/api/health").status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(2)
        raise RuntimeError("Servidor local indisponível após cinco minutos.")


def preparar_retomada() -> None:
    """Consolida agendas vencidas sem cancelar remotamente execuções já iniciadas."""
    with httpx.Client(base_url="http://127.0.0.1:4200/api", trust_env=False, timeout=15) as cliente:
        resposta = cliente.post("/deployments/filter", json={})
        resposta.raise_for_status()
        registros = [
            item
            for item in resposta.json()
            if item.get("work_pool_name") == "pipeline-etl-local"
            and item.get("name") in NOMES_DEPLOYMENTS
        ]
        identificadores = [item["id"] for item in registros]
        if not identificadores:
            raise RuntimeError("Registre os deployments antes de iniciar o worker.")
        pendentes = []
        deslocamento = 0
        instante = datetime.now(UTC).isoformat()
        while True:
            resposta = cliente.post(
                "/flow_runs/filter",
                json={
                    "flow_runs": {
                        "deployment_id": {"any_": identificadores},
                        "state": {"type": {"any_": ["SCHEDULED"]}},
                        "next_scheduled_start_time": {"before_": instante},
                    },
                    "limit": 200,
                    "offset": deslocamento,
                },
            )
            resposta.raise_for_status()
            pagina = resposta.json()
            pendentes.extend(pagina)
            if len(pagina) < 200:
                break
            deslocamento += len(pagina)
        prioridades_ibge = {"ibge-incremental": 0, "ibge-localidades": 1, "ibge-reconciliacao": 2}
        nomes_por_id = {item["id"]: item["name"] for item in registros}
        atrasados_ibge = set()
        for item in pendentes:
            if item.get("auto_scheduled"):
                nome = nomes_por_id.get(item.get("deployment_id"))
                if nome in prioridades_ibge:
                    atrasados_ibge.add(nome)
        incremental = next(item for item in registros if item["name"] == "bcb-incremental")
        retorno = cliente.post(
            f"/deployments/{incremental['id']}/create_flow_run",
            json={
                "name": "retomada-local",
                "parameters": {"modo": "incremental"},
                "idempotency_key": "retomada-"
                + datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y%m%d%H%M"),
            },
        )
        retorno.raise_for_status()
        print("Retomada incremental:", retorno.json()["id"], flush=True)
        if atrasados_ibge:
            nome = max(atrasados_ibge, key=lambda nome: prioridades_ibge[nome])
            alvo = next(item for item in registros if item["name"] == nome)
            modo = nome.removeprefix("ibge-")
            retorno = cliente.post(
                f"/deployments/{alvo['id']}/create_flow_run",
                json={
                    "name": "retomada-ibge-local",
                    "parameters": {"modo": modo, "usar_s3": True},
                    "idempotency_key": "retomada-ibge-" + datetime.now(UTC).strftime("%Y%m%d%H%M"),
                },
            )
            retorno.raise_for_status()
            print("Retomada IBGE:", retorno.json()["id"], flush=True)
        # O marco só muda depois de confirmar as rodadas substitutas.
        # Sem cancelamentos remotos: uma execução que já iniciou permanece intacta.
        registrar_marco(RAIZ, datetime.fromisoformat(instante))


async def registrar() -> None:
    from prefect import flow
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate, WorkPoolUpdate
    from prefect.client.schemas.schedules import CronSchedule
    from prefect.exceptions import ObjectNotFound

    async with get_client() as cliente:
        try:
            grupo = await cliente.read_work_pool("pipeline-etl-local")
            if grupo.type != "process":
                raise ValueError("Pool existente incompatível; não será substituído.")
        except ObjectNotFound:
            await cliente.create_work_pool(
                WorkPoolCreate(name="pipeline-etl-local", type="process", concurrency_limit=1)
            )
        await cliente.update_work_pool("pipeline-etl-local", WorkPoolUpdate(concurrency_limit=1))
    fluxo = await flow.from_source(
        source=str(RAIZ), entrypoint="orquestracao/fluxos.py:executar_fluxo_bcb"
    )
    for nome, modo, cron, regra in [
        ("bcb-incremental", "incremental", "0 20 * * *", True),
        ("bcb-reconciliacao", "reconciliacao", "0 21 1-7 * 0", False),
        ("bcb-publicacao", "publicacao", "0 22 * * *", True),
    ]:
        identificador = await fluxo.deploy(
            name=nome,
            work_pool_name="pipeline-etl-local",
            build=False,
            push=False,
            schedules=[CronSchedule(cron=cron, timezone="America/Sao_Paulo", day_or=regra)],
            parameters={"modo": modo},
            concurrency_limit=1,
            job_variables={"working_dir": str(RAIZ)},
            print_next_steps=False,
        )
        print(nome, identificador)
    fluxo_ibge = await flow.from_source(
        source=str(RAIZ), entrypoint="orquestracao/fluxos.py:executar_fluxo_ibge"
    )
    for nome, modo, cron in [
        ("ibge-localidades", "localidades", "0 18 * * 0"),
        ("ibge-incremental", "incremental", "0 20 5 * *"),
        ("ibge-reconciliacao", "reconciliacao", "0 21 1 1,4,7,10 *"),
    ]:
        identificador = await fluxo_ibge.deploy(
            name=nome,
            work_pool_name="pipeline-etl-local",
            build=False,
            push=False,
            schedules=[CronSchedule(cron=cron, timezone="America/Sao_Paulo", day_or=True)],
            parameters={"modo": modo, "usar_s3": True},
            concurrency_limit=1,
            job_variables={"working_dir": str(RAIZ)},
            print_next_steps=False,
        )
        print(nome, identificador)


def executar() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__)
    argumentos.add_argument("acao", choices=["servidor", "worker", "registrar"])
    opcoes = argumentos.parse_args()
    configurar_ambiente(servidor=opcoes.acao == "servidor")
    if opcoes.acao == "registrar":
        asyncio.run(registrar())
        return 0
    comando = [sys.executable, "-m", "prefect"]
    if opcoes.acao == "servidor":
        limite = time.monotonic() + 300
        while True:
            try:
                with socket.create_connection(("127.0.0.1", 55432), timeout=3):
                    break
            except OSError:
                if time.monotonic() > limite:
                    raise RuntimeError("Inicie Docker/PostgreSQL antes do Prefect.") from None
                time.sleep(2)
        comando += ["server", "start", "--host", "127.0.0.1", "--port", "4200"]
    else:
        aguardar_servidor()
        preparar_retomada()
        comando += [
            "worker",
            "start",
            "--pool",
            "pipeline-etl-local",
            "--type",
            "process",
            "--limit",
            "1",
        ]
    diretorio = RAIZ / ".cache/servicos"
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / (
        opcoes.acao + "_" + datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f") + ".log"
    )
    with caminho.open("x", encoding="utf-8") as registro:
        return subprocess.run(
            comando,
            cwd=RAIZ,
            env=os.environ.copy(),
            stdout=registro,
            stderr=subprocess.STDOUT,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).returncode


if __name__ == "__main__":
    raise SystemExit(executar())
