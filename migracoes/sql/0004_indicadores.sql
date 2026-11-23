-- Indicadores BCB versionados; não alterar após aplicar a revisão0004.
CREATE FUNCTION mart.compor_taxas_bcb(taxas numeric[]) RETURNS numeric
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE produto numeric := 1; taxa numeric;
BEGIN
    IF cardinality(taxas) = 0 THEN RETURN NULL; END IF;
    FOREACH taxa IN ARRAY taxas LOOP
        IF taxa IS NULL THEN RETURN NULL; END IF;
        produto := produto * (1 + taxa / 100::numeric);
    END LOOP;
    RETURN (produto - 1) * 100;
END;
$$;
REVOKE ALL ON FUNCTION mart.compor_taxas_bcb(numeric[]) FROM PUBLIC;

CREATE MATERIALIZED VIEW mart.mv_serie_mensal AS
WITH grupos AS (
 SELECT f.codigo_sgs, date_trunc('month', f.data)::date AS periodo,
        s.unidade, count(*) AS observacoes,
        CASE WHEN f.codigo_sgs<>433 THEN avg(f.valor) END AS media,
        CASE WHEN f.codigo_sgs<>433 THEN min(f.valor) END AS minimo,
        CASE WHEN f.codigo_sgs<>433 THEN max(f.valor) END AS maximo,
        CASE WHEN f.codigo_sgs<>433 THEN (array_agg(f.valor ORDER BY f.data DESC))[1] END AS ultimo,
        CASE WHEN f.codigo_sgs=433 AND count(*)=1 THEN max(f.valor) END AS variacao
 FROM core.fato_serie f JOIN core.dim_serie s ON s.codigo_sgs=f.codigo_sgs
 WHERE f.data >= DATE '2020-01-01'
 GROUP BY f.codigo_sgs, date_trunc('month', f.data)::date, s.unidade
), referencia AS (SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date AS data_referencia)
SELECT g.*, r.data_referencia,
       (periodo + INTERVAL '1 month')::date > r.data_referencia AS parcial,
       CASE WHEN codigo_sgs=433 THEN observacoes=1 AND (periodo + INTERVAL '1 month')::date<=r.data_referencia END AS completo,
       CASE WHEN codigo_sgs<>433 THEN 'CALENDARIO_NAO_HOMOLOGADO'
            WHEN (periodo + INTERVAL '1 month')::date>r.data_referencia THEN 'PERIODO_EM_ANDAMENTO'
            WHEN observacoes<>1 THEN 'MESES_AUSENTES' END AS motivo
FROM grupos g CROSS JOIN referencia r
WITH NO DATA;
CREATE UNIQUE INDEX uq_mv_serie_mensal ON mart.mv_serie_mensal(codigo_sgs,periodo);

CREATE MATERIALIZED VIEW mart.mv_serie_anual AS
WITH grupos AS (
 SELECT f.codigo_sgs, date_trunc('year', f.data)::date AS periodo, s.unidade,
        count(*) AS observacoes, count(DISTINCT date_trunc('month',f.data)) AS meses,
        CASE WHEN f.codigo_sgs<>433 THEN avg(f.valor) END AS media,
        CASE WHEN f.codigo_sgs<>433 THEN min(f.valor) END AS minimo,
        CASE WHEN f.codigo_sgs<>433 THEN max(f.valor) END AS maximo,
        CASE WHEN f.codigo_sgs<>433 THEN (array_agg(f.valor ORDER BY f.data DESC))[1] END AS ultimo,
        CASE WHEN f.codigo_sgs=433 AND count(*)=12 AND count(DISTINCT date_trunc('month',f.data))=12
             THEN mart.compor_taxas_bcb(array_agg(f.valor ORDER BY f.data)) END AS acumulado
 FROM core.fato_serie f JOIN core.dim_serie s ON s.codigo_sgs=f.codigo_sgs
 WHERE f.data >= DATE '2020-01-01'
 GROUP BY f.codigo_sgs,date_trunc('year',f.data)::date,s.unidade
), referencia AS (SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date AS data_referencia)
SELECT codigo_sgs,periodo,CASE WHEN codigo_sgs=433 THEN '% no ano' ELSE unidade END AS unidade,
       observacoes,media,minimo,maximo,ultimo,
       CASE WHEN (periodo + INTERVAL '1 year')::date<=r.data_referencia THEN acumulado END AS variacao,
       r.data_referencia, (periodo + INTERVAL '1 year')::date>r.data_referencia AS parcial,
       CASE WHEN codigo_sgs=433 THEN observacoes=12 AND meses=12 AND (periodo + INTERVAL '1 year')::date<=r.data_referencia END AS completo,
       CASE WHEN codigo_sgs<>433 THEN 'CALENDARIO_NAO_HOMOLOGADO'
            WHEN (periodo + INTERVAL '1 year')::date>r.data_referencia THEN 'PERIODO_EM_ANDAMENTO'
            WHEN observacoes<>12 OR meses<>12 THEN 'MESES_AUSENTES' END AS motivo
FROM grupos g CROSS JOIN referencia r
WITH NO DATA;
CREATE UNIQUE INDEX uq_mv_serie_anual ON mart.mv_serie_anual(codigo_sgs,periodo);

CREATE MATERIALIZED VIEW mart.mv_ipca_12m AS
WITH grupos AS (
 SELECT a.data AS periodo, count(f.data) AS observacoes,
        count(DISTINCT date_trunc('month',f.data)) AS meses,
        CASE WHEN count(f.data)=12 AND count(DISTINCT date_trunc('month',f.data))=12
             THEN mart.compor_taxas_bcb(array_agg(f.valor ORDER BY f.data)) END AS acumulado
 FROM core.fato_serie a LEFT JOIN core.fato_serie f
   ON f.codigo_sgs=433 AND f.data>= (a.data-INTERVAL '11 months')::date AND f.data<=a.data
 WHERE a.codigo_sgs=433 AND a.data >= DATE '2020-01-01'
 GROUP BY a.data
), referencia AS (SELECT (CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')::date AS data_referencia)
SELECT 433 AS codigo_sgs,g.periodo,'% no periodo'::text AS unidade,g.observacoes,
       CASE WHEN (periodo+INTERVAL '1 month')::date<=r.data_referencia THEN acumulado END AS variacao,
       r.data_referencia, (periodo+INTERVAL '1 month')::date>r.data_referencia AS parcial,
       observacoes=12 AND meses=12 AND (periodo+INTERVAL '1 month')::date<=r.data_referencia AS completo,
       CASE WHEN (periodo+INTERVAL '1 month')::date>r.data_referencia THEN 'PERIODO_EM_ANDAMENTO'
            WHEN observacoes<>12 OR meses<>12 THEN 'MESES_AUSENTES' END AS motivo
FROM grupos g CROSS JOIN referencia r
WITH NO DATA;
CREATE UNIQUE INDEX uq_mv_ipca_12m ON mart.mv_ipca_12m(periodo);
GRANT SELECT ON mart.mv_serie_mensal,mart.mv_serie_anual,mart.mv_ipca_12m TO api_leitura;
