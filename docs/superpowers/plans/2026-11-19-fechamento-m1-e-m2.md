# Fechamento M1 e execução M2 local

Autorização: continuar M1/M2; M3 adiado em 19/11/2026. Nenhum GitHub, nuvem ou recurso externo publicado. CI remoto permanece adiado por decisão do responsável, sem alegação de aprovação externa.

## M1
- [ ] Auditoria dos critérios/evidências e homologações finais de fonte/licença/resposta semdados, com limitações de cobertura explícitas.
- [x] Reprodução em cópia de fonte limpa, ambientes/credenciais/container/volume próprios; instalar por lock, aplicar migrações, conferir seeds/probes/API e suíte com banco independente.
- [x] Ensaiar refresh falho/recuperação em banco isolado e consolidar runbook; preservar produção e operação Prefect.
- [x] Reconciliar checklist com evidência e documentar a exceção CIremoto adiado.

## M2
- [x] Homologar IBGE Localidades e população6579/9324 e arquivar amostras oficiais; só depois implementar conector/contratos.
- [x] Modelos/bronze/qualidade/carga idempotente/cobertura/publicação/API IBGE e testes offline/integrados.
- [x] Redis opcional com fallback/gerações/proteção de concorrência/ETag e testes.
- [x] Contrato filesystem/S3 e verificação local do adapter; MinIO opcional.
- [x] Métricas/exporter estável, três painéis e alerta local demonstrado.
- [x] Benchmark M2 sintéticoisolado1milhão, backup/restore e demonstração local reproduzível.

Decisão: avançar etapas dependentes só após evidências correspondentes; preservar app/bronze/fatos da produção. Auditoria e homologação podem ser feitas em paralelo sem alterações compartilhadas. Usar unidades pequenas de plano/testes; não declararM1/M2completos com checklist pendente.

## Registro de retomada — 19/11/2026

- Reprodução M1: `dados/descoberta/reproducao_m1_20261119_040532.json`;
  332 testes, ambiente novo e sete verificações HTTP. Instalação frozen com rede,
  pois o cache local não continha todas as dependências.
- Refresh falho/recuperação M1 executado somente em clone:
  `dados/descoberta/falha_refresh_20261119_040950.json`.
  Runbook/checklist final ainda precisa ser reconciliado.
- Fontes e limitações: `docs/homologacao-bcb-m1.md` e
  `docs/homologacao-ibge-m2.md`. Licença específica SGS433 e calendário histórico
  permanecem sem confirmação suficiente; não declarar cobertura completa.
- API IBGE e `/metrics` integrados à fábrica. Paginação, busca literal, marcadores
  ausentes, totais incompletos e geração dos cursores conferidos no PostgreSQL
  exclusivo `etl_testes`. Exemplos OpenAPI corrigidos após regressão da suíte.
- Cache BCB valida validade do cursor antes de consultar Redis. Proveniência IBGE
  compara cada recurso territorial separadamente, incluindo recoletas iguais.
- Última suíte anterior à inclusão do coordenador IBGE: 458 testes aprovados;
  Ruff aprovado e mypy em 53 módulos. Coordenador: dois testes adicionais aprovados.
  Reexecutar suíte após as próximas alterações antes de fechar aceite.
- Backup e migração local 0007: `dados/descoberta/migracao_m2_20261119_155820.json`;
  4.335 fatos BCB preservados. Backup privado em `backups/`.
- Decisão operacional: orçamento HTTP IBGE de 90 segundos é cooperativo entre
  blocos, com timeout de leitura até 30 segundos; persistência tem custo adicional.
  Não documentar esse orçamento como prazo absoluto.
- Serviços Redis/Prometheus/Grafana ativos em loopback e primeira coleta IBGE oficial confirmada:
  5.571 municípios, 27.855 registros, cinco anos; replay preservou metadados.
  Dez sondagens HTTP passaram; dois alvos Prometheus saudáveis e três painéis provisionados.
  Evidências em `docs/execucao-local-m2.md`; suíte atual 460 testes, 94,75% de cobertura.
  `promtool check rules` e `promtool test rules` aprovados. Alerta real
  `APILocalIndisponivel` firing/resolvido confirmado em
  `dados/descoberta/alerta_m2_20261119.json`; API reiniciada ao final.
  Benchmark M2, operação agendada IBGE e adapter S3 real
  permanecem pendentes até evidência registrada.

## Próxima etapa executada — restauração M2

