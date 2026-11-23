"""Dimensões territoriais e estimativas IBGE com snapshots e cobertura gold."""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0007_populacao.sql").read_text(
            encoding="utf-8-sig"
        )
    )


def downgrade() -> None:
    op.execute("SET LOCAL ROLE publicador")
    for nome in ("mv_populacao_brasil", "mv_populacao_regiao", "mv_populacao_uf"):
        op.execute(f"DROP MATERIALIZED VIEW mart.{nome}")
    op.execute("RESET ROLE")
    for nome in (
        "fato_populacao",
        "dim_indicador",
        "dim_municipio",
        "municipio_snapshot",
        "snapshot_localidades",
        "dim_uf",
        "dim_regiao",
    ):
        op.drop_table(nome, schema="core")
    op.execute("DROP FUNCTION core.impedir_alteracao_snapshot()")
    op.execute("REVOKE SELECT ON ops.lote FROM publicador")
