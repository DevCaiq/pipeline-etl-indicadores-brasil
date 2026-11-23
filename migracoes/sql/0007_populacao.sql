-- Revisão 0007 imutável: dimensões, snapshots e população IBGE.
CREATE TABLE core.dim_regiao (
 codigo integer PRIMARY KEY, sigla varchar(2) NOT NULL UNIQUE, nome text NOT NULL
);
CREATE TABLE core.dim_uf (
 codigo integer PRIMARY KEY, sigla varchar(2) NOT NULL UNIQUE, nome text NOT NULL,
 regiao_codigo integer NOT NULL REFERENCES core.dim_regiao(codigo),
 UNIQUE(codigo,regiao_codigo)
);
CREATE TABLE core.snapshot_localidades (
 snapshot_id uuid PRIMARY KEY, checksum_normalizado varchar(64) NOT NULL UNIQUE
 CHECK(checksum_normalizado ~ '^[0-9a-f]{64}$'),
 lote_id uuid NOT NULL REFERENCES ops.lote(lote_id), coletado_em timestamptz NOT NULL
);
CREATE TABLE core.municipio_snapshot (
 snapshot_id uuid NOT NULL REFERENCES core.snapshot_localidades(snapshot_id),
 codigo_ibge char(7) NOT NULL CHECK(codigo_ibge ~ '^[0-9]{7}$'), nome text NOT NULL,
 uf_codigo integer NOT NULL REFERENCES core.dim_uf(codigo),
 regiao_codigo integer NOT NULL REFERENCES core.dim_regiao(codigo),
 PRIMARY KEY(snapshot_id,codigo_ibge),
 UNIQUE(snapshot_id,codigo_ibge,uf_codigo,regiao_codigo),
 FOREIGN KEY(uf_codigo,regiao_codigo) REFERENCES core.dim_uf(codigo,regiao_codigo)
);
CREATE TABLE core.dim_municipio (
 codigo_ibge char(7) PRIMARY KEY CHECK(codigo_ibge ~ '^[0-9]{7}$'), nome text NOT NULL,
 uf_codigo integer NOT NULL REFERENCES core.dim_uf(codigo), ativo boolean NOT NULL DEFAULT true,
 snapshot_id uuid NOT NULL REFERENCES core.snapshot_localidades(snapshot_id),
 FOREIGN KEY(snapshot_id,codigo_ibge) REFERENCES core.municipio_snapshot(snapshot_id,codigo_ibge)
);
CREATE INDEX ix_dim_municipio_uf_codigo_ibge ON core.dim_municipio(uf_codigo,codigo_ibge);
CREATE TABLE core.dim_indicador (
 indicador_id integer PRIMARY KEY, fonte varchar(30) NOT NULL, tabela varchar(30) NOT NULL,
 variavel varchar(30) NOT NULL, natureza varchar(30) NOT NULL, unidade varchar(50) NOT NULL,
 metadados jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(fonte,tabela,variavel,natureza)
);
INSERT INTO core.dim_indicador(indicador_id,fonte,tabela,variavel,natureza,unidade)
 VALUES(1,'IBGE','6579','9324','estimativa','Pessoas');
CREATE TABLE core.fato_populacao (
 codigo_ibge char(7) NOT NULL REFERENCES core.dim_municipio(codigo_ibge)
 CHECK(codigo_ibge ~ '^[0-9]{7}$'), ano integer NOT NULL CHECK(ano>=2020),
 indicador_id integer NOT NULL REFERENCES core.dim_indicador(indicador_id),
 populacao bigint, marcador varchar(10), motivo text,
 uf_referencia integer NOT NULL REFERENCES core.dim_uf(codigo),
 regiao_referencia integer NOT NULL REFERENCES core.dim_regiao(codigo),
 base_territorial varchar(30) NOT NULL DEFAULT 'atual_na_coleta'
 CHECK(base_territorial='atual_na_coleta'),
 snapshot_id uuid NOT NULL REFERENCES core.snapshot_localidades(snapshot_id),
 lote_id uuid NOT NULL REFERENCES ops.lote(lote_id), origem_coletada_em timestamptz NOT NULL,
 alterado_em timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(codigo_ibge,ano,indicador_id),
 FOREIGN KEY(snapshot_id,codigo_ibge,uf_referencia,regiao_referencia)
 REFERENCES core.municipio_snapshot(snapshot_id,codigo_ibge,uf_codigo,regiao_codigo),
 CHECK((populacao IS NOT NULL AND populacao>=0 AND marcador IS NULL AND motivo IS NULL)
 OR (populacao IS NULL AND marcador IS NOT NULL AND marcador='...'
 AND motivo IS NOT NULL AND motivo='DADO_NAO_DISPONIVEL'))
);
CREATE INDEX ix_fato_populacao_ano_indicador_uf
 ON core.fato_populacao(ano,indicador_id,uf_referencia);
-- Snapshot e seus membros não aceitam alteração ou remoção, mesmo pelo loader.
CREATE FUNCTION core.impedir_alteracao_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Snapshot territorial imutável'; END;
$$;
CREATE TRIGGER snapshot_localidades_imutavel BEFORE UPDATE OR DELETE
 ON core.snapshot_localidades FOR EACH ROW EXECUTE FUNCTION core.impedir_alteracao_snapshot();
CREATE TRIGGER municipio_snapshot_imutavel BEFORE UPDATE OR DELETE
 ON core.municipio_snapshot FOR EACH ROW EXECUTE FUNCTION core.impedir_alteracao_snapshot();
