"""Promoção IBGE offline, atômica, com snapshots territoriais imutáveis."""

import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert

from pipeline_etl.banco.modelos import (
    EstadoPublicacao,
    EtapaPipeline,
    LoteProcessamento,
    RegistroQuarentena,
)
from pipeline_etl.banco.modelos_ibge import (
    DimensaoMunicipio,
    DimensaoRegiao,
    DimensaoUF,
    FatoPopulacao,
    MunicipioSnapshot,
    SnapshotLocalidades,
)
from pipeline_etl.processamento.armazenamento.objetos import ArmazenamentoObjetos, ObjetoBronze
from pipeline_etl.processamento.auditoria import _finalizar_falha, _iniciar
from pipeline_etl.processamento.clientes.ibge import ler_coleta
from pipeline_etl.processamento.contratos.ibge import (
    PopulacaoValidada,
    descobrir_periodos,
    normalizar_localidades,
    normalizar_populacao,
    validar_metadados,
)
from pipeline_etl.processamento.publicacao import ResumoPublicacao, _registrar

CHAVE_TRAVA_IBGE = 2026112001


@dataclass(frozen=True)
class ResumoCargaIBGE:
    execucao_id: UUID
    situacao: str
    snapshot_id: UUID | None = None
    anos: tuple[int, ...] = ()
    inseridas: int = 0
    alteradas: int = 0
    inalteradas: int = 0
    motivo: str | None = None


def _json(valor: object) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _travar(conexao: Connection) -> None:
    conexao.execute(text("SET LOCAL statement_timeout='30s'"))
    conexao.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": CHAVE_TRAVA_IBGE})


def _atualizar_dimensao(
    conexao: Connection, modelo: Any, valores: list[dict[str, Any]], chaves: list[str]
) -> bool:
    mudou = False
    for valor in valores:
        comando = insert(modelo).values(valor)
        campos = {chave: getattr(comando.excluded, chave) for chave in valor if chave not in chaves}
        comando = comando.on_conflict_do_update(
            index_elements=chaves,
            set_=campos,
            where=or_(
                *(
                    getattr(modelo, chave).is_distinct_from(expressao)
                    for chave, expressao in campos.items()
                )
            ),
        )
        mudou = (
            conexao.execute(comando.returning(getattr(modelo, chaves[0]))).first() is not None
            or mudou
        )
    return mudou


