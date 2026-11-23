"""Interface inicial de linha de comando do projeto."""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from importlib.metadata import version
from io import TextIOWrapper
from pathlib import Path

import httpx
import structlog
from pydantic import ValidationError

from pipeline_etl.comandos_api import executar_servidor
from pipeline_etl.comandos_atualizacao import executar_atualizacao
from pipeline_etl.comandos_carga import executar_carga
from pipeline_etl.comandos_publicacao import executar_publicacao
from pipeline_etl.comandos_qualidade import executar_coleta_validada, executar_validacao
from pipeline_etl.configuracao import ConfiguracaoAplicacao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie
from pipeline_etl.processamento.erros import ColetaAdiada, ErroColeta
from pipeline_etl.registros import configurar_registros


def executar(argumentos: Sequence[str] | None = None) -> int:
    """Valida configuração e retorna código de saída sem expor entradas inválidas."""
    # Padroniza o terminal e os redirecionamentos sem exigir ajuste global do Windows.
    for saida in (sys.stdout, sys.stderr):
        if isinstance(saida, TextIOWrapper):
            saida.reconfigure(encoding="utf-8")
    interpretador = argparse.ArgumentParser(
        prog="pipeline-etl",
        description="Pipeline ETL de dados públicos brasileiros.",
        add_help=False,
    )
    interpretador.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    interpretador.add_argument(
        "--versao", action="version", version=version("pipeline-etl"), help="Exibe a versão."
    )
    comandos = interpretador.add_subparsers(dest="comando", title="comandos")
    verificacao = comandos.add_parser(
        "verificar-configuracao", help="Valida e resume a configuração.", add_help=False
    )
    verificacao.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    coleta = comandos.add_parser(
        "coletar", help="Preserva respostas brutas no bronze.", add_help=False
    )
    coleta.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    fontes = coleta.add_subparsers(dest="fonte", required=True, title="fontes")
    bcb = fontes.add_parser("bcb", help="Coleta séries SGS.", add_help=False)
    bcb.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    bcb.add_argument("--serie", action="append", type=int, choices=[432, 433, 1])
    bcb.add_argument("--inicio", type=interpretar_data)
    bcb.add_argument("--fim", type=interpretar_data)
    bcb.add_argument(
        "--modo",
        choices=["carga-historica", "incremental", "reconciliacao"],
        default="carga-historica",
    )
    bcb.add_argument("--validar", action="store_true", help="Valida e registra auditoria SQL.")
    bcb.add_argument("--carregar", action="store_true", help="Valida e carrega a coleta histórica.")
    bcb.add_argument("--planejar", action="store_true", help="Mostra janelas sem HTTP/escrita SQL.")
    bcb.add_argument("--credenciais-locais", type=Path)
    validacao = comandos.add_parser(
        "validar", help="Valida bronze sem consultar a fonte.", add_help=False
    )
    validacao.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    fontes_validacao = validacao.add_subparsers(dest="fonte", required=True)
    validar_bcb = fontes_validacao.add_parser("bcb", add_help=False)
    validar_bcb.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    validar_bcb.add_argument("--manifesto", type=Path, required=True)
    validar_bcb.add_argument("--credenciais-locais", type=Path)
    carga = comandos.add_parser(
        "carregar", help="Promove bronze BCB validado ao core.", add_help=False
    )
    carga.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    fontes_carga = carga.add_subparsers(dest="fonte", required=True)
    carregar_bcb = fontes_carga.add_parser("bcb", add_help=False)
    carregar_bcb.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    carregar_bcb.add_argument("--manifesto", type=Path, required=True)
    carregar_bcb.add_argument("--credenciais-locais", type=Path)
    publicacao = comandos.add_parser(
        "publicar", help="Publica indicadores do domínio.", add_help=False
    )
    publicacao.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    publicacao.add_argument("--dominio", choices=["bcb"], required=True)
    publicacao.add_argument("--credenciais-locais", type=Path)
    servidor = comandos.add_parser(
        "servir", help="Inicia a API somente em127.0.0.1.", add_help=False
    )
    servidor.add_argument("-h", "--ajuda", action="help", help="Exibe esta ajuda.")
    servidor.add_argument("--configuracao-api", type=Path, default=Path(".env.api"))
    servidor.add_argument("--porta", type=int, default=8000)
    opcoes = interpretador.parse_args(argumentos)
    if opcoes.comando == "servir":
        return executar_servidor(opcoes)
    if opcoes.comando == "coletar":
        if opcoes.modo == "carga-historica":
            if opcoes.inicio is None or opcoes.fim is None:
                interpretador.error("Carga histórica exige --inicio e --fim.")
            if opcoes.validar and opcoes.carregar:
                interpretador.error("Escolha --validar ou --carregar.")
            if opcoes.planejar and not opcoes.carregar:
                interpretador.error("Prévia histórica exige --carregar.")
        elif opcoes.inicio is not None or opcoes.fim is not None or opcoes.validar:
            interpretador.error("Atualização automática define datas e já valida/carrega os dados.")
    if opcoes.comando is None:
        interpretador.print_help()
        return 0
    try:
        configuracao = ConfiguracaoAplicacao()
    except ValidationError:
        print(
            "Configuração inválida. Confira as variáveis de ambiente e o arquivo .env.",
            file=sys.stderr,
        )
        return 2
    configurar_registros(configuracao.nivel_registros)
    if opcoes.comando == "publicar":
        return executar_publicacao(configuracao, opcoes)
    if opcoes.comando == "carregar":
        return executar_carga(configuracao, opcoes)
    if opcoes.comando == "validar":
        return executar_validacao(configuracao, opcoes)
    if opcoes.comando == "coletar":
        if opcoes.carregar or opcoes.modo != "carga-historica":
            return executar_atualizacao(configuracao, opcoes)
        if opcoes.validar:
            return executar_coleta_validada(configuracao, opcoes)
        if opcoes.credenciais_locais is not None:
            interpretador.error("--credenciais-locais exige --validar na coleta.")
        return executar_coleta(configuracao, opcoes)
    structlog.get_logger(servico="comandos").info("Configuração verificada")
    resumo = {
        "ambiente": configuracao.ambiente,
        "nivel_registros": configuracao.nivel_registros,
        "caminho_bronze": str(configuracao.caminho_bronze),
        "series_bcb": configuracao.series_bcb,
    }
    print(json.dumps(resumo, ensure_ascii=True))
    return 0