GRANT SELECT ON core.dim_regiao,core.dim_uf,core.snapshot_localidades,core.municipio_snapshot,
 core.dim_municipio,core.dim_indicador,core.fato_populacao TO publicador;
GRANT SELECT ON ops.lote TO publicador;
SET LOCAL ROLE publicador;
-- Cada conjunto usa um snapshot explícito. O publicador rejeita versões mistas antes do refresh.
CREATE MATERIALIZED VIEW mart.mv_populacao_uf AS
WITH conjuntos AS (
 SELECT DISTINCT ano,indicador_id,snapshot_id,base_territorial FROM core.fato_populacao
)
SELECT c.ano,c.indicador_id,c.snapshot_id,c.base_territorial,m.uf_codigo AS uf_codigo,
 count(*) AS municipios_esperados,count(f.codigo_ibge) AS municipios_recebidos,
 count(f.populacao) AS municipios_disponiveis,
 count(*)-count(f.populacao) AS municipios_indisponiveis,
 sum(f.populacao) AS subtotal_disponivel,
 CASE WHEN count(*)=count(f.populacao) THEN sum(f.populacao) END AS populacao_total,
 count(*)=count(f.populacao) AS completo,
 CASE WHEN count(*)<>count(f.populacao) THEN 'COBERTURA_INCOMPLETA'::text END AS motivo
FROM conjuntos c JOIN core.municipio_snapshot m ON m.snapshot_id=c.snapshot_id
LEFT JOIN core.fato_populacao f ON f.snapshot_id=c.snapshot_id AND f.codigo_ibge=m.codigo_ibge
 AND f.ano=c.ano AND f.indicador_id=c.indicador_id AND f.base_territorial=c.base_territorial
GROUP BY c.ano,c.indicador_id,c.snapshot_id,c.base_territorial,m.uf_codigo;
CREATE UNIQUE INDEX uq_mv_populacao_uf ON mart.mv_populacao_uf
 (ano,indicador_id,snapshot_id,base_territorial,uf_codigo);
CREATE MATERIALIZED VIEW mart.mv_populacao_regiao AS
WITH conjuntos AS (
 SELECT DISTINCT ano,indicador_id,snapshot_id,base_territorial FROM core.fato_populacao
)
SELECT c.ano,c.indicador_id,c.snapshot_id,c.base_territorial,m.regiao_codigo AS regiao_codigo,
 count(*) AS municipios_esperados,count(f.codigo_ibge) AS municipios_recebidos,
 count(f.populacao) AS municipios_disponiveis,
 count(*)-count(f.populacao) AS municipios_indisponiveis,
 sum(f.populacao) AS subtotal_disponivel,
 CASE WHEN count(*)=count(f.populacao) THEN sum(f.populacao) END AS populacao_total,
 count(*)=count(f.populacao) AS completo,
 CASE WHEN count(*)<>count(f.populacao) THEN 'COBERTURA_INCOMPLETA'::text END AS motivo
FROM conjuntos c JOIN core.municipio_snapshot m ON m.snapshot_id=c.snapshot_id
LEFT JOIN core.fato_populacao f ON f.snapshot_id=c.snapshot_id AND f.codigo_ibge=m.codigo_ibge
 AND f.ano=c.ano AND f.indicador_id=c.indicador_id AND f.base_territorial=c.base_territorial
GROUP BY c.ano,c.indicador_id,c.snapshot_id,c.base_territorial,m.regiao_codigo;
CREATE UNIQUE INDEX uq_mv_populacao_regiao ON mart.mv_populacao_regiao
 (ano,indicador_id,snapshot_id,base_territorial,regiao_codigo);
CREATE MATERIALIZED VIEW mart.mv_populacao_brasil AS
WITH conjuntos AS (
 SELECT DISTINCT ano,indicador_id,snapshot_id,base_territorial FROM core.fato_populacao
)
SELECT c.ano,c.indicador_id,c.snapshot_id,c.base_territorial,1::integer AS brasil_codigo,
 count(*) AS municipios_esperados,count(f.codigo_ibge) AS municipios_recebidos,
 count(f.populacao) AS municipios_disponiveis,
 count(*)-count(f.populacao) AS municipios_indisponiveis,
 sum(f.populacao) AS subtotal_disponivel,
 CASE WHEN count(*)=count(f.populacao) THEN sum(f.populacao) END AS populacao_total,
 count(*)=count(f.populacao) AS completo,
 CASE WHEN count(*)<>count(f.populacao) THEN 'COBERTURA_INCOMPLETA'::text END AS motivo
FROM conjuntos c JOIN core.municipio_snapshot m ON m.snapshot_id=c.snapshot_id
LEFT JOIN core.fato_populacao f ON f.snapshot_id=c.snapshot_id AND f.codigo_ibge=m.codigo_ibge
 AND f.ano=c.ano AND f.indicador_id=c.indicador_id AND f.base_territorial=c.base_territorial
GROUP BY c.ano,c.indicador_id,c.snapshot_id,c.base_territorial;
CREATE UNIQUE INDEX uq_mv_populacao_brasil ON mart.mv_populacao_brasil
 (ano,indicador_id,snapshot_id,base_territorial,brasil_codigo);
GRANT SELECT ON mart.mv_populacao_uf,mart.mv_populacao_regiao,mart.mv_populacao_brasil TO api_leitura;
RESET ROLE;
