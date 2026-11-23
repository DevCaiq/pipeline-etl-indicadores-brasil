"""Remove escrita herdada nas visões públicas de consulta."""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # As views criadas em ops herdaram os privilégios de processamento das tabelas ETL.
    # A visão de versão nunca pode permitir alteração indireta de alembic_version.
    op.execute(
        "REVOKE INSERT,UPDATE,DELETE ON ops.v_esquema_api,ops.v_publicacao_api, "
        "ops.v_execucoes_api,ops.v_frescor_api FROM processamento"
    )


def downgrade() -> None:
    op.execute(
        "GRANT INSERT,UPDATE,DELETE ON ops.v_esquema_api,ops.v_publicacao_api, "
        "ops.v_execucoes_api,ops.v_frescor_api TO processamento"
    )
