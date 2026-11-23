# Monitoramento de fases — M2 local

A instrumentação complementar, métricas de cache e demonstração foram concluídas na etapa seguinte. Ver [monitoramento completo](monitoramento-completo-m2.md) e [aceite técnico](aceite-tecnico-m2.md).

Validação em 19/11/2026. Continuação da instrumentação prevista no plano.

O exporter estável em `/metrics` consulta `ops.v_execucoes_api` com o papel de
leitura, transação somente leitura e timeouts existentes. Não depende de o job
continuar vivo. Não foram criadas migrações, permissões ou tabelas.

| Métrica gauge | Significado |
|---|---|
| pipeline_fase_execucoes | Quantidade de execuções concluídas na auditoria retida |
| pipeline_fase_duracao_media_segundos | Média histórica da duração dessas execuções |
| pipeline_fase_ultima_conclusao_segundos | Instante Unix da última conclusão |

Rótulos: fonte, fase e situação. Lista fechada de fases BCB/IBGE e estados
SUCESSO/PARCIAL/FALHA/IGNORADA; identificadores, parâmetros, mensagens e caminhos
não viram rótulos. Execuções sem término ou com término anterior ao início não
participam dessas métricas. As métricas anteriores permanecem disponíveis.
Falha de qualquer consulta publica somente `pipeline_coleta_disponivel=0` para
esta família de estatísticas operacionais, sem expor resultados parciais ou erro.

São gauges, não counters: retenção da auditoria pode reduzir os valores. Não usar
`rate()` ou `increase()` sobre essas contagens. A média não representa p95 nem a
última execução. Pais e filhos são fases distintas, com tempos sobrepostos;
não somar fases para obter duração ou número de rodadas únicas.

## Consulta local

Grafana: http://127.0.0.1:3000/d/pipeline-pipeline

O painel do pipeline tem seis gráficos, incluindo média histórica, quantidade
concluída e tempo desde a última conclusão por fonte/fase/situação. Os outros
dois dashboards existentes permanecem provisionados.

PromQL para tempo desde o último sucesso:

```promql
time() - pipeline_fase_ultima_conclusao_segundos{situacao="SUCESSO"}
```

Uma fase sem histórico não produz série; ausência não significa zero segundos.
As métricas são calculadas da auditoria SQL retida e sobrevivem ao reinício da
API. Já métricas HTTP e de cache por processo mantêm o comportamento anterior.

Nesta atualização, o arquivo montado no Grafana já tinha seis gráficos, mas o
painel servido ainda tinha três. A recarga explícita do provisionamento resolveu:
`POST http://127.0.0.1:3000/api/admin/provisioning/dashboards/reload`, usando a
conta administrativa local e a senha privada de `.env.monitoramento`. Não incluir
credenciais na linha de comando, documentação pública ou relatórios. Alternativa:
reiniciar somente o serviço Grafana para reler os arquivos provisionados.

## Evidências

- Dois testes novos reproduziram as métricas ausentes e a falta de consulta de
  fases; depois passaram. Sete testes direcionados aprovados.
- Suíte completa: 525 testes, cobertura 94,34%; banco exclusivo `etl_testes`,
  sem APIs externas. Log `.cache/verificacao_metricas_fases_m2.log`.
- Ruff e formatação: 121 arquivos; mypy: 55 módulos; wheel construído.
- Revisão independente estática sem achados concretos.
- API reconstruída e atualizada isoladamente. Oito rotas retornaram HTTP 200.
- Onze grupos exportados tiveram contagens comparadas ao SQL com o papel API.
  Prometheus retornou onze séries de cada métrica nova; Grafana confirmou seis
  gráficos no dashboard do pipeline.
- Relatório privado: `dados/descoberta/instrumentacao_fases_m2_20261119.json`.

Esta entrega cobre duração/resultados por fase. Contagens de linhas, rejeições,
retries persistidos e cobertura/frescor IBGE ainda precisam de complementação.
A demonstração cronometrada e reconciliação dos critérios também permanecem
pendentes. Não declarar M2 completo; M3 e GitHub continuam adiados.