def interpretar_data(valor: str) -> date:
    """Aceita datas ISO e apresenta diagnóstico compreensível na CLI."""
    try:
        return date.fromisoformat(valor)
    except ValueError as erro:
        raise argparse.ArgumentTypeError("Informe data no formato AAAA-MM-DD.") from erro


def executar_coleta(configuracao: ConfiguracaoAplicacao, opcoes: argparse.Namespace) -> int:
    """Coleta séries independentemente e informa qualquer execução incompleta."""
    resultados: list[dict[str, object]] = []
    series = tuple(dict.fromkeys(opcoes.serie or configuracao.series_bcb))
    armazenamento = ArmazenamentoBronze(configuracao.caminho_bronze)
    with httpx.Client() as transporte:
        cliente = ClienteBCB(transporte)
        for codigo in series:
            try:
                manifesto = coletar_serie(cliente, armazenamento, codigo, opcoes.inicio, opcoes.fim)
                resultados.append(
                    {"codigo_serie": codigo, "situacao": "COLETADA", "manifesto": str(manifesto)}
                )
            except ValueError:
                print(
                    "Período de coleta inválido. Use datas entre 2020-01-01 e hoje.",
                    file=sys.stderr,
                )
                return 2
            except ErroColeta as erro:
                item: dict[str, object] = {
                    "codigo_serie": codigo,
                    "situacao": "INCOMPLETA",
                    "manifesto": str(erro.manifesto) if erro.manifesto else None,
                    "motivo": str(erro),
                }
                if isinstance(erro, ColetaAdiada):
                    item["proxima_tentativa_em"] = erro.proxima_tentativa_em.isoformat()
                resultados.append(item)
                structlog.get_logger(servico="coleta").warning(
                    "Coleta incompleta",
                    codigo_serie=codigo,
                    tipo_falha=type(erro).__name__,
                )
    concluida = all(item["situacao"] == "COLETADA" for item in resultados)
    print(
        json.dumps({"situacao": "COLETADA" if concluida else "INCOMPLETA", "coletas": resultados})
    )
    return 0 if concluida else 1
