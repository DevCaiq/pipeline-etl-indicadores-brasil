"""Auditoria transacional da qualidade; nunca carrega dados econômicos no core."""

import json
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import version
from pathlib import Path
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from pipeline_etl.banco.modelos import (
    ArtefatoPipeline,
    EtapaPipeline,
    ExecucaoPipeline,
    RegistroQuarentena,
)
from pipeline_etl.banco.sessoes import abrir_sessao
from pipeline_etl.processamento.armazenamento.arquivos import ArmazenamentoBronze
from pipeline_etl.processamento.clientes.bcb import ClienteBCB
from pipeline_etl.processamento.coleta import coletar_serie
from pipeline_etl.processamento.erros import ColetaAdiada, ErroColeta
from pipeline_etl.processamento.frescor import AvaliacaoFrescor, avaliar_frescor_local
from pipeline_etl.processamento.manifestos import ManifestoVerificado, ler_manifesto
from pipeline_etl.processamento.qualidade import (
    VERSAO_CONTRATO,
    ContagensValidacao,
    RejeicaoRegistro,
    ResultadoValidacao,
    validar_corpo,
)

PAI_PIPELINE: ContextVar[UUID | None] = ContextVar("pai_pipeline", default=None)


class ErroValidacao(Exception):
    """Falha técnica; o identificador permite consultar a auditoria sem expor segredos."""

    def __init__(self, execucao_id: UUID) -> None:
        super().__init__("Não foi possível persistir a validação; consulte a execução.")
        self.execucao_id = execucao_id


@dataclass(frozen=True)
class ResumoAuditoria:
    execucao_id: UUID
    situacao: str
    contagens: ContagensValidacao
    avisos: tuple[str, ...] = ()


def _atribuir_contagens(
    registro: ExecucaoPipeline | EtapaPipeline, contagens: ContagensValidacao
) -> None:
    registro.linhas_lidas = contagens.lidas
    registro.linhas_validas = contagens.validas
    registro.linhas_rejeitadas = contagens.rejeitadas
    registro.linhas_duplicadas = contagens.duplicadas
    registro.linhas_nao_processadas = contagens.nao_processadas


def _iniciar(motor: Engine, modo: str, parametros: dict[str, object]) -> UUID:
    pai = PAI_PIPELINE.get()
    if pai is not None:
        parametros = {**parametros, "pai_pipeline_id": str(pai)}
    identificador = uuid4()
    with abrir_sessao(motor) as sessao:
        sessao.add(
            ExecucaoPipeline(
                execucao_id=identificador,
                modo=modo,
                parametros=parametros,
                versao_codigo=version("pipeline-etl"),
                versao_contrato=VERSAO_CONTRATO,
            )
        )
    return identificador


def _finalizar_falha(
    motor: Engine, identificador: UUID, motivo: str, detalhes: dict[str, object] | None = None
) -> None:
    with abrir_sessao(motor) as sessao:
        registro = sessao.get(ExecucaoPipeline, identificador, with_for_update=True)
        if registro is None:
            raise ValueError("Execução não encontrada.")
        if registro.situacao != "EM_EXECUCAO":
            return
        registro.situacao = "FALHA"
        registro.finalizado_em = datetime.now(UTC)
        registro.erro = motivo
        if detalhes:
            registro.parametros = {**registro.parametros, **detalhes}


def _frescor_janela(
    verificado: ManifestoVerificado, indice: int, resultado: ResultadoValidacao, hoje: date
) -> AvaliacaoFrescor | None:
    artefato = verificado.artefatos[indice]
    if artefato.fim < hoje - timedelta(days=4):
        return None
    ultima = max((observacao.data for observacao in resultado.observacoes), default=None)
    avaliacao = avaliar_frescor_local(verificado.manifesto.codigo_serie, ultima, hoje)
    if avaliacao.referencia_esperada is not None and not (
        artefato.inicio <= avaliacao.referencia_esperada <= artefato.fim
    ):
        return None
    return avaliacao


