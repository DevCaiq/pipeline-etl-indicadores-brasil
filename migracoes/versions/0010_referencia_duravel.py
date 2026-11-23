"""Materializadas BCB usam referência durável, preservada pelo backup."""

from collections.abc import Sequence
from pathlib import Path

from alembic import op
from sqlalchemy import text

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOMES = ("mv_serie_mensal", "mv_serie_anual", "mv_ipca_12m")


def _recriar_materializadas(duravel: bool) -> None:
    conexao = op.get_bind()
    if not conexao.scalar(text("SELECT pg_try_advisory_xact_lock(2026111801)")):
        raise RuntimeError("Migração adiada: carga ou publicação BCB em andamento.")
    estado = (
        conexao.execute(
            text(
                "SELECT versao_core,versao_gold,situacao,data_publicacao "
                "FROM ops.publicacao WHERE dominio='bcb' FOR UPDATE"
            )
        )
        .mappings()
        .first()
    )
    existem_fatos = conexao.scalar(text("SELECT EXISTS(SELECT 1 FROM core.fato_serie)"))
    estados = {
        linha.relname: linha.relispopulated
        for linha in conexao.execute(
            text(
                "SELECT relname,relispopulated FROM pg_class "
                "WHERE relnamespace='mart'::regnamespace "
                "AND relname IN ('mv_serie_mensal','mv_serie_anual','mv_ipca_12m')"
            )
        )
    }
    if (
        any(estados.values())
        and (existem_fatos or (estado is not None and estado["versao_core"] > 0))
        and (
            estado is None
            or estado["versao_core"] != estado["versao_gold"]
            or estado["situacao"] != "PRONTA"
            or estado["data_publicacao"] is None
        )
    ):
        raise RuntimeError("Migração adiada: publicação BCB pendente; publicar antes da migração.")
    pasta = Path(__file__).resolve().parents[1] / "sql"
    if duravel:
        definicao = (pasta / "0010_referencia_duravel.sql").read_text(encoding="utf-8-sig")
    else:
        original = (pasta / "0004_indicadores.sql").read_text(encoding="utf-8-sig")
        definicao = (
            "CREATE MATERIALIZED VIEW mart.mv_serie_mensal"
            + original.split("CREATE MATERIALIZED VIEW mart.mv_serie_mensal", 1)[1]
        )
    op.execute("SET LOCAL ROLE publicador")
    for nome in reversed(NOMES):
        op.execute(f"DROP MATERIALIZED VIEW mart.{nome}")
    op.execute(definicao)
    for nome in NOMES:
        if estados[nome]:
            op.execute(f"REFRESH MATERIALIZED VIEW mart.{nome}")
    op.execute("RESET ROLE")


def upgrade() -> None:
    _recriar_materializadas(True)


def downgrade() -> None:
    _recriar_materializadas(False)
