"""Visões sanitizadas para consulta pública da API M1."""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE VIEW ops.v_publicacao_api AS SELECT "
        "dominio,versao_core,versao_gold,situacao,data_publicacao FROM "
        "ops.publicacao"
    )
    op.execute("CREATE VIEW ops.v_esquema_api AS SELECT version_num FROM public.alembic_version")
    op.execute("""CREATE VIEW ops.v_execucoes_api AS
      SELECT execucao_id,modo,situacao,iniciado_em,finalizado_em,
      CASE WHEN modo IN
('carga_bcb','coleta_validacao','validacao_bronze','coleta_atualizacao','atualizacao_bcb','publicacao_bcb')
THEN 'bcb'::text END AS fonte
      FROM ops.execucao""")
    op.execute("""CREATE VIEW ops.v_frescor_api AS
      SELECT s.codigo_sgs,min(f.data) AS inicio,max(f.data) AS fim,count(f.data) AS observacoes,
      (SELECT max(e.finalizado_em) FROM ops.execucao e WHERE e.modo IN
('coleta_validacao','coleta_atualizacao')
         AND e.situacao='SUCESSO' AND e.parametros->>'codigo_serie'=s.codigo_sgs::text) AS
ultima_consulta,
      (SELECT max(e.finalizado_em) FROM ops.execucao e WHERE e.modo='publicacao_bcb' AND
e.situacao='SUCESSO') AS ultima_publicacao
      FROM core.dim_serie s LEFT JOIN core.fato_serie f ON f.codigo_sgs=s.codigo_sgs AND
f.data>=s.inicio_publico
      GROUP BY s.codigo_sgs""")
    op.execute(
        "GRANT SELECT ON ops.v_publicacao_api,ops.v_esquema_api,ops.v_execucoes"
        "_api,ops.v_frescor_api TO api_leitura"
    )


def downgrade() -> None:
    for nome in ("v_frescor_api", "v_execucoes_api", "v_esquema_api", "v_publicacao_api"):
        op.execute(f"DROP VIEW ops.{nome}")
