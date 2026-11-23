"""Preserva consultas confirmadas em falhas posteriores e restringe timestamps."""

from collections.abc import Sequence
from pathlib import Path

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        (Path(__file__).resolve().parents[1] / "sql" / "0009_frescor_consulta.sql").read_text(
            encoding="utf-8-sig"
        )
    )


def downgrade() -> None:
    base = (Path(__file__).resolve().parents[1] / "sql" / "0008_monitoramento.sql").read_text(
        encoding="utf-8-sig"
    )
    visao = base.split("CREATE VIEW ops.v_monitoramento_ibge_api AS", 1)[1].split(
        "CREATE VIEW ops.v_cobertura_ibge_api", 1
    )[0]
    op.execute("CREATE OR REPLACE VIEW ops.v_monitoramento_ibge_api AS" + visao)
