-- Descoberta confirmada independe da carga; timestamps apenas no formato UTC do produtor.
CREATE OR REPLACE VIEW ops.v_monitoramento_ibge_api AS
SELECT
 (SELECT max(parametros->>'origem_territorial') FROM ops.execucao
 WHERE modo='carga_ibge' AND situacao='SUCESSO'
 AND jsonb_typeof(parametros->'origem_territorial')='string'
 AND parametros->>'origem_territorial' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?[+]00:00$') AS ultima_localidades,
 (SELECT max(parametros->>'consulta_periodos_em') FROM ops.execucao
 WHERE modo='pipeline_ibge'
 AND jsonb_typeof(parametros->'consulta_periodos_em')='string'
 AND parametros->>'consulta_periodos_em' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]{1,6})?[+]00:00$')
 AS ultima_consulta_populacao,
 (SELECT max(ano::integer) FROM ops.execucao e
 CROSS JOIN LATERAL jsonb_array_elements_text(
 CASE WHEN jsonb_typeof(e.parametros->'anos_disponiveis')='array'
 THEN e.parametros->'anos_disponiveis' ELSE '[]'::jsonb END) AS periodos(ano)
 WHERE e.modo='pipeline_ibge'
 AND ano ~ '^[0-9]{4}$' AND ano >= '2020'
 AND ano <= extract(year FROM CURRENT_DATE)::text) AS ultimo_ano_descoberto,
 (SELECT max(ano) FROM core.fato_populacao WHERE indicador_id=1) AS ultimo_ano_carregado;