def carregar_ibge(
    armazenamento: ArmazenamentoObjetos, manifestos: tuple[ObjetoBronze, ...], motor: Engine
) -> ResumoCargaIBGE:
    """Valida todo o pacote bronze antes de promover qualquer dimensão ou fato."""
    descritores = sorted(
        (asdict(objeto) for objeto in manifestos), key=lambda objeto: objeto["chave"]
    )
    identificador = _iniciar(motor, "carga_ibge", {"manifestos": descritores})
    try:
        coletas = {}
        for manifesto in manifestos:
            coleta = ler_coleta(armazenamento, manifesto)
            chave = (coleta.recurso, coleta.ano)
            if chave in coletas:
                raise ValueError("RECURSO_DUPLICADO")
            coletas[chave] = coleta
        obrigatorios = {
            (recurso, None) for recurso in ("regioes", "ufs", "municipios", "metadados", "periodos")
        }
        if not obrigatorios.issubset(coletas):
            raise ValueError("PACOTE_INCOMPLETO")
        validar_metadados(coletas["metadados", None].corpo)
        disponiveis = descobrir_periodos(coletas["periodos", None].corpo)
        anos = tuple(
            sorted(ano for recurso, ano in coletas if recurso == "populacao" and ano is not None)
        )
        if (
            not anos
            or not set(anos).issubset(disponiveis)
            or len(coletas) != len(obrigatorios) + len(anos)
        ):
            raise ValueError("ANOS_INDISPONIVEIS")
        localidades = normalizar_localidades(
            *(coletas[recurso, None].corpo for recurso in ("regioes", "ufs", "municipios"))
        )
        municipios = {municipio.codigo_ibge: municipio for municipio in localidades.municipios}
        ufs = {uf.codigo: uf for uf in localidades.ufs}
        linhas: list[tuple[PopulacaoValidada, datetime]] = []
        for ano in anos:
            coleta = coletas["populacao", ano]
            linhas.extend(
                (linha, coleta.coletado_em)
                for linha in normalizar_populacao(coleta.corpo, {ano}, set(municipios))
            )
        soma = sha256(_json(asdict(localidades)).encode()).hexdigest()
        snapshot = UUID(soma[:32])
        origens_territoriais = {
            recurso: {
                "coletado_em": coletas[recurso, None].coletado_em.isoformat(),
                "checksum_normalizado": sha256(
                    _json([asdict(item) for item in getattr(localidades, recurso)]).encode()
                ).hexdigest(),
            }
            for recurso in ("regioes", "ufs", "municipios")
        }
        origem_territorial = max(
            coletas[recurso, None].coletado_em for recurso in ("regioes", "ufs", "municipios")
        )
        with motor.begin() as conexao:
            _travar(conexao)
            ultimo = (
                conexao.execute(
                    select(SnapshotLocalidades)
                    .order_by(SnapshotLocalidades.coletado_em.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if (
                ultimo
                and ultimo.snapshot_id != snapshot
                and origem_territorial <= ultimo.coletado_em
            ):
                raise ValueError("SNAPSHOT_ANTIGO_DIVERGENTE")
            atuais = {
                (linha.codigo_ibge, linha.ano): linha
                for linha in conexao.execute(
                    select(FatoPopulacao).where(
                        FatoPopulacao.ano.in_(anos), FatoPopulacao.indicador_id == 1
                    )
                ).mappings()
            }
            evidencias = (
                conexao.execute(
                    text(
                        "SELECT e.parametros FROM ops.execucao e JOIN ops.lote l "
                        "ON l.execucao_id=e.execucao_id WHERE e.modo='carga_ibge' "
                        "AND e.situacao='SUCESSO' AND l.fonte='ibge'"
                    )
                )
                .scalars()
                .all()
            )
            evidencias_territoriais = [
                parametros for parametros in evidencias if "origem_territorial" in parametros
            ]
            if evidencias_territoriais:
                mais_recente = max(
                    evidencias_territoriais, key=lambda parametros: parametros["origem_territorial"]
                )
                if str(snapshot) != mais_recente[
                    "snapshot_id"
                ] and origem_territorial <= datetime.fromisoformat(
                    mais_recente["origem_territorial"]
                ):
                    raise ValueError("SNAPSHOT_ANTIGO_DIVERGENTE")
            for recurso, proveniencia in origens_territoriais.items():
                anteriores = [
                    parametros["origens_territoriais"][recurso]
                    for parametros in evidencias
                    if recurso in parametros.get("origens_territoriais", {})
                ]
                if anteriores:
                    anterior = max(
                        anteriores,
                        key=lambda item: datetime.fromisoformat(item["coletado_em"]),
                    )
                    if proveniencia["checksum_normalizado"] != anterior[
                        "checksum_normalizado"
                    ] and datetime.fromisoformat(
                        proveniencia["coletado_em"]
                    ) <= datetime.fromisoformat(anterior["coletado_em"]):
                        raise ValueError("SNAPSHOT_ANTIGO_DIVERGENTE")
            origens_confirmadas: dict[int, datetime] = {}
            for parametros in evidencias:
                for ano_texto, instante in parametros.get("origens_anos", {}).items():
                    ano_confirmado = int(ano_texto)
                    origem_confirmada = datetime.fromisoformat(instante)
                    if (
                        ano_confirmado not in origens_confirmadas
                        or origem_confirmada > origens_confirmadas[ano_confirmado]
                    ):
                        origens_confirmadas[ano_confirmado] = origem_confirmada
            inseridas = alteradas = inalteradas = 0
            valores = []
            campos = (
                "populacao",
                "marcador",
                "motivo",
                "uf_referencia",
                "regiao_referencia",
                "snapshot_id",
                "base_territorial",
            )
            lote = uuid4()
            for linha, origem in linhas:
                municipio = municipios[linha.codigo_ibge]
                valor = {
                    **asdict(linha),
                    "indicador_id": 1,
                    "uf_referencia": municipio.uf_codigo,
                    "regiao_referencia": ufs[municipio.uf_codigo].regiao_codigo,
                    "snapshot_id": snapshot,
                    "base_territorial": "atual_na_coleta",
                    "lote_id": lote,
                    "origem_coletada_em": origem,
                }
                anterior = atuais.get((linha.codigo_ibge, linha.ano))
                if anterior is None:
                    inseridas += 1
                elif all(anterior[chave] == valor[chave] for chave in campos):
                    inalteradas += 1
                else:
                    if origem <= max(
                        anterior.origem_coletada_em,
                        origens_confirmadas.get(linha.ano, anterior.origem_coletada_em),
                    ):
                        raise ValueError("BRONZE_ANTIGO_DIVERGENTE")
                    alteradas += 1
                valores.append(valor)
            # O pacote substitui apenas seus anos; fatos fora dele mantêm a história.
            extras = set(atuais) - {(linha.codigo_ibge, linha.ano) for linha, _ in linhas}
            if extras:
                raise ValueError("COBERTURA_ANTERIOR_DIVERGENTE")
            conexao.execute(
                insert(LoteProcessamento).values(
                    lote_id=lote,
                    execucao_id=identificador,
                    fonte="ibge",
                    chave="6579/9324",
                    janela_inicio=date(min(anos), 1, 1),
                    janela_fim=date(max(anos), 12, 31),
                    manifesto=_json(descritores),
                    checksum=sha256(_json(descritores).encode()).hexdigest(),
                    confirmado_em=datetime.now(UTC),
                )
            )
            mudou = _atualizar_dimensao(
                conexao,
                DimensaoRegiao,
                [asdict(regiao) for regiao in localidades.regioes],
                ["codigo"],
            )
            mudou = (
                _atualizar_dimensao(
                    conexao, DimensaoUF, [asdict(uf) for uf in localidades.ufs], ["codigo"]
                )
                or mudou
            )
            existe = conexao.scalar(
                select(SnapshotLocalidades.snapshot_id).where(
                    SnapshotLocalidades.snapshot_id == snapshot
                )
            )
            if not existe:
                conexao.execute(
                    insert(SnapshotLocalidades).values(
                        snapshot_id=snapshot,
                        checksum_normalizado=soma,
                        lote_id=lote,
                        coletado_em=origem_territorial,
                    )
                )
                conexao.execute(
                    insert(MunicipioSnapshot),
                    [
                        dict(
                            snapshot_id=snapshot,
                            codigo_ibge=municipio.codigo_ibge,
                            nome=municipio.nome,
                            uf_codigo=municipio.uf_codigo,
                            regiao_codigo=ufs[municipio.uf_codigo].regiao_codigo,
                        )
                        for municipio in localidades.municipios
                    ],
                )
            mudou = (
                _atualizar_dimensao(
                    conexao,
                    DimensaoMunicipio,
                    [
                        dict(**asdict(municipio), ativo=True, snapshot_id=snapshot)
                        for municipio in localidades.municipios
                    ],
                    ["codigo_ibge"],
                )
                or mudou
            )
            resultado = conexao.execute(
                text(
                    "UPDATE core.dim_municipio SET ativo=false WHERE ativo AND NOT (codigo_ibge "
                    "= ANY(:codigos)) RETURNING codigo_ibge"
                ),
                {"codigos": list(municipios)},
            )
            mudou = resultado.first() is not None or mudou
            for inicio in range(0, len(valores), 1000):
                comando = insert(FatoPopulacao).values(valores[inicio : inicio + 1000])
                conexao.execute(
                    comando.on_conflict_do_update(
                        index_elements=["codigo_ibge", "ano", "indicador_id"],
                        set_={
                            **{
                                chave: getattr(comando.excluded, chave)
                                for chave in (*campos, "lote_id", "origem_coletada_em")
                            },
                            "alterado_em": func.now(),
                        },
                        where=or_(
                            *(
                                getattr(FatoPopulacao, chave).is_distinct_from(
                                    getattr(comando.excluded, chave)
                                )
                                for chave in campos
                            )
                        ),
                    )
                )
            if mudou or inseridas or alteradas:
                comando = insert(EstadoPublicacao).values(
                    dominio="ibge", versao_core=1, situacao="PENDENTE"
                )
                conexao.execute(
                    comando.on_conflict_do_update(
                        index_elements=["dominio"],
                        set_={
                            "versao_core": EstadoPublicacao.versao_core + 1,
                            "situacao": "PENDENTE",
                        },
                    )
                )
            resumo = ResumoCargaIBGE(
                identificador, "SUCESSO", snapshot, anos, inseridas, alteradas, inalteradas
            )
            conexao.execute(
                insert(EtapaPipeline).values(
                    execucao_id=identificador,
                    nome="validacao_ibge",
                    fonte="ibge",
                    situacao="SUCESSO",
                    finalizado_em=datetime.now(UTC),
                    linhas_lidas=len(linhas),
                    linhas_validas=len(linhas),
                )
            )
            conexao.execute(
                text(
                    "UPDATE ops.execucao SET "
                    "situacao='SUCESSO',finalizado_em=now(),linhas_lidas=:total,linhas_validas=:"
                    "total,parametros=parametros || CAST(:resumo AS jsonb) WHERE execucao_id=:id"
                ),
                {
                    "total": len(linhas),
                    "resumo": _json(
                        {
                            **asdict(resumo),
                            "origem_territorial": origem_territorial.isoformat(),
                            "origens_territoriais": origens_territoriais,
                            "origens_anos": {
                                str(ano): coletas["populacao", ano].coletado_em.isoformat()
                                for ano in anos
                            },
                        }
                    ),
                    "id": identificador,
                },
            )
            return resumo
    except Exception as erro:
        motivo = (
            str(erro)
            if isinstance(erro, ValueError)
            and str(erro)
            in {
                "BRONZE_ANTIGO_DIVERGENTE",
                "SNAPSHOT_ANTIGO_DIVERGENTE",
                "COBERTURA_ANTERIOR_DIVERGENTE",
            }
            else "CONTRATO_IBGE_INVALIDO"
        )
        _finalizar_falha(motor, identificador, motivo)
        with motor.begin() as conexao:
            etapa = uuid4()
            conexao.execute(
                insert(EtapaPipeline).values(
                    etapa_id=etapa,
                    execucao_id=identificador,
                    nome="validacao_ibge",
                    fonte="ibge",
                    situacao="FALHA",
                    finalizado_em=datetime.now(UTC),
                )
            )
            conexao.execute(
                insert(RegistroQuarentena).values(
                    etapa_id=etapa,
                    posicao=0,
                    motivo=motivo,
                    registro_original={"referencias_bronze": _json(descritores)},
                )
            )
        return ResumoCargaIBGE(identificador, "FALHA", motivo=motivo)


def publicar_ibge(motor: Engine) -> ResumoPublicacao:
    """Valida denominadores e publica as três agregações numa única transação."""
    identificador = _iniciar(motor, "publicacao_ibge", {"dominio": "ibge"})
    try:
        with motor.begin() as conexao:
            _travar(conexao)
            estado = conexao.execute(
                text("SELECT * FROM ops.publicacao WHERE dominio='ibge' FOR UPDATE")
            ).first()
            if estado is None or estado.versao_core == 0:
                resumo = ResumoPublicacao(identificador, "IGNORADA", motivo="SEM_GERACAO_CORE")
            elif estado.versao_core == estado.versao_gold and estado.situacao == "PRONTA":
                resumo = ResumoPublicacao(
                    identificador,
                    "IGNORADA",
                    estado.versao_core,
                    estado.versao_gold,
                    "JA_PUBLICADA",
                    estado.data_publicacao,
                )
            else:
                misturado = conexao.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM core.fato_populacao GROUP BY ano,indicador_id "
                        "HAVING count(DISTINCT snapshot_id)>1 "
                        "OR count(DISTINCT base_territorial)>1)"
                    )
                )
                incompleto = conexao.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM (SELECT ano,indicador_id,snapshot_id,count(*) "
                        "AS recebidos FROM core.fato_populacao GROUP BY "
                        "ano,indicador_id,snapshot_id) f WHERE recebidos<>(SELECT count(*) FROM "
                        "core.municipio_snapshot m WHERE m.snapshot_id=f.snapshot_id))"
                    )
                )
                if misturado or incompleto:
                    raise ValueError("COBERTURA_INVALIDA")
                for nome in ("uf", "regiao", "brasil"):
                    conexao.execute(text(f"REFRESH MATERIALIZED VIEW mart.mv_populacao_{nome}"))
                hoje = conexao.scalar(
                    text("SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date")
                )
                conexao.execute(
                    text(
                        "UPDATE ops.publicacao SET "
                        "versao_gold=versao_core,situacao='PRONTA',data_publicacao=:hoje WHERE "
                        "dominio='ibge'"
                    ),
                    {"hoje": hoje},
                )
                resumo = ResumoPublicacao(
                    identificador,
                    "SUCESSO",
                    estado.versao_core,
                    estado.versao_core,
                    data_publicacao=hoje,
                )
            _registrar(conexao, resumo)
            return resumo
    except Exception:
        resumo = ResumoPublicacao(identificador, "FALHA", motivo="PUBLICACAO_FALHOU")
        with motor.begin() as conexao:
            _travar(conexao)
            conexao.execute(
                text(
                    "UPDATE ops.publicacao SET situacao='PENDENTE' WHERE dominio='ibge' AND "
                    "versao_gold<versao_core"
                )
            )
            _registrar(conexao, resumo)
        return resumo
