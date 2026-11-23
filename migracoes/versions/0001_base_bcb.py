"""base bcb"""

from collections.abc import Sequence
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Aplica a revisão do esquema."""
    # Objetos desta revisão permanecem imutáveis após aplicação.
    op.execute("CREATE SCHEMA ops")
    op.execute("CREATE SCHEMA core")
    op.execute("CREATE SCHEMA mart AUTHORIZATION publicador")
    op.create_table(
        "dim_serie",
        sa.Column("codigo_sgs", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("nome", sa.String(length=150), nullable=False),
        sa.Column("periodicidade", sa.String(length=20), nullable=False),
        sa.Column("unidade", sa.String(length=30), nullable=False),
        sa.Column("inicio_publico", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("codigo_sgs", name=op.f("pk_dim_serie")),
        schema="core",
    )
    op.create_table(
        "execucao",
        sa.Column(
            "execucao_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("modo", sa.String(length=30), nullable=False),
        sa.Column("situacao", sa.String(length=20), server_default="EM_EXECUCAO", nullable=False),
        sa.Column(
            "parametros",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "iniciado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finalizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "situacao IN ('EM_EXECUCAO','SUCESSO','PARCIAL','FALHA','IGNORADA')",
            name=op.f("ck_execucao_situacao_valida"),
        ),
        sa.PrimaryKeyConstraint("execucao_id", name=op.f("pk_execucao")),
        schema="ops",
    )
    op.create_table(
        "lote",
        sa.Column(
            "lote_id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("execucao_id", sa.Uuid(), nullable=False),
        sa.Column("fonte", sa.String(length=30), nullable=False),
        sa.Column("chave", sa.String(length=100), nullable=False),
        sa.Column("janela_inicio", sa.Date(), nullable=False),
        sa.Column("janela_fim", sa.Date(), nullable=False),
        sa.Column("manifesto", sa.Text(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("confirmado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("janela_fim >= janela_inicio", name=op.f("ck_lote_janela_valida")),
        sa.ForeignKeyConstraint(
            ["execucao_id"], ["ops.execucao.execucao_id"], name=op.f("fk_lote_execucao_id_execucao")
        ),
        sa.PrimaryKeyConstraint("lote_id", name=op.f("pk_lote")),
        schema="ops",
    )
    op.create_index(
        op.f("ix_lote_execucao_id"), "lote", ["execucao_id"], unique=False, schema="ops"
    )
    op.create_table(
        "fato_serie",
        sa.Column("codigo_sgs", sa.Integer(), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("valor", sa.Numeric(precision=24, scale=10), nullable=False),
        sa.Column("lote_id", sa.Uuid(), nullable=False),
        sa.Column(
            "alterado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("valor != 'NaN'::numeric", name=op.f("ck_fato_serie_valor_finito")),
        sa.ForeignKeyConstraint(
            ["codigo_sgs"],
            ["core.dim_serie.codigo_sgs"],
            name=op.f("fk_fato_serie_codigo_sgs_dim_serie"),
        ),
        sa.ForeignKeyConstraint(
            ["lote_id"], ["ops.lote.lote_id"], name=op.f("fk_fato_serie_lote_id_lote")
        ),
        sa.PrimaryKeyConstraint("codigo_sgs", "data", name=op.f("pk_fato_serie")),
        schema="core",
    )
    op.create_index(
        op.f("ix_fato_serie_lote_id"), "fato_serie", ["lote_id"], unique=False, schema="core"
    )

    catalogo = sa.table(
        "dim_serie",
        sa.column("codigo_sgs", sa.Integer),
        sa.column("nome", sa.String),
        sa.column("periodicidade", sa.String),
        sa.column("unidade", sa.String),
        sa.column("inicio_publico", sa.Date),
        schema="core",
    )
    op.bulk_insert(
        catalogo,
        [
            {
                "codigo_sgs": 432,
                "nome": "Meta Selic",
                "periodicidade": "diaria",
                "unidade": "% a.a.",
                "inicio_publico": date(2020, 1, 1),
            },
            {
                "codigo_sgs": 433,
                "nome": "IPCA",
                "periodicidade": "mensal",
                "unidade": "% no mes",
                "inicio_publico": date(2020, 1, 1),
            },
            {
                "codigo_sgs": 1,
                "nome": "Dolar americano - venda",
                "periodicidade": "diaria",
                "unidade": "BRL/USD",
                "inicio_publico": date(2020, 1, 1),
            },
        ],
    )
    op.execute(
        "CREATE VIEW ops.v_execucoes AS SELECT execucao_id, modo, situacao, iniciado_em, "
        "finalizado_em FROM ops.execucao"
    )
    op.execute("GRANT USAGE ON SCHEMA core, mart, ops TO api_leitura")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA core, mart TO api_leitura")
    op.execute("GRANT SELECT ON ops.v_execucoes TO api_leitura")
    op.execute("GRANT USAGE ON SCHEMA core, ops, mart TO processamento")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, ops TO processamento"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE migracoes IN SCHEMA core GRANT SELECT ON "
        "TABLES TO api_leitura"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE migracoes IN SCHEMA core, ops GRANT SELECT, "
        "INSERT, UPDATE, DELETE ON TABLES TO processamento"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE migracoes IN SCHEMA core, ops GRANT USAGE, "
        "SELECT ON SEQUENCES TO processamento"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE publicador IN SCHEMA mart GRANT SELECT ON "
        "TABLES TO api_leitura, processamento"
    )


def downgrade() -> None:
    """Reverte a revisão; usar somente em destino apropriado."""
    # Objetos desta revisão permanecem imutáveis após aplicação.
    op.execute("DROP VIEW ops.v_execucoes")
    op.drop_index(op.f("ix_fato_serie_lote_id"), table_name="fato_serie", schema="core")
    op.drop_table("fato_serie", schema="core")
    op.drop_index(op.f("ix_lote_execucao_id"), table_name="lote", schema="ops")
    op.drop_table("lote", schema="ops")
    op.drop_table("execucao", schema="ops")
    op.drop_table("dim_serie", schema="core")

    op.execute("DROP SCHEMA mart")
    op.execute("DROP SCHEMA core")
    op.execute("DROP SCHEMA ops")
