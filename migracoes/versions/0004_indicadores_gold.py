"""Indicadores BCB e privilégios de publicação atômica."""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publicacao", sa.Column("data_publicacao", sa.Date(), nullable=True), schema="ops"
    )
    op.execute("GRANT USAGE ON SCHEMA core,ops TO publicador")
    op.execute("GRANT SELECT ON core.fato_serie,core.dim_serie,ops.publicacao TO publicador")
    op.execute("GRANT UPDATE(versao_gold,situacao,data_publicacao) ON ops.publicacao TO publicador")
    op.execute("GRANT SELECT,INSERT,UPDATE ON ops.execucao TO publicador")
    op.execute("SET LOCAL ROLE publicador")
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0004_indicadores.sql").read_text(
            encoding="utf-8"
        )
    )
    op.execute("RESET ROLE")


def downgrade() -> None:
    op.execute("SET LOCAL ROLE publicador")
    for nome in ("mv_ipca_12m", "mv_serie_anual", "mv_serie_mensal"):
        op.execute(f"DROP MATERIALIZED VIEW mart.{nome}")
    op.execute("DROP FUNCTION mart.compor_taxas_bcb(numeric[])")
    op.execute("RESET ROLE")
    op.execute(
        "REVOKE UPDATE(versao_gold,situacao,data_publicacao) ON ops.publicacao FROM publicador"
    )
    op.execute("REVOKE SELECT ON core.fato_serie,core.dim_serie,ops.publicacao FROM publicador")
    op.execute("REVOKE SELECT,INSERT,UPDATE ON ops.execucao FROM publicador")
    op.execute("REVOKE USAGE ON SCHEMA core,ops FROM publicador")
    op.drop_column("publicacao", "data_publicacao", schema="ops")