def _avisos_qualidade(
    sessao: Session,
    verificado: ManifestoVerificado,
    indice: int,
    resultado: ResultadoValidacao,
    hoje: date,
) -> list[str]:
    artefato = verificado.artefatos[indice]
    anterior = sessao.scalar(
        select(EtapaPipeline.linhas_lidas)
        .join(ArtefatoPipeline, ArtefatoPipeline.etapa_id == EtapaPipeline.etapa_id)
        .join(ExecucaoPipeline, ExecucaoPipeline.execucao_id == EtapaPipeline.execucao_id)
        .where(
            EtapaPipeline.codigo_serie == verificado.manifesto.codigo_serie,
            ExecucaoPipeline.situacao == "SUCESSO",
            ArtefatoPipeline.janela_inicio == artefato.inicio,
            ArtefatoPipeline.janela_fim == artefato.fim,
        )
        .order_by(ExecucaoPipeline.finalizado_em.desc())
        .limit(1)
    )
    avisos = []
    if anterior and abs(resultado.contagens.lidas - anterior) * 100 > 20 * anterior:
        avisos.append("VOLUMETRIA_VARIACAO_SUPERIOR_20_PCT")
    avaliacao = _frescor_janela(verificado, indice, resultado, hoje)
    if avaliacao is not None and avaliacao.defasado:
        avisos.append("FRESCOR_POTENCIALMENTE_DEFASADO")
    return avisos


def _persistir(
    motor: Engine,
    identificador: UUID,
    verificado: ManifestoVerificado | None,
    resultados: list[ResultadoValidacao],
) -> ResumoAuditoria:
    total = ContagensValidacao(
        *(
            sum(getattr(resultado.contagens, nome) for resultado in resultados)
            for nome in ("lidas", "validas", "rejeitadas", "duplicadas", "nao_processadas")
        )
    )
    erro = next(
        (resultado.erro_estrutural for resultado in resultados if resultado.erro_estrutural), None
    )
    situacao = ResultadoValidacao(total, erro_estrutural=erro).situacao
    avisos_totais = []
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    with abrir_sessao(motor) as sessao:
        registro = sessao.get(ExecucaoPipeline, identificador, with_for_update=True)
        if registro is None or registro.situacao != "EM_EXECUCAO":
            raise ValueError("Execução inexistente ou já finalizada.")
        avaliacoes_frescor = []
        for indice, resultado in enumerate(resultados):
            etapa_id = uuid4()
            avisos = (
                _avisos_qualidade(sessao, verificado, indice, resultado, hoje) if verificado else []
            )
            avaliacao = _frescor_janela(verificado, indice, resultado, hoje) if verificado else None
            if avaliacao is not None:
                avaliacoes_frescor.append({"indice_artefato": indice, **asdict(avaliacao)})
            if resultado.erro_estrutural:
                avisos.append(resultado.erro_estrutural)
            etapa = EtapaPipeline(
                etapa_id=etapa_id,
                execucao_id=identificador,
                nome="validacao_bcb" if verificado else "manifesto",
                codigo_serie=verificado.manifesto.codigo_serie if verificado else None,
                situacao=resultado.situacao,
                finalizado_em=datetime.now(UTC),
                avisos=avisos,
            )
            _atribuir_contagens(etapa, resultado.contagens)
            sessao.add(etapa)
            sessao.flush()
            artefato_id = None
            if verificado:
                origem = verificado.artefatos[indice]
                artefato_id = uuid4()
                sessao.add(
                    ArtefatoPipeline(
                        artefato_id=artefato_id,
                        etapa_id=etapa_id,
                        identificador_bronze=origem.metadados.artefato_id,
                        execucao_coleta_id=verificado.manifesto.execucao_id,
                        caminho_metadados=str(origem.caminho_metadados),
                        sha256=origem.metadados.sha256,
                        tamanho_bytes=origem.metadados.tamanho_bytes,
                        janela_inicio=origem.inicio,
                        janela_fim=origem.fim,
                        coletado_em=origem.metadados.coletado_em,
                        codificacao_conteudo=origem.metadados.codificacao_conteudo,
                    )
                )
                sessao.flush()
            for rejeicao in resultado.rejeicoes:
                sessao.add(
                    RegistroQuarentena(
                        etapa_id=etapa_id,
                        artefato_id=artefato_id,
                        posicao=rejeicao.posicao,
                        motivo=rejeicao.motivo,
                        registro_original={
                            "json_escapado": json.dumps(
                                rejeicao.original, ensure_ascii=True, allow_nan=False
                            )
                        },
                    )
                )
            avisos_totais.extend(avisos)
        _atribuir_contagens(registro, total)
        registro.situacao = situacao
        registro.parametros = {
            **registro.parametros,
            "avaliacoes_frescor": json.loads(json.dumps(avaliacoes_frescor, default=str)),
        }
        registro.finalizado_em = datetime.now(UTC)
        registro.erro = erro
    return ResumoAuditoria(identificador, situacao, total, tuple(sorted(set(avisos_totais))))


