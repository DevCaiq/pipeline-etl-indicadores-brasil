# Coleta incremental e reconciliação BCB

A atualização reutiliza a coleta bronze, a validação e a carga idempotente. Planeja janelas anuais, confirma cada uma antes de seguir e interrompe a série na primeira falha. Outras séries são avaliadas independentemente; o mesmo cliente HTTP mantém espaçamento e eventuais esperas impostas pela fonte.

## Comandos locais

Abra Docker Desktop e inicie o PostgreSQL conforme [guia do banco](banco-de-dados.md). Antes de executar, veja as janelas sem consultar a API nem escrever no banco:

```powershell
uv run --frozen pipeline-etl coletar bcb --modo incremental --planejar --credenciais-locais .env.banco
uv run --frozen pipeline-etl coletar bcb --modo reconciliacao --planejar --credenciais-locais .env.banco
```

Sem checkpoint, o incremental retorna SEM_CHECKPOINT para a série. A amostra local começa em 02/01/2020 e não comprova a janela inicial desde 01/01; por isso não inicializa esse checkpoint. A carga histórica explícita inicial pode ser planejada e depois executada:

```powershell
uv run --frozen pipeline-etl coletar bcb --carregar --serie 432 --inicio 2020-01-01 --fim 2026-11-18 --planejar --credenciais-locais .env.banco
uv run --frozen pipeline-etl coletar bcb --carregar --serie 432 --inicio 2020-01-01 --fim 2026-11-18 --credenciais-locais .env.banco
```

O fim acima é um exemplo datado; use a data desejada, até hoje em São Paulo. Sem --planejar, o comando consulta o BCB e carrega cada janela aprovada. --carregar equivale à carga-historica com promoção por janela; não combinar com --validar. O comando antigo sem --carregar continua salvando somente bronze; --validar continua validando sem promover.

Depois da carga histórica confirmada:

```powershell
uv run --frozen pipeline-etl coletar bcb --modo incremental --credenciais-locais .env.banco
uv run --frozen pipeline-etl coletar bcb --modo reconciliacao --credenciais-locais .env.banco
```

Esses dois modos já validam e carregam. Não aceitam --inicio/--fim ou --validar: suas datas são calculadas. --serie pode ser repetido para selecionar um subconjunto; sem essa opção, usa SERIES_BCB. URL_BANCO_PROCESSAMENTO é alternativa ao arquivo local explícito, usando o papel processamento.

## Regras de planejamento

| Modo | Início | Fim |
|---|---|---|
| incremental, séries 432 e 1 | Última observação confirmada menos 30 dias, limitado a 01/01/2020 | Hoje em America/Sao_Paulo |
| incremental, série 433 | Primeiro dia do mês da última observação menos 24 meses de calendário, limitado a 01/01/2020 | Hoje em America/Sao_Paulo |
| reconciliacao | 01/01/2020 | Hoje em America/Sao_Paulo |
| carga-historica --carregar | --inicio explícito, desde 2020 | --fim explícito, até hoje |

Recuo de meses não é aproximado por um número de dias. O coletor acrescenta o apoio IPCA de fevereiro a dezembro de 2019 quando a primeira janela começa em 01/01/2020. Esse apoio não altera o recorte público de 2020+. Não cria observações para datas ausentes.

O marco precisa satisfazer 2020 <= ultima_observacao <= fim_coberto <= hoje. Ausência ou inconsistência bloqueia o incremental, sem iniciar coleta ou gerar uma execução bem-sucedida. O checkpoint continua sendo calculado na mesma transação da carga, pela cobertura contígua de lotes confirmados. Uma carga fora de ordem não salta um intervalo ainda não confirmado.

Reconciliação revisita todo o recorte para detectar revisões além da janela incremental. A recomendação mensal do plano é uma rotina operacional futura; não há agendador nesta entrega. A máquina e os processos devem estar ativos quando os comandos forem executados.

