"""carga bcb transacional"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Aplica a revisão do esquema."""
    # Revisão independente; não alterar após aplicação.
    op.create_table(
        "publicacao",
        sa.Column("dominio", sa.String(length=20), nullable=False),
        sa.Column("versao_core", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("versao_gold", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("situacao", sa.String(length=20), server_default="PENDENTE", nullable=False),
        sa.CheckConstraint(
            "situacao IN ('PENDENTE','PRONTA')", name=op.f("ck_publicacao_situacao_valida")
        ),
        sa.CheckConstraint(
            "versao_core>=versao_gold AND versao_gold>=0",
            name=op.f("ck_publicacao_versoes_validas"),
        ),
        sa.PrimaryKeyConstraint("dominio", name=op.f("pk_publicacao")),
        schema="ops",
    )
    op.create_table(
        "preparacao_bcb",
        sa.Column("execucao_id", sa.Uuid(), nullable=False),
        sa.Column("codigo_sgs", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("origem_coletada_em", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["codigo_sgs"],
            ["core.dim_serie.codigo_sgs"],
            name=op.f("fk_preparacao_bcb_codigo_sgs_dim_serie"),
        ),
        sa.ForeignKeyConstraint(
            ["execucao_id"],
            ["ops.execucao.execucao_id"],
            name=op.f("fk_preparacao_bcb_execucao_id_execucao"),
        ),
        sa.PrimaryKeyConstraint(
            "execucao_id", "codigo_sgs", "data", name=op.f("pk_preparacao_bcb")
        ),
        schema="ops",
    )
    op.create_table(
        "watermark_bcb",
        sa.Column("codigo_sgs", sa.Integer(), nullable=False),
        sa.Column("fim_coberto", sa.Date(), nullable=False),
        sa.Column("ultima_observacao", sa.Date(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["codigo_sgs"],
            ["core.dim_serie.codigo_sgs"],
            name=op.f("fk_watermark_bcb_codigo_sgs_dim_serie"),
        ),
        sa.PrimaryKeyConstraint("codigo_sgs", name=op.f("pk_watermark_bcb")),
        schema="ops",
    )
    op.create_index(
        "ix_preparacao_bcb_serie_data", "preparacao_bcb", ["codigo_sgs", "data"], schema="ops"
    )
    op.add_column(
        "fato_serie",
        sa.Column("origem_coletada_em", sa.DateTime(timezone=True), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    """Reverte a revisão; usar somente em destino apropriado."""
    # Revisão independente; não alterar após aplicação.
    op.drop_column("fato_serie", "origem_coletada_em", schema="core")
    op.drop_table("watermark_bcb", schema="ops")
    op.drop_index("ix_preparacao_bcb_serie_data", table_name="preparacao_bcb", schema="ops")
    op.drop_table("preparacao_bcb", schema="ops")
    op.drop_table("publicacao", schema="ops")
