-- Somente agregações e campos explicitamente selecionados; nenhum JSON bruto público.
CREATE VIEW ops.v_metricas_etapas_api AS
WITH execucoes AS (
 SELECT modo AS fase, situacao, linhas_lidas, linhas_validas, linhas_rejeitadas,
 linhas_duplicadas, linhas_nao_processadas,
 CASE WHEN jsonb_typeof(parametros->'metricas_coleta'->'requisicoes')='number'
 AND parametros->'metricas_coleta'->>'requisicoes' ~ '^[0-9]{1,18}$'
 THEN (parametros->'metricas_coleta'->>'requisicoes')::bigint END AS requisicoes,
 CASE WHEN jsonb_typeof(parametros->'metricas_coleta'->'retentativas')='number'
 AND parametros->'metricas_coleta'->>'retentativas' ~ '^[0-9]{1,18}$'
 THEN (parametros->'metricas_coleta'->>'retentativas')::bigint END AS retentativas
 FROM ops.execucao WHERE finalizado_em IS NOT NULL
 AND situacao IN ('SUCESSO','PARCIAL','FALHA','IGNORADA')
 AND modo IN ('pipeline_bcb','carga_bcb','coleta_validacao','validacao_bronze',
 'coleta_atualizacao','atualizacao_bcb','publicacao_bcb',
 'pipeline_ibge','carga_ibge','publicacao_ibge')
)
SELECT CASE WHEN fase IN ('pipeline_ibge','carga_ibge','publicacao_ibge')
 THEN 'ibge' ELSE 'bcb' END AS fonte, fase, situacao,
 sum(linhas_lidas) AS linhas_lidas, sum(linhas_validas) AS linhas_validas,
 sum(linhas_rejeitadas) AS linhas_rejeitadas, sum(linhas_duplicadas) AS linhas_duplicadas,
 sum(linhas_nao_processadas) AS linhas_nao_processadas,
 sum(requisicoes) FILTER (WHERE retentativas IS NOT NULL) AS requisicoes,
 sum(retentativas) FILTER (WHERE requisicoes IS NOT NULL) AS retentativas,
 count(*) FILTER (WHERE requisicoes IS NOT NULL AND retentativas IS NOT NULL)
 AS execucoes_instrumentadas
FROM execucoes GROUP BY fase,situacao;

CREATE VIEW ops.v_monitoramento_ibge_api AS
SELECT
 (SELECT max(parametros->>'origem_territorial') FROM ops.execucao
 WHERE modo='carga_ibge' AND situacao='SUCESSO') AS ultima_localidades,
 (SELECT max(parametros->>'consulta_periodos_em') FROM ops.execucao
 WHERE modo='pipeline_ibge' AND situacao IN ('SUCESSO','PARCIAL'))
 AS ultima_consulta_populacao,
 (SELECT max(ano::integer) FROM ops.execucao e
 CROSS JOIN LATERAL jsonb_array_elements_text(
 CASE WHEN jsonb_typeof(e.parametros->'anos_disponiveis')='array'
 THEN e.parametros->'anos_disponiveis' ELSE '[]'::jsonb END) AS periodos(ano)
 WHERE e.modo='pipeline_ibge' AND e.situacao IN ('SUCESSO','PARCIAL')
 AND ano ~ '^[0-9]{4}$' AND ano >= '2020'
 AND ano <= extract(year FROM CURRENT_DATE)::text) AS ultimo_ano_descoberto,
 (SELECT max(ano) FROM core.fato_populacao WHERE indicador_id=1) AS ultimo_ano_carregado;

CREATE VIEW ops.v_cobertura_ibge_api AS
SELECT ano,municipios_esperados,municipios_recebidos,municipios_disponiveis,
 municipios_indisponiveis,completo FROM mart.mv_populacao_brasil
WHERE indicador_id=1 AND ano BETWEEN 2020 AND extract(year FROM CURRENT_DATE);

REVOKE ALL ON ops.v_metricas_etapas_api,ops.v_monitoramento_ibge_api,
 ops.v_cobertura_ibge_api FROM PUBLIC,processamento;
GRANT SELECT ON ops.v_metricas_etapas_api,ops.v_monitoramento_ibge_api,
 ops.v_cobertura_ibge_api TO api_leitura;