- [x] Backup novo com BCB/IBGE e restauração em banco exclusivo, sem reutilizar destinos.
- [x] Comparar dados e catálogo completo, incluindo gatilhos core e sequências.
- [x] Comparar API com papel de leitura e continuidade dos cursores.
- [x] Retratar origem/cópia após sondagens para comprovar ausência de alterações.
- [x] Registrar runbook e limites do ensaio em `docs/recuperacao-local-m2.md`.
- Evidência final revisada: `dados/descoberta/restauracao_m2_20261119_162132_7013d2.json`;
  24 tabelas/MVs, 15 grupos de catálogo, 25 rotas, duas segundas páginas,
  restauração 30,453 segundos; origem e cópia preservadas.
- Decisão: o tempo de assinatura dos tokens pode variar; comparar presença do
  próximo cursor, filtros e dados, além de reutilizar o cursor da origem na cópia.
  Não declarar igualdade byte a byte de tokens com instantes de assinatura distintos.
- Revisão independente: detectou ausência do tamanho completo de tipos SQL no
  catálogo e falta de exigência explícita de segunda página. Regressões
  reproduzidas e corrigidas: `test_retrato_detecta_alteracao_do_tamanho_varchar`
  e `test_sondagem_nao_declara_sucesso_sem_exercitar_cursor`.
  Nove testes direcionados passaram. A versão revisada registra hash da segunda
  página e exige pelo menos uma continuidade comprovada; novo ensaio aprovado.
- Verificação final da etapa: 469 testes, 94,75% de cobertura, Ruff e formatação
  dos três arquivos Python novos aprovados, mypy em 54 módulos aprovado.
  Log `.cache/verificacao_restauracao_m2_final.log`. Próxima pendência: benchmark M2.

## Benchmark M2 — concluído, meta sem cache pendente

- Banco novo com 400 séries simuladas e 2.500 datas por série; um milhão de
  observações, semente 20261119. Dados reais e amostras oficiais preservados.
- Reutiliza mistura e estatística HTTP M1, adicionando contadores de retornos
  cacheados versus cálculos delimitados às barreiras da janela medida.
- Redis exclusivo identificado por rótulo aleatório; limpeza é confirmada e
  falhas de limpeza ficam registradas sem suprimir o relatório.
- Revisão apontou e corrigimos: limpeza após criação inconclusiva, evidência de
  cache durante a medição e registro real dos índices/versão PostgreSQL/código.
  Testes novos dessas proteções reproduziram a ausência e passaram após implementação.
- Protocolo: `docs/desempenho/protocolo-m2.md`. Execução preliminar não é o
  resultado homologado; resultados finais dependem da versão revisada.
- Decisão: medir uma série de 2.500 registros em banco de um milhão de fatos;
  não alegar paginação de um milhão de registros por série, saturação ou cobertura
  de todas as rotas. Metas não atingidas serão relatadas sem ajustar o dataset.
- Antes da medição final: 478 testes passaram, cobertura 94,75%, Ruff e mypy
  aprovados. A suíte terminou antes de iniciar o benchmark homologado;
  log `.cache/verificacao_benchmark_m2.log`.
- Execução final: `dados/descoberta/desempenho_m2_20261119_165126_db457c.json`.
  Um milhão de fatos confirmados; 23 tabelas/MVs e origem preservadas.
  p95 sem cache 1.093,60 ms, meta 500 ms não atingida; com cache 108,58 ms,
  meta 250 ms atingida. Zero erros. 8.754 respostas cacheadas comprovadas na
  janela medida; remoção do Redis exclusivo confirmada.
- Evidências e limites: `docs/desempenho/2026-11-19-m2-local.md`.
  Pendência de desempenho: diagnosticar latência sem cache; não declarar meta
  atendida nem atribuir causa definitiva apenas aos planos de paginação.

## Melhoria da latência sem cache — investigação e execução

- Diagnóstico com papel API, somente leitura no banco sintético do benchmark:
  consulta integral do catálogo retornou 400 séries, mediana de 214,985 ms;
  consulta restrita retornou uma série, mediana de 2,141 ms (cinco execuções).
  Resolução original no repositório levou 215,390 ms.
  Evidência: `dados/descoberta/diagnostico_latencia_sem_cache_20261119.json`, com planos.
- Implementação: resolução individual usa igualdade parametrizada no SQL; catálogo
  completo mantém semântica. Nenhum índice, migração, grant ou cache novo.
