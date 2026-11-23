# Investigação e melhoria da latência sem cache

## Causa confirmada

O benchmark anterior mediu p95 de 1.093,60 ms sem cache, acima da meta local de
500 ms. A resolução de uma série chamava o catálogo completo, calculava a
cobertura das 400 séries e procurava o código em Python. Esse caminho era
executado novamente nas consultas de observações e agregados sem cache.

Diagnóstico somente leitura no mesmo banco sintético de um milhão de fatos,
com papel `api_leitura`, cinco execuções por consulta:

| Consulta | Séries retornadas | Mediana SQL + leitura das linhas |
|---|---:|---:|
| Catálogo integral | 400 | 214,985 ms |
| Série filtrada por código | 1 | 2,141 ms |

O plano executou Index Only Scan em `pk_fato_serie`, 2.500 registros por loop:
400 loops no catálogo integral, um na consulta filtrada. Shared Hit Blocks:
4.463 versus 10; zero Shared Read Blocks nessa amostra. O custo vinha do volume
de agregações solicitado pela aplicação; o índice existente já servia à consulta.

Evidência com planos:
`dados/descoberta/diagnostico_latencia_sem_cache_20261119.json`.

Para reproduzir o diagnóstico com papel de leitura no banco sintético:

```sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT s.codigo_sgs AS codigo, s.nome, s.periodicidade, s.unidade,
       s.inicio_publico, f.inicio, f.fim, f.observacoes
FROM core.dim_serie s
JOIN ops.v_frescor_api f USING (codigo_sgs)
WHERE s.codigo_sgs = 432
ORDER BY s.codigo_sgs;
```

Comparar com a mesma consulta sem a cláusula WHERE para observar o trabalho do
catálogo integral. Na aplicação, o código é parâmetro vinculado; o literal acima
serve apenas ao diagnóstico manual no dataset simulado.

## Alteração

`RepositorioLeitura.serie` consulta somente o código solicitado, com parâmetro
SQL vinculado. O helper compartilhado continua montando os mesmos DTOs e regras
de cobertura; `catalogo` permanece sem filtro para a rota de listagem completa.
Sem novos índices, migrações, permissões ou dependência de cache.

São preservados o snapshot de leitura, série conhecida sem observações,
404 para código inexistente, suporte IPCA de 2019 excluído da cobertura pública,
valores e contratos de resposta, ETag e validação de cursores.

A resolução completa pelo repositório caiu de 215,390 ms para 3,145 ms no
diagnóstico serial, com a mesma cobertura. Esse tempo não é p95 HTTP.
Evidência após correção:
`dados/descoberta/diagnostico_latencia_sem_cache_depois_20261119.json`.

## Validação

Quatro regressões reproduziram a leitura de todas as séries e passaram após o
ajuste. Conferem igualdade com o DTO do catálogo e uma linha lida para código
existente, zero para inexistente. Os testes de API/cache também passaram.
Revisão independente não encontrou defeito concreto na alteração.

Suíte completa: 482 testes aprovados, cobertura 94,76%, Ruff e mypy aprovados.
Log `.cache/verificacao_otimizacao_sem_cache.log`.

## Benchmark após a correção

Mesma semente, esquema, índices e protocolo: banco novo, um milhão de fatos,
30 segundos de aquecimento, 60 segundos de medição, dez clientes e cem itens
por página. Entre os hashes de código/configuração registrados, somente
`src/pipeline_etl/api/repositorio.py` mudou em relação à medição anterior.

| Métrica | Antes, sem cache | Depois, sem cache | Depois, com cache |
|---|---:|---:|---:|
| Pedidos medidos | 788 | 5.606 | 8.123 |
| Vazão | 13,03 req/s | 93,35 req/s | 135,29 req/s |
| p50 | 747,17 ms | 101,37 ms | 65,60 ms |
| p95 | 1.093,60 ms | **158,75 ms** | **126,87 ms** |
| p99 | 1.389,35 ms | 196,60 ms | 206,45 ms |
| Erros HTTP/transporte/validação básica | 0 | 0 | 0 |
| Meta p95 | 500 ms: não atingida | 500 ms: **atingida** | 250 ms: **atingida** |

Redução observada de 85,48% no p95 sem cache. A modalidade sem cache comprovou
5.606 cálculos e zero retornos cacheados durante a medição; com cache, 8.123
retornos cacheados e zero cálculos. Não houve uso de Redis para produzir o ganho
da primeira modalidade. As consultas de autoridade no banco permanecem nas duas.

| Cenário | p95 depois, sem cache | p95 depois, com cache |
|---|---:|---:|
| Primeira página | 148,28 ms | 113,62 ms |
| Página central | 146,24 ms | 124,95 ms |
| Última página | 151,56 ms | 118,79 ms |
| Agregados mensais | 179,33 ms | 147,84 ms |

Relatório final:
`dados/descoberta/desempenho_m2_20261119_173111_cf7a54.json`.
Banco isolado `etl_benchmark_m2_20261119_173111_cf7a54`, log
`.cache/benchmark_m2_otimizado.log`. Origem real e dados sintéticos preservados;
remoção do Redis temporário confirmada. As metas foram atendidas também em cada
cenário. O [protocolo M2](protocolo-m2.md) e suas limitações continuam aplicáveis:
execuções sequenciais, buffers aquecidos e mistura fixa não são SLA nem teste
de saturação. A listagem integral continua calculando a cobertura do catálogo
inteiro por finalidade; a alteração reduz o custo das consultas individuais.

O container local da API foi reconstruído e iniciado com a correção. A presença
do novo helper foi conferida na imagem em execução. Dez sondagens HTTP
(BCB/IBGE, probes e métricas) retornaram 200; dois alvos Prometheus saudáveis,
três painéis Grafana provisionados e Redis operacional respondendo.
Evidências locais: `.cache/atualizacao_api_otimizada.log` e
`dados/descoberta/monitoramento_m2_20261119.json` (verificação de 17:37:48 UTC).
M3 e disponibilização no GitHub permanecem adiados.
