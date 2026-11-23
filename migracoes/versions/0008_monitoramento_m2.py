"""Visões agregadas e sanitizadas de monitoramento M2."""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0008_monitoramento.sql").read_text(
            encoding="utf-8-sig"
        )
    )


def downgrade() -> None:
    for nome in ("v_cobertura_ibge_api", "v_monitoramento_ibge_api", "v_metricas_etapas_api"):
        op.execute(f"DROP VIEW ops.{nome}")