- Quatro casos de regressão (1,432,433,999) reproduziram leitura excessiva e
  passaram após o ajuste. Conferem DTO/cobertura/404 e uma linha (ou zero) lida.
  Trinta testes API/cache passaram, Ruff e mypy aprovados.
- Suíte completa e revisão independente em andamento; só considerar meta de
  desempenho corrigida após novo benchmark com mesma semente/protocolo.
- Plano real confirmou Index Only Scan da chave primária com 2.500 linhas por
  execução: 400 loops na consulta integral, um loop na consulta filtrada;
  blocos compartilhados hit 4.463 versus 10, sem leitura física nessa amostra.
- Resolução no repositório após correção: 3,145 ms na mesma base (medição serial),
  cobertura inalterada. Evidência separada:
  `dados/descoberta/diagnostico_latencia_sem_cache_depois_20261119.json`.
- Revisão independente concluída sem achados concretos de defeito; preservação
  da regra de apoio IPCA 2019 e dos filtros/DTO/snapshot conferida estaticamente.
- Verificação final: 482 testes, cobertura 94,76%, Ruff e mypy aprovados antes
  do benchmark, sem suíte concorrente na medição. Log
  `.cache/verificacao_otimizacao_sem_cache.log`.
- Benchmark corrigido: `dados/descoberta/desempenho_m2_20261119_173111_cf7a54.json`;
  p95 sem cache 158,75 ms, com cache 126,87 ms, ambas metas atendidas em todos
  os cenários, zero erros. Origem e dataset preservados, limpeza Redis confirmada.
  Somente o hash do repositório API mudou entre os fontes registrados.
- Evidência consolidada: `docs/desempenho/2026-11-19-otimizacao-sem-cache.md`.
  API local reconstruída e atualizada; helper conferido na imagem em execução.
  Dez sondagens HTTP 200, dois alvos Prometheus saudáveis e Redis operacional
  conferidos após atualização. Log `.cache/atualizacao_api_otimizada.log`.
- Etapa de investigação/correção concluída; metas locais atendidas, sem concluir
  automaticamente as demais pendências M2 ou iniciar M3.

## Armazenamento S3/MinIO — concluído nesta etapa

- Imagem construída de releases oficiais fixas, bucket privado/versionado,
  credenciais separadas e usuário get/put no prefixo, sem exclusão de versões.
- Colisões, concorrência, checksum, acesso anônimo e fora do prefixo validados
  contra MinIO real. Replay arquivos/S3 em novo clone: 27.855 inalterados,
  core/mart preservados, publicação JA_PUBLICADA.
- Evidência: `dados/descoberta/objetos_s3_20261119_211019_50aeca.json`;
  persistência após reinício/reprovisionamento em
  `dados/descoberta/persistencia_s3_20261119.json`: 32 objetos, uma versão cada.
- Revisão: políticas anteriores de bucket e permissões adicionais/grupos do
  usuário agora são recusados, preservando configurações inesperadas.
  Regressões RED→GREEN e reprovisionamento real aprovados.
- Suíte 506 testes, 94,44% de cobertura, Ruff e mypy 55 módulos aprovados.
  Procedimento e limites em `docs/armazenamento-s3-local.md`.
- Decisão: imutabilidade via contrato IfNoneMatch do adaptador, versionamento e
  conta sem exclusão; não alegar WORM ou backup externo. IBGE aceita S3 opt-in,
  BCB M1 permanece em arquivos. M3 continua adiado.
- Verificações finais: wheel construído com módulo S3 sem credenciais; dez
  sondagens da API/monitoramento retornaram 200. MinIO saudável como usuário
  aplicativo, somente porta 127.0.0.1:9000; arquivo privado ignorado pelo Git.

## Agendamento IBGE — concluído nesta etapa

- Três agendas do plano registradas com America/Sao_Paulo; seis deployments no
  pool global um, servidor/worker Windows Running. S3 opt-in dos deployments,
  mensal busca novos anos e revisa o último; reconciliação busca todos.
- Decisão: rodada semanal Localidades também coleta populações disponíveis,
  preservando o contrato transacional de snapshot/cobertura. Custo: mais consultas
  semanais, sem promoção parcial de dimensões fora do pacote validado.
- Pai pipeline_ibge registra PID/host, referência de armazenamento e manifestos;
  filhos vinculados. Trava 2026112002 independente de BCB; recuperação conservadora
  reutilizada com filtro por domínio, preservando o comportamento BCB.
