# Execução local M2 — 19/11/2026

Atualização 23/11/2026: entrega técnica M2 concluída, esquema0010, 588 testes/95,80%,15 módulos críticos>=95%, demonstração125,359 s. Ver [aceite técnico](aceite-tecnico-m2.md) para evidências e ressalvas herdadas. As seções de 19/11 abaixo registram a evolução da entrega.

M2 continua em validação. M3 e disponibilização no GitHub estão adiados.
Código próprio em português-BR, preservando os contratos de bibliotecas.

## Dados e integridade

Migração `0007` aplicada após backup `backups/antes_m2_20261119_155820.dump`.
Os 4.335 fatos BCB foram preservados. Relatório privado:
`dados/descoberta/migracao_m2_20261119_155820.json`.

Primeira coleta oficial IBGE: dez manifestos, 5 regiões, 27 UFs,
5.571 municípios e 27.855 registros populacionais.

| Ano | Municípios | Valores disponíveis | Subtotal disponível |
|---|---:|---:|---:|
| 2020 | 5.571 | 5.570 | 211.755.692 |
| 2021 | 5.571 | 5.570 | 213.317.639 |
| 2024 | 5.571 | 5.570 | 212.583.750 |
| 2025 | 5.571 | 5.571 | 213.421.037 |
| 2026 | 5.571 | 5.571 | 214.211.951 |

Nos três primeiros anos, Boa Esperança do Norte tem marcador `...`; o total
nacional é `null` com `completo=false`. Subtotal não é apresentado como total.
2022/2023 não estão disponíveis nessa série de estimativas; não misturar censo.
Associação territorial atual na coleta, sem alegação de malha histórica.

Replay: zero inserções, zero alterações, 27.855 inalterados; checksum de todos
os campos dos fatos preservado. Publicação subsequente: `IGNORADA/JA_PUBLICADA`,
core/gold 1. Evidência: `dados/descoberta/execucao_ibge_m2_20261119.json`.

## Operação

Coleta oficial completa, carga e publicação com papéis separados:

```powershell
uv run --frozen python scripts/executar_ibge_local.py
```

Esse comando acessa a fonte oficial. Falha de coleta impede carga; falha de carga
impede publicação. Bronze persistido antes de interpretar JSON. Orçamento de
coleta cooperativo de 90 segundos entre blocos; leitura bloqueada pode acrescentar
até 30 segundos, além do tempo de persistência.

Após preparar `.env.monitoramento` e `.cache/redis/redis.conf` privados:

```powershell
docker compose --env-file .env.banco --env-file .env.monitoramento -f compose.yaml -f compose.monitoramento.yaml --profile monitoramento up -d --build api_local cache prometheus grafana
```

API: http://127.0.0.1:8001/docs; Prometheus: http://127.0.0.1:9090;
Grafana: http://127.0.0.1:3000. Login Grafana: `administrador`; senha no arquivo
privado, chave `SENHA_GRAFANA`. Não copiar credenciais para documentação pública.

Dez consultas HTTP, incluindo probes, BCB, IBGE e métricas, retornaram 200.
Prometheus: alvos `api_local` e `prometheus_local` saudáveis. Grafana: três painéis
provisionados. Redis autenticado respondeu PING e armazenou sete chaves.
Evidência: `dados/descoberta/monitoramento_m2_20261119.json`.

## Verificação e pendências

523 testes passaram após integrar as agendas IBGE, cobertura global 94,32%; Ruff
aprovado e mypy em 55 módulos. Log `.cache/verificacao_agendamento_ibge_final.log`.
Testes com amostras/mocks e banco exclusivo
`etl_testes`, sem APIs externas.

Bandit foi iniciado novamente, mas não terminou durante esta validação e suas
execuções duplicadas foram interrompidas. Não considerar a análise de segurança
estática atual aprovada; investigar o tempo de execução antes do aceite final.

Restauração BCB/IBGE validada em banco isolado: 24 tabelas/MVs e 25 consultas API,
com comparação de catálogo, permissões e origem preservada. Procedimento e
limites em [recuperação local M2](recuperacao-local-m2.md).

Benchmark sintético inicial de um milhão concluído em banco isolado: p95 1.093,60 ms
sem cache (meta não atingida), 108,58 ms com cache (meta atingida), zero erros.
Dados e origem preservados; Redis temporário removido. Ver
[resultados M2](desempenho/2026-11-19-m2-local.md).

Após a investigação, a consulta individual passou a filtrar o código no SQL.
Nova medição: p95 **158,75 ms sem cache** e **126,87 ms com cache**, metas
atingidas, zero erros e origem preservada. API local reconstruída e dez sondagens
HTTP aprovadas, com dois alvos Prometheus saudáveis. Detalhes em
[otimização sem cache](desempenho/2026-11-19-otimizacao-sem-cache.md).

MinIO/S3 validado: bucket privado versionado, usuário restrito, colisões/checksums
e permissões reais conferidos; replay de trinta objetos/dez manifestos confirmou
27.855 registros inalterados no clone. Persistência após reinício e
reprovisionamento conferida. Ver [armazenamento S3 local](armazenamento-s3-local.md).

Agendas IBGE ativas no Prefect local; incremental real e recuperação de publicação
concluídos, com auditoria e descarte seguro de agendas vencidas.
Ver [operação IBGE](orquestracao-ibge-local.md).

Pendências M2: instrumentação complementar, demonstração cronometrada e
reconciliação do checklist geral.

Alerta real `APILocalIndisponivel`: parada controlada somente da API demonstrativa
da porta 8001; `firing` em 19/11/2026 às 16:05:09 UTC, resolvido às 16:05:40 UTC
após reinício automático pelo bloco `finally` do ensaio. PostgreSQL preservado.
Evidência: `dados/descoberta/alerta_m2_20261119.json`. `promtool check rules` aprovou
quatro regras e `promtool test rules` passou. Auditoria dos pacotes instalados
com `pip-audit --skip-editable --timeout 10`: nenhuma vulnerabilidade conhecida;
o pacote próprio editável não é consultado como dependência publicada.

Limitações de licença/calendário BCB em `homologacao-bcb-m1.md`. Não declarar
todos os critérios M1/M2 concluídos enquanto houver pendências.

## Instrumentação por fase

Métricas de duração média histórica, quantidade concluída e última conclusão
BCB/IBGE integradas; 525 testes, cobertura 94,34%, Ruff e mypy aprovados.
API/Prometheus/Grafana validados com onze grupos de contagens comparados ao SQL.
Ver [monitoramento de fases](monitoramento-fases-m2.md) para evidências e pendências.