## Auditoria, resultado e recuperação

Cada série tem uma execução pai de modo atualizacao_bcb, com modo solicitado, plano de janelas e resultados. Antes de HTTP, cada janela recebe uma execução filha de coleta_atualizacao com pai_id. Manifesto, coleta_id e carga_id relacionam transporte, validação e promoção; a carga mantém sua própria validação_id. Resultado de coleta SUCESSO significa bronze salvo, não qualidade ou carga aprovadas.

A situação da série é SUCESSO se todas as janelas forem confirmadas, PARCIAL se algumas foram confirmadas antes de uma falha prevista, ou FALHA se nenhuma foi confirmada. O resultado de cada carga e seus avisos, inclusive desaparecimento de registros, aparecem no resumo. Janelas seguintes não são consultadas após falha. A CLI continua avaliando as outras séries, sem tratá-las como uma transação global.

Saída JSON em stdout tem situacao e atualizacoes. Prévia aprovada usa PLANEJADA, sem execucao_id. Uma série sem checkpoint usa IGNORADA/SEM_CHECKPOINT; o agregado pode ser FALHA ou PARCIAL, conforme as demais séries. Retorno 0 significa sucesso ou prévia aprovada; 1 indica bloqueio, falha ou resultado parcial; 2 indica credenciais inválidas/ausentes. Combinações inválidas de argumentos retornam 2 antes da operação.

Depois de falha, repetir o comando é seguro para fatos iguais: a carga preserva valores e metadados. Incremental recalcula a janela com o checkpoint confirmado; carga histórica explícita pode retomar pelo recorte informado. Histórico confirmado permanece, mesmo quando o comando termina com falha. Se houver falha técnica depois de promover uma janela, o pai é marcado FALHA com os resultados já conhecidos; isso não desfaz transações anteriormente confirmadas.

Se o banco continuar indisponível, registrar a falha pode falhar também: conferir execuções EM_EXECUCAO e manifestos preservados após restabelecer o serviço. Não presumir sucesso nem apagar bronze. Retry-After longo interrompe a tentativa e registra proxima_tentativa_em na coleta, sem insistir imediatamente. Esperar a liberação da fonte antes de executar novamente.

Resposta vazia, qualidade parcial e alteração de esquema continuam bloqueadas conservadoramente. A homologação de calendários é pendente; uma janela curta de feriado ou mês sem publicação pode exigir investigação e repetição com um recorte adequado. Nenhuma data é preenchida artificialmente para avançar checkpoint. Nenhuma observação desaparecida é excluída automaticamente.

## Evidências locais — 18/11/2026

217 testes passaram, com cobertura global 95,72%, planejador 100%, executor 96% e CLI de atualização 100%. A suíte usa HTTP simulado e PostgreSQL exclusivo etl_testes: testa falha entre anos, retomada preservando fatos e metadados, recuos, permissões, banco antes de HTTP e indisponibilidade de auditoria. A revisão estática independente não apontou falhas importantes/críticas.

No banco principal, as prévias das três séries foram executadas com HTTP explicitamente bloqueado. Incremental retornou SEM_CHECKPOINT para todas; reconciliação retornou PLANEJADA para as três. Comparação antes/depois confirmou cinco fatos com valores e metadados idênticos, mesmos lotes, auditoria, marcos e versões. Relatório local ignorado pelo Git: dados/descoberta/sondagem_incremental_bcb.json.

Não houve nova migração: esquema permanece na revisão 0003. O histórico completo desde 2020 ainda não foi baixado; a comprovação da execução completa desta etapa usa fixtures e banco de testes. Indicadores, publicação gold, API, orquestração e replay isolado permanecem para as próximas entregas.

Atualização posterior: indicadores BCB e publicação gold local foram implementados na revisão0004; ver [guia de publicação](indicadores-e-publicacao.md). O histórico completo continua pendente.
