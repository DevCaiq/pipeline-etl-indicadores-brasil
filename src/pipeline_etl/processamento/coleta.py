"""Fluxo de coleta bruta: persistência independente do banco e da validação."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from structlog.contextvars import bound_contextvars

from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.erros import ErroColeta
from pipeline_etl.processamento.tipos import ArtefatoBronze


def dividir_janelas(inicio: date, fim: date) -> Iterator[tuple[date, date]]:
    """Produz intervalos inclusivos por ano civil, sem sobrepor limites."""
    if inicio > fim:
        raise ValueError("A data inicial deve ser anterior ou igual à final.")
    atual = inicio
    while atual <= fim:
        final = min(fim, date(atual.year, 12, 31))
        yield atual, final
        if final == fim:
            break
        atual = final + timedelta(days=1)


def coletar_serie(
    cliente: ClienteBCB,
    armazenamento: ArmazenamentoBronze,
    codigo: int,
    inicio: date,
    fim: date,
    *,
    execucao_id: UUID | None = None,
) -> Path:
    """Coleta janelas anuais e registra manifesto parcial quando houver falha."""
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    if codigo not in {432, 433, 1} or inicio < date(2020, 1, 1) or inicio > fim or fim > hoje:
        raise ValueError(
            "Use série homologada e período entre 2020-01-01 e hoje, em ordem crescente."
        )
    inicio_coleta = date(2019, 2, 1) if codigo == 433 and inicio == date(2020, 1, 1) else inicio
    identificador = execucao_id or uuid4()
    instante = datetime.now(UTC)
    artefatos: list[ArtefatoBronze] = []
    with bound_contextvars(execucao_id=str(identificador)):
        try:
            for inicio_janela, fim_janela in dividir_janelas(inicio_coleta, fim):
                resposta = cliente.buscar(codigo, inicio_janela, fim_janela)
                artefatos.append(armazenamento.salvar(resposta, identificador, instante))
            return armazenamento.salvar_manifesto(
                codigo,
                identificador,
                instante,
                inicio,
                fim,
                artefatos,
                inicio_coleta=inicio_coleta,
            )
        except (ErroColeta, OSError, ValueError) as erro:
            try:
                manifesto = armazenamento.salvar_manifesto(
                    codigo,
                    identificador,
                    instante,
                    inicio,
                    fim,
                    artefatos,
                    situacao="INCOMPLETA",
                    motivo=type(erro).__name__,
                    inicio_coleta=inicio_coleta,
                )
            except (OSError, ValueError) as erro_persistencia:
                raise ErroColeta(
                    "Não foi possível publicar o manifesto bronze."
                ) from erro_persistencia
            if isinstance(erro, ErroColeta):
                erro.manifesto = manifesto
                raise
            raise ErroColeta("Falha na persistência dos artefatos bronze.", manifesto) from erro
