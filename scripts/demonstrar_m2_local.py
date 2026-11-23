"""Demonstra M2 com restauração, replay e API em clone novo, sem coleta externa."""

import json
import secrets
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import dotenv_values
from ensaiar_recuperacao_local import exigir, retratar, soma_logica
from ensaiar_restauracao_m2 import comparar_api, conferir_destino
from ensaiar_restauracao_m2 import executar as restaurar
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import URL, text

from pipeline_etl.api.aplicacao import criar_aplicacao
from pipeline_etl.banco.sessoes import criar_motor
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.armazenamento.objetos import ObjetoBronze, SistemaArquivosObjetos
from pipeline_etl.processamento.carga import carregar_manifesto
from pipeline_etl.processamento.carga_ibge import carregar_ibge, publicar_ibge
from pipeline_etl.processamento.publicacao import publicar_bcb

RAIZ = Path(__file__).resolve().parents[1]


def marcar_publicacao_pendente(motor, destino: str) -> None:
    """Força refresh somente no banco exclusivo criado pelo ensaio."""
    conferir_destino(destino)
    with motor.begin() as conexao:
        exigir(
            conexao.scalar(text("SELECT current_database()")) == destino,
            "Conexão não aponta para o clone exclusivo.",
        )
        conexao.execute(
            text(
                "UPDATE ops.publicacao SET data_publicacao=NULL,situacao='PENDENTE' "
                "WHERE dominio IN ('bcb','ibge')"
            )
        )


def conferir_gold_recalculada(motor, destino: str) -> dict:
    """Confere todas as linhas contra a definição SQL, sem ignorar metadados temporais."""
    conferir_destino(destino)
    resultado = {}
    with motor.begin() as conexao:
        conexao.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        exigir(
            conexao.scalar(text("SELECT current_database()")) == destino,
            "Conexão não aponta para o clone exclusivo.",
        )
        for nome in (
            "mv_serie_mensal",
            "mv_serie_anual",
            "mv_ipca_12m",
            "mv_populacao_uf",
            "mv_populacao_regiao",
            "mv_populacao_brasil",
        ):
            definicao = (
                conexao.scalar(
                    text("SELECT pg_get_viewdef(to_regclass(:nome),true)"), {"nome": "mart." + nome}
                )
                .strip()
                .rstrip(";")
            )
            # Nomes são fechados; a definição é o SELECT do catálogo administrado pelo projeto.
            atual = (
                conexao.execute(text(f"SELECT to_jsonb(t)::text FROM mart.{nome} t ORDER BY 1"))
                .scalars()
                .all()
            )
            esperado = (
                conexao.execute(text(f"SELECT to_jsonb(t)::text FROM ({definicao}) t ORDER BY 1"))
                .scalars()
                .all()
            )
            exigir(atual == esperado, "Materializada diverge do cálculo confirmado: " + nome)
            resultado[nome] = soma_logica(atual)
    return resultado