def validar_manifesto(
    armazenamento: ArmazenamentoBronze,
    caminho: Path,
    motor: Engine,
    *,
    execucao_id: UUID | None = None,
) -> ResumoAuditoria:
    """Revalida arquivos sem rede e mantém histórico independente a cada tentativa."""
    identificador = execucao_id or _iniciar(
        motor, "validacao_bronze", {"manifesto": str(caminho.resolve())}
    )
    try:
        try:
            verificado = ler_manifesto(armazenamento, caminho)
        except (OSError, ValueError, RecursionError):
            resultado = ResultadoValidacao(
                ContagensValidacao(),
                rejeicoes=(RejeicaoRegistro(0, "MANIFESTO_INVALIDO", None),),
                erro_estrutural="MANIFESTO_INVALIDO",
            )
            return _persistir(motor, identificador, None, [resultado])
        hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        resultados = [
            validar_corpo(
                artefato.corpo,
                verificado.manifesto.codigo_serie,
                artefato.inicio,
                artefato.fim,
                hoje,
                artefato.metadados.codificacao_conteudo,
            )
            for artefato in verificado.artefatos
        ]
        return _persistir(motor, identificador, verificado, resultados)
    except Exception as erro:
        try:
            _finalizar_falha(motor, identificador, "PERSISTENCIA_VALIDACAO_FALHOU")
        except Exception:
            structlog.get_logger(servico="validacao").error(
                "Registro de falha indisponível", execucao_id=str(identificador)
            )
        raise ErroValidacao(identificador) from erro


def coletar_e_validar(
    cliente: ClienteBCB,
    armazenamento: ArmazenamentoBronze,
    motor: Engine,
    codigo: int,
    inicio: date,
    fim: date,
) -> ResumoAuditoria:
    """Registra início antes da rede e mantém falhas de coleta consultáveis."""
    identificador = _iniciar(
        motor,
        "coleta_validacao",
        {"codigo_serie": codigo, "inicio": inicio.isoformat(), "fim": fim.isoformat()},
    )
    try:
        caminho = coletar_serie(
            cliente, armazenamento, codigo, inicio, fim, execucao_id=identificador
        )
    except (ErroColeta, OSError, ValueError) as erro:
        detalhes: dict[str, object] = {}
        if isinstance(erro, ErroColeta) and erro.manifesto is not None:
            detalhes["manifesto"] = str(erro.manifesto)
        if isinstance(erro, ColetaAdiada):
            detalhes["proxima_tentativa_em"] = erro.proxima_tentativa_em.isoformat()
        _finalizar_falha(motor, identificador, "COLETA_FALHOU", detalhes)
        return ResumoAuditoria(identificador, "FALHA", ContagensValidacao())
    return validar_manifesto(armazenamento, caminho, motor, execucao_id=identificador)
