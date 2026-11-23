"""Atualização auditada por janelas, interrompendo a série na primeira falha."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import Engine, select

from pipeline_etl.banco.modelos import ExecucaoPipeline, MarcoCoberturaBCB
from pipeline_etl.banco.sessoes import abrir_sessao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.auditoria import _finalizar_falha, _iniciar
from pipeline_etl.processamento.carga import ResumoCarga, carregar_manifesto
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie
from pipeline_etl.processamento.erros import ColetaAdiada, ErroColeta
from pipeline_etl.processamento.incremental import PlanoAtualizacao, planejar_atualizacao


class ErroAtualizacao(Exception):
    """Falha técnica segura; a auditoria pode precisar de reconciliação."""

    def __init__(self, execucao_id: UUID):
        super().__init__("Atualização interrompida; confira a auditoria.")
        self.execucao_id = execucao_id


@dataclass(frozen=True)
class ResultadoJanela:
    inicio: date
    fim: date
    coleta_id: UUID
    manifesto: Path | None
    carga: ResumoCarga | None
    motivo: str | None = None


@dataclass(frozen=True)
class ResumoAtualizacao:
    codigo_serie: int
    situacao: str
    plano: PlanoAtualizacao | None = None
    execucao_id: UUID | None = None
    resultados: tuple[ResultadoJanela, ...] = ()
    motivo: str | None = None


def _serializar(resultados: list[ResultadoJanela]) -> list[dict[str, object]]:
    return [
        {
            "inicio": str(item.inicio),
            "fim": str(item.fim),
            "coleta_id": str(item.coleta_id),
            "manifesto": str(item.manifesto) if item.manifesto else None,
            "carga_id": str(item.carga.execucao_id) if item.carga else None,
            "situacao": item.carga.situacao if item.carga else "FALHA",
            "motivo": item.motivo,
            "avisos": list(item.carga.avisos) if item.carga else [],
        }
        for item in resultados
    ]


def _coletar_janela(
    cliente: ClienteBCB,
    armazenamento: ArmazenamentoBronze,
    motor: Engine,
    pai: UUID,
    codigo: int,
    inicio: date,
    fim: date,
) -> ResultadoJanela:
    coleta = _iniciar(
        motor,
        "coleta_atualizacao",
        {"pai_id": str(pai), "codigo_serie": codigo, "inicio": str(inicio), "fim": str(fim)},
    )
    manifesto: Path | None
    try:
        manifesto = coletar_serie(cliente, armazenamento, codigo, inicio, fim, execucao_id=coleta)
    except (ErroColeta, OSError, ValueError) as erro:
        manifesto = erro.manifesto if isinstance(erro, ErroColeta) else None
        detalhes: dict[str, object] = {"manifesto": str(manifesto) if manifesto else None}
        if isinstance(erro, ColetaAdiada):
            detalhes["proxima_tentativa_em"] = erro.proxima_tentativa_em.isoformat()
        _finalizar_falha(motor, coleta, "COLETA_FALHOU", detalhes)
        return ResultadoJanela(inicio, fim, coleta, manifesto, None, "COLETA_FALHOU")
    with abrir_sessao(motor) as sessao:
        registro = sessao.get(ExecucaoPipeline, coleta)
        if registro is None:
            raise ValueError("Execução de coleta não encontrada.")
        registro.situacao = "SUCESSO"
        registro.finalizado_em = datetime.now(UTC)
        registro.parametros = {**registro.parametros, "manifesto": str(manifesto)}
    carga = carregar_manifesto(armazenamento, manifesto, motor)
    return ResultadoJanela(inicio, fim, coleta, manifesto, carga, carga.motivo)


def atualizar_serie(
    cliente: ClienteBCB,
    armazenamento: ArmazenamentoBronze,
    motor: Engine,
    codigo: int,
    modo: str,
    *,
    inicio: date | None = None,
    fim: date | None = None,
    somente_planejar: bool = False,
    hoje: date | None = None,
) -> ResumoAtualizacao:
    """SQL antes de HTTP; a janela seguinte exige confirmação da anterior."""
    hoje = hoje or datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    ultima = cobertura = None
    if modo == "incremental":
        with motor.connect() as conexao:
            marco = (
                conexao.execute(
                    select(MarcoCoberturaBCB).where(MarcoCoberturaBCB.codigo_sgs == codigo)
                )
                .mappings()
                .first()
            )
        if marco is not None:
            ultima, cobertura = marco.ultima_observacao, marco.fim_coberto
    try:
        plano = planejar_atualizacao(
            codigo,
            modo,
            hoje,
            ultima_observacao=ultima,
            fim_coberto=cobertura,
            inicio=inicio,
            fim=fim,
        )
    except ValueError as erro:
        return ResumoAtualizacao(codigo, "IGNORADA", motivo=str(erro))
    if somente_planejar:
        return ResumoAtualizacao(codigo, "PLANEJADA", plano=plano)
    identificador = _iniciar(
        motor,
        "atualizacao_bcb",
        {
            "codigo_serie": codigo,
            "modo": modo,
            "inicio": str(plano.inicio),
            "fim": str(plano.fim),
            "janelas": [[str(inicial), str(final)] for inicial, final in plano.janelas],
        },
    )
    resultados: list[ResultadoJanela] = []
    try:
        for inicial, final in plano.janelas:
            resultado = _coletar_janela(
                cliente, armazenamento, motor, identificador, codigo, inicial, final
            )
            resultados.append(resultado)
            if resultado.carga is None or resultado.carga.situacao != "SUCESSO":
                break
        confirmadas = sum(
            item.carga is not None and item.carga.situacao == "SUCESSO" for item in resultados
        )
        situacao = (
            "SUCESSO"
            if confirmadas == len(plano.janelas)
            else "PARCIAL"
            if confirmadas
            else "FALHA"
        )
        with abrir_sessao(motor) as sessao:
            registro = sessao.get(ExecucaoPipeline, identificador)
            if registro is None:
                raise ValueError("Execução de atualização não encontrada.")
            registro.situacao = situacao
            registro.finalizado_em = datetime.now(UTC)
            registro.erro = None if situacao == "SUCESSO" else "JANELA_NAO_CONFIRMADA"
            registro.parametros = {
                **registro.parametros,
                "resultados": _serializar(resultados),
                "janelas_confirmadas": confirmadas,
                "janelas_nao_executadas": len(plano.janelas) - len(resultados),
            }
        return ResumoAtualizacao(codigo, situacao, plano, identificador, tuple(resultados))
    except Exception as erro:
        try:
            _finalizar_falha(
                motor,
                identificador,
                "ATUALIZACAO_INTERROMPIDA",
                {"resultados": _serializar(resultados)},
            )
        except Exception:
            structlog.get_logger(servico="atualizacao").error(
                "Registro de falha indisponível", execucao_id=str(identificador)
            )
        raise ErroAtualizacao(identificador) from erro