def executar() -> int:
    """Preserva origem e clone; registra durações e evidências privadas."""
    inicio = time.monotonic()
    instante = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    pasta = RAIZ / "dados/descoberta"
    pasta.mkdir(parents=True, exist_ok=True)
    relatorio = {"iniciado_em": datetime.now(UTC).isoformat(), "situacao": "EM_EXECUCAO"}
    motores = []
    segredos = dotenv_values(RAIZ / ".env.banco", interpolate=False)

    def motor_local(banco, papel):
        if banco != "etl":
            conferir_destino(banco)
        chave = {"administrador": "ADMIN", "api_leitura": "API"}.get(papel, papel.upper())
        endereco = URL.create(
            "postgresql+psycopg",
            username=papel,
            password=segredos["SENHA_BANCO_" + chave],
            host="127.0.0.1",
            port=55432,
            database=banco,
        )
        motor = criar_motor(SecretStr(endereco.render_as_string(hide_password=False)))
        motores.append(motor)
        return motor

    try:
        print("Etapa 1: backup, restauração e comparação integral.", flush=True)
        existentes = set(pasta.glob("restauracao_m2_*.json"))
        fase = time.monotonic()
        exigir(restaurar() == 0, "Restauração M2 falhou.")
        novos = set(pasta.glob("restauracao_m2_*.json")) - existentes
        exigir(len(novos) == 1, "Relatório de restauração ambíguo.")
        caminho = novos.pop()
        restauracao = json.loads(caminho.read_text(encoding="utf-8"))
        destino = restauracao["destino"]
        conferir_destino(destino)
        relatorio["restauracao"] = {
            "segundos": round(time.monotonic() - fase, 3),
            "relatorio": str(caminho.relative_to(RAIZ)),
            "destino": destino,
        }
        origem = motor_local("etl", "administrador")
        antes = retratar(origem)
        clone = motor_local(destino, "administrador")
        dados_antes = {
            n: v for n, v in retratar(clone)["tabelas"].items() if n.startswith(("core.", "mart."))
        }
        with clone.begin() as conexao:
            conexao.execute(text("SET TRANSACTION READ ONLY"))
            plano = (
                conexao.execute(
                    text(
                        "SELECT l.manifesto FROM ops.lote l JOIN ops.execucao e USING(execucao_id) "
                        "WHERE e.modo='carga_bcb' AND e.situacao='SUCESSO' "
                        "ORDER BY l.confirmado_em,l.execucao_id"
                    )
                )
                .scalars()
                .all()
            )
            parametros = conexao.scalar(
                text(
                    "SELECT e.parametros FROM ops.execucao e JOIN ops.lote l USING(execucao_id) "
                    "LEFT JOIN ops.execucao p "
                    "ON p.execucao_id::text=e.parametros->>'pai_pipeline_id' "
                    "WHERE e.modo='carga_ibge' AND e.situacao='SUCESSO' AND l.fonte='ibge' "
                    "AND COALESCE(p.parametros->'armazenamento'->>'tipo','arquivos')='arquivos' "
                    "ORDER BY e.finalizado_em DESC LIMIT 1"
                )
            )
        exigir(bool(plano) and parametros is not None, "Bronze BCB/IBGE prévio obrigatório.")
        processamento = motor_local(destino, "processamento")
        publicador = motor_local(destino, "publicador")
        print("Etapa 2: replay bronze BCB/IBGE somente no clone.", flush=True)
        fase = time.monotonic()
        cargas = []
        armazenamento = ArmazenamentoBronze(RAIZ / "dados/bronze")
        for manifesto in plano:
            carga = carregar_manifesto(armazenamento, Path(manifesto), processamento)
            exigir(carga.situacao == "SUCESSO", "Replay BCB falhou.")
            cargas.append(asdict(carga))
        objetos = SistemaArquivosObjetos(RAIZ / "dados/bronze")
        manifestos = tuple(ObjetoBronze(**objeto) for objeto in parametros["manifestos"])
        carga_ibge = carregar_ibge(objetos, manifestos, processamento)
        exigir(carga_ibge.situacao == "SUCESSO", "Replay IBGE falhou.")
        relatorio["replay"] = {
            "segundos": round(time.monotonic() - fase, 3),
            "bcb": cargas,
            "ibge": asdict(carga_ibge),
            "manifestos_ibge": len(manifestos),
        }
        dados_replay = {
            n: v for n, v in retratar(clone)["tabelas"].items() if n.startswith(("core.", "mart."))
        }
        exigir(dados_antes == dados_replay, "Replay alterou dados ou metadados confirmados.")
        relatorio["replay_core_gold_preservados"] = True
        relatorio["api_clone"] = comparar_api(
            motor_local("etl", "api_leitura"), motor_local(destino, "api_leitura")
        )
        fase = time.monotonic()
        print("Etapa 3: publicação e conferência core/gold/API.", flush=True)
        # Apenas o controle de publicação do clone é marcado pendente para exercitar refresh.
        marcar_publicacao_pendente(clone, destino)
        publicacoes = [publicar_bcb(publicador), publicar_ibge(publicador)]
        relatorio["publicacao"] = {
            "segundos": round(time.monotonic() - fase, 3),
            "controle_pendente_somente_clone": True,
            "resultados": [asdict(p) for p in publicacoes],
        }
        exigir(
            all(p.situacao == "SUCESSO" for p in publicacoes),
            "Publicação não concluída.",
        )
        dados_depois = {
            n: v for n, v in retratar(clone)["tabelas"].items() if n.startswith(("core.", "mart."))
        }
        exigir(
            {n: v for n, v in dados_antes.items() if n.startswith("core.")}
            == {n: v for n, v in dados_depois.items() if n.startswith("core.")},
            "Publicação alterou fatos ou metadados core.",
        )
        # Uma nova publicação pode avançar referência e flags temporais da gold.
        # Validamos o snapshot novo, mantendo a comparação exata do replay acima.
        relatorio["gold_recalculada"] = conferir_gold_recalculada(clone, destino)
        configuracao = ConfiguracaoAplicacao(
            segredo_cursor=SecretStr(secrets.token_hex(48)),
            cache_habilitado=False,
            limite_requisicoes_minuto=1000,
        )
        with TestClient(
            criar_aplicacao(configuracao, motor_local(destino, "api_leitura"))
        ) as cliente:
            publicadas = {}
            for rota in (
                "/api/v1/series/432/agregados?de=2020-01-01&ate=2020-12-31",
                "/api/v1/indicadores/ipca-12m?de=2020-01-01&ate=2020-12-31",
                "/api/v1/populacao/brasil?ano=2026",
            ):
                resposta = cliente.get(rota)
                exigir(resposta.status_code == 200, "API gold republicada indisponível.")
                publicadas[rota] = resposta.status_code
                if rota.startswith("/api/v1/series/") or "/ipca-12m" in rota:
                    exigir(
                        resposta.json()["meta"]["data_publicacao"]
                        == publicacoes[0].data_publicacao.isoformat(),
                        "API gold republicada não usa a referência confirmada.",
                    )
            relatorio["api_gold_republicada"] = publicadas
        monitoramento = dotenv_values(RAIZ / ".env.monitoramento", interpolate=False)
        print("Etapa 4: monitoramento local, ETag e origem preservada.", flush=True)
        with httpx.Client(timeout=10, trust_env=False) as cliente:
            sondagens = {}
            for endereco in (
                "http://127.0.0.1:8001/ready",
                "http://127.0.0.1:8001/metrics",
                "http://127.0.0.1:9090/api/v1/targets",
            ):
                resposta = cliente.get(endereco)
                exigir(resposta.status_code == 200, "Serviço demonstrativo indisponível.")
                sondagens[endereco] = resposta.status_code
                if endereco.endswith("targets"):
                    alvos = resposta.json()["data"]["activeTargets"]
                    exigir(
                        bool(alvos) and all(a["health"] == "up" for a in alvos),
                        "Alvo Prometheus indisponível.",
                    )
                    relatorio["alvos_prometheus"] = [a["labels"] for a in alvos]
            resposta = cliente.get(
                "http://127.0.0.1:3000/api/search?type=dash-db",
                auth=("administrador", monitoramento["SENHA_GRAFANA"]),
            )
            exigir(
                resposta.status_code == 200 and len(resposta.json()) >= 3,
                "Três dashboards Grafana obrigatórios.",
            )
            relatorio["dashboards"] = [p["title"] for p in resposta.json()]
            endereco = "http://127.0.0.1:8001/api/v1/municipios?limite=2"
            primeira = cliente.get(endereco)
            exigir(primeira.status_code == 200, "Consulta IBGE demonstrativa falhou.")
            etag = primeira.headers.get("etag")
            exigir(bool(etag), "Consulta IBGE não retornou ETag.")
            segunda = cliente.get(endereco, headers={"If-None-Match": etag})
            exigir(segunda.status_code == 304, "Revalidação ETag falhou.")
            relatorio["etag"] = {"primeira": 200, "revalidacao": 304}
            relatorio["sondagens"] = sondagens
        exigir(retratar(origem) == antes, "Origem mudou durante a demonstração.")
        exigir(time.monotonic() - inicio <= 900, "Demonstração excedeu quinze minutos.")
        relatorio.update(
            situacao="SUCESSO",
            origem_preservada=True,
            core_clone_preservado=True,
            gold_recalculada_conferida=True,
        )
        return 0
    except Exception as erro:
        relatorio.update(situacao="FALHA", tipo_erro=type(erro).__name__)
        raise
    finally:
        for motor in motores:
            motor.dispose()
        relatorio["segundos_totais"] = round(time.monotonic() - inicio, 3)
        relatorio["dentro_de_15_minutos"] = relatorio["segundos_totais"] <= 900
        relatorio["finalizado_em"] = datetime.now(UTC).isoformat()
        caminho = pasta / ("demonstracao_m2_" + instante + ".json")
        with caminho.open("x", encoding="utf-8") as arquivo:
            json.dump(relatorio, arquivo, default=str, ensure_ascii=False, indent=2)
        print(
            json.dumps(
                {
                    "relatorio": str(caminho.relative_to(RAIZ)),
                    "situacao": relatorio["situacao"],
                    "segundos": relatorio["segundos_totais"],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    raise SystemExit(executar())
