"""Cópia limpa e stack PostgreSQL isolada; não usa credenciais ou volumes operacionais."""

import json
import os
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_hex

import httpx
import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import URL

RAIZ = Path(__file__).resolve().parents[1]


def exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise RuntimeError(mensagem)


def localizar_ferramenta(nome: str) -> Path:
    """Localiza executável instalado, sem depender de usuário ou sistema operacional."""
    caminho = shutil.which(nome)
    if caminho is None:
        raise RuntimeError(f"Ferramenta {nome} não encontrada no PATH.")
    return Path(caminho)


def executar() -> int:
    docker = localizar_ferramenta("docker")
    uv = localizar_ferramenta("uv")
    configuracao = Config(str(RAIZ / "alembic.ini"))
    configuracao.set_main_option("script_location", str(RAIZ / "migracoes"))
    revisao_esperada = ScriptDirectory.from_config(configuracao).get_current_head()
    instante = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    base = RAIZ / ".cache" / ("reproducao_m1_" + instante)
    copia = base / "projeto"
    copia.mkdir(parents=True, exist_ok=False)
    lista = (
        subprocess.run(
            [
                "git",
                "-c",
                "safe.directory=" + RAIZ.as_posix(),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            cwd=RAIZ,
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .split("\0")
    )
    arquivos = []
    for nome in filter(None, lista):
        origem = RAIZ / nome
        if not origem.is_file():
            continue
        destino = copia / nome
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
        arquivos.append(nome)
    exigir(not (copia / ".env.banco").exists(), "Credencial operacional não pode ser copiada.")
    projeto = "etl-m1-repro-" + instante.replace("_", "-")
    porta = 55433
    with socket.socket() as verificacao:
        verificacao.bind(("127.0.0.1", porta))
    credenciais = {
        nome: token_hex(24) for nome in ["ADMIN", "MIGRACOES", "PROCESSAMENTO", "API", "PUBLICADOR"]
    }
    (copia / ".env.banco").write_text(
        "".join(f"SENHA_BANCO_{nome}={valor}\n" for nome, valor in credenciais.items()),
        encoding="utf-8",
    )
    (copia / "compose.verificacao.yaml").write_text(
        """services:
  banco:
    ports: !override
      - "127.0.0.1:55433:5432"
""",
        encoding="utf-8",
    )
    ambiente = os.environ.copy()
    ambiente["PATH"] = str(docker.parent) + os.pathsep + ambiente.get("PATH", "")
    for nome in list(ambiente):
        if nome.startswith(("URL_BANCO_", "SENHA_BANCO_")):
            ambiente.pop(nome)
    comando_compose = [
        str(docker),
        "compose",
        "--project-name",
        projeto,
        "--env-file",
        ".env.banco",
        "-f",
        "compose.yaml",
        "-f",
        "compose.verificacao.yaml",
    ]
    api = None

    def comandar(argumentos: list[str], nome: str, tempo: int = 300):
        with (base / (nome + ".log")).open("x", encoding="utf-8") as registro:
            resultado = subprocess.run(
                argumentos,
                cwd=copia,
                env=ambiente,
                stdout=registro,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=tempo,
            )
        exigir(resultado.returncode == 0, "Etapa falhou: " + nome + "; consulte log privado.")

    try:
        comandar(["git", "init", "--initial-branch", "validacao-local"], "git_isolado")
        comandar([str(uv), "sync", "--frozen"], "instalacao")
        print("Cópia limpa instalada pelo lock.", flush=True)
        comandar(comando_compose + ["up", "-d", "--wait", "banco"], "banco")
        comandar(comando_compose + ["run", "--build", "--rm", "migracoes"], "migracoes", 600)
        print("Banco/migrações isolados verificados.", flush=True)
        with psycopg.connect(
            host="127.0.0.1",
            port=porta,
            dbname="etl",
            user="administrador",
            password=credenciais["ADMIN"],
            autocommit=True,
            connect_timeout=5,
        ) as conexao:
            exigir(
                conexao.execute("SELECT count(*) FROM core.dim_serie").fetchone()[0] == 3,
                "Catálogo inicial inválido.",
            )
            exigir(
                conexao.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == revisao_esperada,
                "Revisão inesperada na cópia limpa.",
            )
            conexao.execute("CREATE DATABASE etl_testes OWNER migracoes")
        python = copia / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        endereco = URL.create(
            "postgresql+psycopg",
            username="migracoes",
            password=credenciais["MIGRACOES"],
            host="127.0.0.1",
            port=porta,
            database="etl_testes",
        )
        ambiente["URL_BANCO_TESTES"] = endereco.render_as_string(hide_password=False)
        for nome in ("API", "PUBLICADOR", "PROCESSAMENTO"):
            ambiente["SENHA_BANCO_" + nome + "_TESTES"] = credenciais[nome]
        comandar([str(python), "-m", "pytest", "--cov", "--cov-report=term-missing"], "testes", 600)
        print("Suíte completa passou na cópia/banco independentes.", flush=True)
        endereco = endereco.set(username="api_leitura", password=credenciais["API"], database="etl")
        (copia / ".env.api").write_text(
            "URL_BANCO_API="
            + endereco.render_as_string(hide_password=False)
            + "\nSEGREDO_CURSOR="
            + token_hex(32)
            + "\n",
            encoding="utf-8",
        )
        with socket.socket() as reserva:
            reserva.bind(("127.0.0.1", 0))
            porta_api = reserva.getsockname()[1]
        with (base / "api.log").open("x", encoding="utf-8") as registro:
            api = subprocess.Popen(
                [str(python), "-m", "pipeline_etl", "servir", "--porta", str(porta_api)],
                cwd=copia,
                env=ambiente,
                stdout=registro,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            limite = time.monotonic() + 30
            with httpx.Client(
                base_url=f"http://127.0.0.1:{porta_api}", trust_env=False, timeout=3
            ) as cliente:
                while True:
                    try:
                        if cliente.get("/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    exigir(
                        api.poll() is None and time.monotonic() < limite, "API limpa não iniciou."
                    )
                    time.sleep(0.2)
                respostas = {
                    rota: cliente.get(rota).status_code
                    for rota in [
                        "/health",
                        "/ready",
                        "/api/v1/series",
                        "/api/v1/series/432/observacoes",
                        "/api/v1/series/432/agregados",
                        "/docs",
                        "/openapi.json",
                    ]
                }
                exigir(all(estado == 200 for estado in respostas.values()), "Smoke HTTP falhou.")
                exigir(len(cliente.get("/api/v1/series").json()["data"]) == 3, "Seed API inválido.")
        relatorio = {
            "instante_utc": instante,
            "copia": str(copia),
            "projeto_compose": projeto,
            "porta_postgres": porta,
            "arquivos_copiados": len(arquivos),
            "http": respostas,
            "instalacao_frozen_offline": False,
            "migracao": revisao_esperada,
            "credenciais_operacionais_copiadas": False,
            "suite_completa": True,
            "sem_dados_operacionais": True,
        }
        destino = RAIZ / "dados/descoberta" / ("reproducao_m1_" + instante + ".json")
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("x", encoding="utf-8") as saida:
            json.dump(relatorio, saida, ensure_ascii=False, indent=2)
        print(json.dumps(relatorio, ensure_ascii=False), flush=True)
        return 0
    finally:
        if api is not None:
            api.terminate()
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait(timeout=5)
        # Projeto exclusivo; não remove volumes nem para os serviços do ambiente operacional.
        with (base / "encerramento.log").open("x", encoding="utf-8") as registro:
            subprocess.run(
                comando_compose + ["down"],
                cwd=copia,
                env=ambiente,
                stdout=registro,
                stderr=subprocess.STDOUT,
                check=False,
                timeout=60,
            )


if __name__ == "__main__":
    raise SystemExit(executar())