- Execução real incremental eed7cd3f-6ca6-4110-85b9-35ba5725b292 Completed;
  pai 987d7237-f933-4c14-8001-accd6c5b10b2 SUCESSO, seis manifestos S3,
  5.571 linhas, gold PRONTA core/gold1. Publicação sem coleta pelo worker atualizado
  e 8584333-c628-40f1-a9a3-8e972be62fef também Completed.
- Revisão e regressões: substitutas confirmadas antes de atualizar marco;
  removidos cancelamentos remotos forçados que poderiam atingir rodada já iniciada.
  Decisão: o próprio flow antigo retorna Cancelled antes do subprocesso; filas
  grandes podem levar mais tempo para descartar, sem risco de interromper ETL ativo.
  Simulação SDK real 122eedf4-b3ac-4667-9ad3-5e59c5b40381 Cancelled sem subprocesso.
- Suíte final 523 testes, cobertura 94,32%, Ruff e mypy em 55 módulos aprovados.
  Evidências e limites em `docs/orquestracao-ibge-local.md`; falta instrumentação
  complementar, demonstração cronometrada e reconciliação global de critérios.
  Não declarar M2/M3 globais concluídos.

## Instrumentação das fases — entrega incremental concluída

- Gauges de contagens concluídas, média histórica da duração e última conclusão por fase/fonte/situação, sem migração ou alteração de permissões.
- Dois testes RED→GREEN; suíte 525 testes, cobertura 94,34%, Ruff/formato/mypy e wheel aprovados. Revisão independente sem achados.
- API atualizada isoladamente; oito sondagens 200, onze grupos de contagens comparados ao SQL, onze séries por família nova no Prometheus e seis gráficos no painel pipeline Grafana após recarga do provisionamento.
- Decisão: gauges representam auditoria retida; média histórica não é p95. Pais e filhos não devem ser somados como rodadas únicas.
- Ainda faltam contagens detalhadas/rejeições/retries e cobertura/frescor IBGE, demonstração e checklist. Evidências: docs/monitoramento-fases-m2.md. M2 não declarado completo, M3/GitHub adiados.


## Consolidação final — 23/11/2026

M2 técnico local verificado:588 testes/95,80%,15 módulos críticos>=95%, checks,
segurança, build e imagem aprovados; demo125,359 s com origem preservada.
Monitoramento SQL/API/Prometheus/Grafana, Redis real e tarefas locais conferidos.
Runbook e critérios reconciliados em docs/aceite-tecnico-m2.md e docs/runbook.md.
Permanece sem marcação global a homologação integral de fonte M1 (licença433 e
calendários históricos), expressa no DoD herdado do M2. Não declarar essa evidência
obtida nem CI remoto aprovado. M3/GitHub continuam adiados.


## Conferência documental e histórica — 23/11/2026

Nova consulta oficial do calendário foi arquivada com URL/parâmetros/UTC/SHA256;
2450 itens,96 referências IPCA 2019–2026. Recorte já divulgado:93 esperadas e93 carregadas,
82 públicas e11apoio. Sem faltas/inesperadas. Selic 2519 datas civis contínuas. Dólar
1728 observações e68 dias de semana sem observação a classificar por calendário próprio.
PDA IBGE2024–2025 arquivado HTTP 200; termos BCB confirmados por extração indexada,
GET direto continuou shell JavaScript. Licença nominal não inventada. Evidências em
`docs/conferencia-fontes-2026-11-23.md`. Nenhuma alteração em aplicativo,fixtures,
calendário empacotado ou banco. Sem GitHub/M3, sem contatos externos.

## Conferência PTAX e encaminhamento documental — 23/11/2026

Histórico do dólar: sete respostas anuais PTAX, 1.728 datas distintas iguais ao banco,
sem faltas/extras. Duplicata de valores idênticos em 23/04/2025 registrada. Calendários
ANBIMA classificam as 68 ausências em dias de semana. Corpos originais, UTC, URL e
hashes arquivados; consulta SQL somente leitura. Evidências em
`docs/conferencia-dolar-2026-11-23.md`. Minuta de esclarecimento BCB/IBGE em
`docs/solicitacao-termos-ipca.md`, não enviada. Confirmação documental específica
IPCA continua aberta; aceite global não marcado. Sem alterações no aplicativo,
banco, fixtures ou política de cobertura da API; sem publicação/GitHub/M3.
