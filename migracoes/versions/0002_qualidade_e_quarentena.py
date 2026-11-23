"""qualidade e quarentena"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Aplica a revisão do esquema."""
    # Revisão independente da base inicial; não modificar após aplicação.
    op.create_table(
        "etapa",
        sa.Column(
            "etapa_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("execucao_id", sa.Uuid(), nullable=False),
        sa.Column("nome", sa.String(length=40), nullable=False),
        sa.Column("fonte", sa.String(length=20), server_default="bcb", nullable=False),
        sa.Column("codigo_serie", sa.Integer(), nullable=True),
        sa.Column("situacao", sa.String(length=20), nullable=False),
        sa.Column(
            "iniciado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "avisos",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("linhas_lidas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("linhas_validas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("linhas_rejeitadas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("linhas_duplicadas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("linhas_nao_processadas", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "situacao IN ('EM_EXECUCAO','SUCESSO','PARCIAL','FALHA','IGNORADA')",
            name=op.f("ck_etapa_situacao_valida"),
        ),
        sa.CheckConstraint(
            "linhas_lidas = linhas_validas + linhas_rejeitadas + linhas_duplicadas + "
            "linhas_nao_processadas AND linhas_validas>=0 AND linhas_rejeitadas>=0 AND "
            "linhas_duplicadas>=0 AND linhas_nao_processadas>=0",
            name=op.f("ck_etapa_contagens_validas"),
        ),
        sa.ForeignKeyConstraint(
            ["execucao_id"],
            ["ops.execucao.execucao_id"],
            name=op.f("fk_etapa_execucao_id_execucao"),
        ),
        sa.PrimaryKeyConstraint("etapa_id", name=op.f("pk_etapa")),
        schema="ops",
    )
    op.create_index(
        op.f("ix_etapa_execucao_id"), "etapa", ["execucao_id"], unique=False, schema="ops"
    )
    op.create_table(
        "artefato",
        sa.Column(
            "artefato_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("etapa_id", sa.Uuid(), nullable=False),
        sa.Column("identificador_bronze", sa.Uuid(), nullable=False),
        sa.Column("execucao_coleta_id", sa.Uuid(), nullable=False),
        sa.Column("caminho_metadados", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=False),
        sa.Column("janela_inicio", sa.Date(), nullable=False),
        sa.Column("janela_fim", sa.Date(), nullable=False),
        sa.Column("coletado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("codificacao_conteudo", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            "tamanho_bytes>=0 AND janela_fim>=janela_inicio",
            name=op.f("ck_artefato_referencia_valida"),
        ),
        sa.ForeignKeyConstraint(
            ["etapa_id"], ["ops.etapa.etapa_id"], name=op.f("fk_artefato_etapa_id_etapa")
        ),
        sa.PrimaryKeyConstraint("artefato_id", name=op.f("pk_artefato")),
        sa.UniqueConstraint("artefato_id", "etapa_id", name="uq_artefato_etapa"),
        schema="ops",
    )
    op.create_index(
        op.f("ix_artefato_etapa_id"), "artefato", ["etapa_id"], unique=False, schema="ops"
    )
    op.create_table(
        "quarentena",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("etapa_id", sa.Uuid(), nullable=False),
        sa.Column("artefato_id", sa.Uuid(), nullable=True),
        sa.Column("posicao", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(length=100), nullable=False),
        sa.Column("registro_original", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "criado_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("posicao>=0", name=op.f("ck_quarentena_posicao_valida")),
        sa.ForeignKeyConstraint(
            ["artefato_id", "etapa_id"],
            ["ops.artefato.artefato_id", "ops.artefato.etapa_id"],
            name="fk_quarentena_artefato_etapa",
        ),
        sa.ForeignKeyConstraint(
            ["etapa_id"], ["ops.etapa.etapa_id"], name=op.f("fk_quarentena_etapa_id_etapa")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quarentena")),
        sa.UniqueConstraint("etapa_id", "posicao", name="uq_quarentena_posicao"),
        schema="ops",
    )
    op.create_index(
        op.f("ix_quarentena_artefato_id"), "quarentena", ["artefato_id"], unique=False, schema="ops"
    )
    op.create_index(
        op.f("ix_quarentena_etapa_id"), "quarentena", ["etapa_id"], unique=False, schema="ops"
    )
    op.add_column(
        "execucao",
        sa.Column(
            "versao_codigo", sa.String(length=40), server_default="nao_aplicavel", nullable=False
        ),
        schema="ops",
    )
    op.add_column(
        "execucao",
        sa.Column(
            "versao_contrato", sa.String(length=40), server_default="nao_aplicavel", nullable=False
        ),
        schema="ops",
    )
    op.add_column(
        "execucao",
        sa.Column("linhas_lidas", sa.Integer(), server_default="0", nullable=False),
        schema="ops",
    )
    op.add_column(
        "execucao",
        sa.Column("linhas_validas", sa.Integer(), server_default="0", nullable=False),
        schema="ops",
    )
    op.add_column(
        "execucao",
        sa.Column("linhas_rejeitadas", sa.Integer(), server_default="0", nullable=False),
        schema="ops",
    )
    op.add_column(
        "execucao",
        sa.Column("linhas_duplicadas", sa.Integer(), server_default="0", nullable=False),
        schema="ops",
    )
    op.add_column(
        "execucao",
        sa.Column("linhas_nao_processadas", sa.Integer(), server_default="0", nullable=False),
        schema="ops",
    )

    op.create_check_constraint(
        op.f("ck_execucao_contagens_validas"),
        "execucao",
        "linhas_lidas = linhas_validas + linhas_rejeitadas + linhas_duplicadas + "
        "linhas_nao_processadas AND linhas_validas>=0 AND linhas_rejeitadas>=0 AND "
        "linhas_duplicadas>=0 AND linhas_nao_processadas>=0",
        schema="ops",
    )


def downgrade() -> None:
    """Reverte a revisão; usar somente em destino apropriado."""
    # Revisão independente da base inicial; não modificar após aplicação.
    op.drop_constraint(
        op.f("ck_execucao_contagens_validas"), "execucao", schema="ops", type_="check"
    )
    op.drop_column("execucao", "linhas_nao_processadas", schema="ops")
    op.drop_column("execucao", "linhas_duplicadas", schema="ops")
    op.drop_column("execucao", "linhas_rejeitadas", schema="ops")
    op.drop_column("execucao", "linhas_validas", schema="ops")
    op.drop_column("execucao", "linhas_lidas", schema="ops")
    op.drop_column("execucao", "versao_contrato", schema="ops")
    op.drop_column("execucao", "versao_codigo", schema="ops")
    op.drop_index(op.f("ix_quarentena_etapa_id"), table_name="quarentena", schema="ops")
    op.drop_index(op.f("ix_quarentena_artefato_id"), table_name="quarentena", schema="ops")
    op.drop_table("quarentena", schema="ops")
    op.drop_index(op.f("ix_artefato_etapa_id"), table_name="artefato", schema="ops")
    op.drop_table("artefato", schema="ops")
    op.drop_index(op.f("ix_etapa_execucao_id"), table_name="etapa", schema="ops")
    op.drop_table("etapa", schema="ops")
