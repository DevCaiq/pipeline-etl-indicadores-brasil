"""Modelos da base BCB; futuras mudanças exigem novas migrações."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BaseModelo(DeclarativeBase):
    """Metadados compartilhados, com nomes determinísticos para constraints."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class ContagensOperacionais:
    """Contagens da qualidade compartilhadas por execução e etapa."""

    linhas_lidas: Mapped[int] = mapped_column(server_default="0")
    linhas_validas: Mapped[int] = mapped_column(server_default="0")
    linhas_rejeitadas: Mapped[int] = mapped_column(server_default="0")
    linhas_duplicadas: Mapped[int] = mapped_column(server_default="0")
    linhas_nao_processadas: Mapped[int] = mapped_column(server_default="0")


class ExecucaoPipeline(ContagensOperacionais, BaseModelo):
    """Identifica uma execução completa e seu diagnóstico operacional."""

    __tablename__ = "execucao"
    __table_args__ = (
        CheckConstraint(
            "situacao IN ('EM_EXECUCAO','SUCESSO','PARCIAL','FALHA','IGNORADA')",
            name="situacao_valida",
        ),
        CheckConstraint(
            "linhas_lidas = linhas_validas + linhas_rejeitadas + linhas_duplicadas + "
            "linhas_nao_processadas AND linhas_validas>=0 AND linhas_rejeitadas>=0 AND "
            "linhas_duplicadas>=0 AND linhas_nao_processadas>=0",
            name="contagens_validas",
        ),
        {"schema": "ops"},
    )
    execucao_id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    modo: Mapped[str] = mapped_column(String(30))
    versao_codigo: Mapped[str] = mapped_column(String(40), server_default="nao_aplicavel")
    versao_contrato: Mapped[str] = mapped_column(String(40), server_default="nao_aplicavel")
    situacao: Mapped[str] = mapped_column(String(20), server_default="EM_EXECUCAO")
    parametros: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    iniciado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erro: Mapped[str | None] = mapped_column(Text)


class LoteProcessamento(BaseModelo):
    """Relaciona janela e manifesto bronze à execução que confirmou a carga."""

    __tablename__ = "lote"
    __table_args__ = (
        CheckConstraint("janela_fim >= janela_inicio", name="janela_valida"),
        {"schema": "ops"},
    )
    lote_id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    execucao_id: Mapped[UUID] = mapped_column(ForeignKey("ops.execucao.execucao_id"), index=True)
    fonte: Mapped[str] = mapped_column(String(30))
    chave: Mapped[str] = mapped_column(String(100))
    janela_inicio: Mapped[date] = mapped_column(Date)
    janela_fim: Mapped[date] = mapped_column(Date)
    manifesto: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str | None] = mapped_column(String(64))
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SerieEconomica(BaseModelo):
    """Catálogo mínimo de significado e unidade das séries selecionadas."""

    __tablename__ = "dim_serie"
    __table_args__ = {"schema": "core"}
    codigo_sgs: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    nome: Mapped[str] = mapped_column(String(150))
    periodicidade: Mapped[str] = mapped_column(String(20))
    unidade: Mapped[str] = mapped_column(String(30))
    inicio_publico: Mapped[date] = mapped_column(Date)


class ObservacaoSerie(BaseModelo):
    """Observação exata, sem float, rastreável ao lote de origem."""

    __tablename__ = "fato_serie"
    __table_args__ = (
        CheckConstraint("valor != 'NaN'::numeric", name="valor_finito"),
        {"schema": "core"},
    )
    codigo_sgs: Mapped[int] = mapped_column(
        ForeignKey("core.dim_serie.codigo_sgs"), primary_key=True
    )
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    lote_id: Mapped[UUID] = mapped_column(ForeignKey("ops.lote.lote_id"), index=True)
    origem_coletada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    alterado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EtapaPipeline(ContagensOperacionais, BaseModelo):
    """Resultado de qualidade de um artefato ou do manifesto inteiro."""

    __tablename__ = "etapa"
    __table_args__ = (
        CheckConstraint(
            "situacao IN ('EM_EXECUCAO','SUCESSO','PARCIAL','FALHA','IGNORADA')",
            name="situacao_valida",
        ),
        CheckConstraint(
            "linhas_lidas = linhas_validas + linhas_rejeitadas + linhas_duplicadas + "
            "linhas_nao_processadas AND linhas_validas>=0 AND linhas_rejeitadas>=0 AND "
            "linhas_duplicadas>=0 AND linhas_nao_processadas>=0",
            name="contagens_validas",
        ),
        {"schema": "ops"},
    )
    etapa_id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    execucao_id: Mapped[UUID] = mapped_column(ForeignKey("ops.execucao.execucao_id"), index=True)
    nome: Mapped[str] = mapped_column(String(40))
    fonte: Mapped[str] = mapped_column(String(20), server_default="bcb")
    codigo_serie: Mapped[int | None]
    situacao: Mapped[str] = mapped_column(String(20))
    iniciado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avisos: Mapped[list[str]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))


