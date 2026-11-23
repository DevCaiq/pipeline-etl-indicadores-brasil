"""Dimensões territoriais, snapshots e fatos da população estimada."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pipeline_etl.banco.modelos import BaseModelo


class DimensaoRegiao(BaseModelo):
    """Regiões oficiais referenciadas pelos snapshots."""

    __tablename__ = "dim_regiao"
    __table_args__ = ({"schema": "core"},)
    codigo: Mapped[int] = mapped_column(primary_key=True)
    sigla: Mapped[str] = mapped_column(String(2), unique=True)
    nome: Mapped[str] = mapped_column(Text)


class DimensaoUF(BaseModelo):
    """UF com referência regional oficial."""

    __tablename__ = "dim_uf"
    __table_args__ = (UniqueConstraint("codigo", "regiao_codigo"), {"schema": "core"})
    codigo: Mapped[int] = mapped_column(primary_key=True)
    sigla: Mapped[str] = mapped_column(String(2), unique=True)
    nome: Mapped[str] = mapped_column(Text)
    regiao_codigo: Mapped[int] = mapped_column(ForeignKey("core.dim_regiao.codigo"))


class SnapshotLocalidades(BaseModelo):
    """Identidade imutável de uma resposta territorial normalizada."""

    __tablename__ = "snapshot_localidades"
    __table_args__ = (
        CheckConstraint("checksum_normalizado ~ '^[0-9a-f]{64}$'", name="checksum_valido"),
        {"schema": "core"},
    )
    snapshot_id: Mapped[UUID] = mapped_column(primary_key=True)
    checksum_normalizado: Mapped[str] = mapped_column(String(64), unique=True)
    lote_id: Mapped[UUID] = mapped_column(ForeignKey("ops.lote.lote_id"))
    coletado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MunicipioSnapshot(BaseModelo):
    """Associação territorial preservada para denominadores históricos."""

    __tablename__ = "municipio_snapshot"
    __table_args__ = (
        CheckConstraint("codigo_ibge ~ '^[0-9]{7}$'", name="codigo_valido"),
        ForeignKeyConstraint(
            ["uf_codigo", "regiao_codigo"], ["core.dim_uf.codigo", "core.dim_uf.regiao_codigo"]
        ),
        UniqueConstraint("snapshot_id", "codigo_ibge", "uf_codigo", "regiao_codigo"),
        {"schema": "core"},
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.snapshot_localidades.snapshot_id"), primary_key=True
    )
    codigo_ibge: Mapped[str] = mapped_column(CHAR(7), primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    uf_codigo: Mapped[int] = mapped_column(ForeignKey("core.dim_uf.codigo"))
    regiao_codigo: Mapped[int] = mapped_column(ForeignKey("core.dim_regiao.codigo"))


class DimensaoMunicipio(BaseModelo):
    """Cadastro atual; a história permanece no snapshot."""

    __tablename__ = "dim_municipio"
    __table_args__ = (
        CheckConstraint("codigo_ibge ~ '^[0-9]{7}$'", name="codigo_valido"),
        ForeignKeyConstraint(
            ["snapshot_id", "codigo_ibge"],
            ["core.municipio_snapshot.snapshot_id", "core.municipio_snapshot.codigo_ibge"],
        ),
        Index("ix_dim_municipio_uf_codigo_ibge", "uf_codigo", "codigo_ibge"),
        {"schema": "core"},
    )
    codigo_ibge: Mapped[str] = mapped_column(CHAR(7), primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    uf_codigo: Mapped[int] = mapped_column(ForeignKey("core.dim_uf.codigo"))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("core.snapshot_localidades.snapshot_id"))


class DimensaoIndicador(BaseModelo):
    """Contrato identificado por produtor, tabela, variável e natureza."""

    __tablename__ = "dim_indicador"
    __table_args__ = (
        UniqueConstraint("fonte", "tabela", "variavel", "natureza"),
        {"schema": "core"},
    )
    indicador_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    fonte: Mapped[str] = mapped_column(String(30))
    tabela: Mapped[str] = mapped_column(String(30))
    variavel: Mapped[str] = mapped_column(String(30))
    natureza: Mapped[str] = mapped_column(String(30))
    unidade: Mapped[str] = mapped_column(String(50))
    metadados: Mapped[dict[str, object]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))


class FatoPopulacao(BaseModelo):
    """Valor ou ausência oficial com linhagem e associação territorial explícitas."""

    __tablename__ = "fato_populacao"
    __table_args__ = (
        CheckConstraint("codigo_ibge ~ '^[0-9]{7}$'", name="codigo_valido"),
        CheckConstraint("ano >= 2020", name="ano_valido"),
        CheckConstraint("base_territorial = 'atual_na_coleta'", name="base_valida"),
        CheckConstraint(
            "(populacao IS NOT NULL AND populacao >= 0 AND marcador IS NULL AND motivo IS NULL) "
            "OR (populacao IS NULL AND marcador IS NOT NULL AND marcador='...' "
            "AND motivo IS NOT NULL AND motivo='DADO_NAO_DISPONIVEL')",
            name="valor_valido",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "codigo_ibge", "uf_referencia", "regiao_referencia"],
            [
                "core.municipio_snapshot.snapshot_id",
                "core.municipio_snapshot.codigo_ibge",
                "core.municipio_snapshot.uf_codigo",
                "core.municipio_snapshot.regiao_codigo",
            ],
        ),
        Index("ix_fato_populacao_ano_indicador_uf", "ano", "indicador_id", "uf_referencia"),
        {"schema": "core"},
    )
    codigo_ibge: Mapped[str] = mapped_column(
        CHAR(7), ForeignKey("core.dim_municipio.codigo_ibge"), primary_key=True
    )
    ano: Mapped[int] = mapped_column(primary_key=True)
    indicador_id: Mapped[int] = mapped_column(
        ForeignKey("core.dim_indicador.indicador_id"), primary_key=True
    )
    populacao: Mapped[int | None] = mapped_column(BigInteger)
    marcador: Mapped[str | None] = mapped_column(String(10))
    motivo: Mapped[str | None] = mapped_column(Text)
    uf_referencia: Mapped[int] = mapped_column(ForeignKey("core.dim_uf.codigo"))
    regiao_referencia: Mapped[int] = mapped_column(ForeignKey("core.dim_regiao.codigo"))
    base_territorial: Mapped[str] = mapped_column(String(30), server_default="atual_na_coleta")
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("core.snapshot_localidades.snapshot_id"))
    lote_id: Mapped[UUID] = mapped_column(ForeignKey("ops.lote.lote_id"))
    origem_coletada_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    alterado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