class ArtefatoPipeline(BaseModelo):
    """Referência auditada, mantendo identidade do bronze sem sobrescrevê-lo."""

    __tablename__ = "artefato"
    __table_args__ = (
        UniqueConstraint("artefato_id", "etapa_id", name="uq_artefato_etapa"),
        CheckConstraint("tamanho_bytes>=0 AND janela_fim>=janela_inicio", name="referencia_valida"),
        {"schema": "ops"},
    )
    artefato_id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    etapa_id: Mapped[UUID] = mapped_column(ForeignKey("ops.etapa.etapa_id"), index=True)
    identificador_bronze: Mapped[UUID]
    execucao_coleta_id: Mapped[UUID]
    caminho_metadados: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    janela_inicio: Mapped[date] = mapped_column(Date)
    janela_fim: Mapped[date] = mapped_column(Date)
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    codificacao_conteudo: Mapped[str | None] = mapped_column(String(100))


class RegistroQuarentena(BaseModelo):
    """Rejeição rastreável; envelope usa posição0, linhas começam em1."""

    __tablename__ = "quarentena"
    __table_args__ = (
        ForeignKeyConstraint(
            ["artefato_id", "etapa_id"],
            ["ops.artefato.artefato_id", "ops.artefato.etapa_id"],
            name="fk_quarentena_artefato_etapa",
        ),
        UniqueConstraint("etapa_id", "posicao", name="uq_quarentena_posicao"),
        CheckConstraint("posicao>=0", name="posicao_valida"),
        {"schema": "ops"},
    )
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    etapa_id: Mapped[UUID] = mapped_column(ForeignKey("ops.etapa.etapa_id"), index=True)
    artefato_id: Mapped[UUID | None] = mapped_column(index=True)
    posicao: Mapped[int]
    motivo: Mapped[str] = mapped_column(String(100))
    registro_original: Mapped[dict[str, str]] = mapped_column(JSONB)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PreparacaoBCB(BaseModelo):
    """Dados validados antes de qualquer promoção ao core."""

    __tablename__ = "preparacao_bcb"
    __table_args__ = (
        Index("ix_preparacao_bcb_serie_data", "codigo_sgs", "data"),
        {"schema": "ops"},
    )
    execucao_id: Mapped[UUID] = mapped_column(
        ForeignKey("ops.execucao.execucao_id"), primary_key=True
    )
    codigo_sgs: Mapped[int] = mapped_column(
        ForeignKey("core.dim_serie.codigo_sgs"), primary_key=True
    )
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(24, 10))
    origem_coletada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MarcoCoberturaBCB(BaseModelo):
    """Cobertura contígua confirmada, distinta da última observação publicada."""

    __tablename__ = "watermark_bcb"
    __table_args__ = ({"schema": "ops"},)
    codigo_sgs: Mapped[int] = mapped_column(
        ForeignKey("core.dim_serie.codigo_sgs"), primary_key=True
    )
    fim_coberto: Mapped[date] = mapped_column(Date)
    ultima_observacao: Mapped[date] = mapped_column(Date)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class EstadoPublicacao(BaseModelo):
    """Gerações do domínio; gold só avança na etapa futura de publicação."""

    __tablename__ = "publicacao"
    __table_args__ = (
        CheckConstraint("versao_core>=versao_gold AND versao_gold>=0", name="versoes_validas"),
        CheckConstraint("situacao IN ('PENDENTE','PRONTA')", name="situacao_valida"),
        {"schema": "ops"},
    )
    dominio: Mapped[str] = mapped_column(String(20), primary_key=True)
    versao_core: Mapped[int] = mapped_column(BigInteger, server_default="0")
    versao_gold: Mapped[int] = mapped_column(BigInteger, server_default="0")
    data_publicacao: Mapped[date | None] = mapped_column(Date)
    situacao: Mapped[str] = mapped_column(String(20), server_default="PENDENTE")
