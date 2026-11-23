# Indicadores BCB e publicação gold

A revisão 0004 acrescenta três visões materializadas em mart e uma função NUMERIC versionada. A publicação é local no PostgreSQL; ainda não existe uma API HTTP nesta entrega.

## Publicar

Com Docker Desktop e PostgreSQL ativos, depois de aplicar as migrações:

```powershell
uv run --frozen pipeline-etl publicar --dominio bcb --credenciais-locais .env.banco
```

O comando usa somente a senha do papel publicador. URL_BANCO_PUBLICADOR é alternativa ao arquivo local explícito; não combinar as duas origens. O publicador é proprietário das visões, lê fatos e atualiza apenas as colunas necessárias do estado de publicação. Não recebe UPDATE sobre core.fato_serie. api_leitura pode consultar as MVs, mas não atualizá-las.

O resumo JSON inclui execução, situação, versões, motivo e data_publicacao. Retorno 0 indica publicação concluída ou JA_PUBLICADA; 1 indica falha, trava ocupada ou ausência de geração core; 2 indica credenciais inválidas/ausentes. Repetir o comando no mesmo dia e sem nova geração não regrava gold; o histórico operacional recebe uma nova tentativa.

## Indicadores

| Visão | Série | Conteúdo |
|---|---|---|
| mart.mv_serie_mensal | Selic/dólar | Média simples das observações publicadas, mínimo, máximo e último |
| mart.mv_serie_anual | Selic/dólar | As mesmas estatísticas sobre todas as observações do ano |
| mart.mv_serie_mensal | IPCA | Variação original do mês |
| mart.mv_serie_anual | IPCA | Composição janeiro–dezembro, em % no ano |
| mart.mv_ipca_12m | IPCA | Composição dos 12 meses-calendário até o mês consultado |

A média anual não é a média das médias mensais. Meta Selic permanece em % a.a.; não é composta como rentabilidade. Dólar permanece BRL/USD, sem cotação criada para feriados. IPCA acumulado usa 100 × (produto(1 + taxa/100) − 1), sem logaritmos ou ponto flutuante.

mart.compor_taxas_bcb usa NUMERIC; a referência Python compor_ipca usa Decimal com precisão suficiente para as 12 entradas NUMERIC(24,10). Não há arredondamento intermediário intencional para apresentação. formatar_decimal prepara a fronteira pública futura: seis casas, ROUND_HALF_EVEN e decimal como string. SQL mantém valores numéricos.

Somente períodos desde 2020 aparecem nas MVs. O IPCA 12m de janeiro de 2020 pode usar fevereiro–dezembro de 2019; esse apoio não aparece como um período público anterior a 2020. Não há geração artificial de meses sem observação: a visão 12m tem uma linha para cada mês observado no recorte público.

## Incompletude e referência temporal

Todas as visões informam unidade, observacoes, parcial, completo, motivo e data_referencia. parcial identifica período ainda em andamento na referência temporal da publicação; não prova cobertura histórica.

Para Selic e dólar, completo permanece NULL e motivo é CALENDARIO_NAO_HOMOLOGADO. Estatísticas descrevem as observações disponíveis; mês fechado não significa calendário completo. Para IPCA anual/12m, faltas ou menos de 12 meses distintos/consecutivos retornam variacao=NULL, completo=false e MESES_AUSENTES. Período aberto retorna PERIODO_EM_ANDAMENTO e não produz acumulado anual/12m completo. O IPCA mensal mantém a variação original, com sua sinalização de período aberto.

A referência usa o início da transação PostgreSQL, convertido para America/Sao_Paulo, igual nas três visões. Se a transação atravessar meia-noite, a referência anterior permanece identificada até a próxima execução. data_publicacao registra essa referência, não um timestamp de término. Mesmo sem mudança no core, publicar em outro dia renova a referência e as flags de período.

A futura API/cache deverá considerar (versao_gold, data_publicacao) ao identificar a representação, além de rota e filtros. Comparar somente versao_core/versao_gold não detecta mudança diária de flags temporais. Consumidores também devem verificar se a data de publicação corresponde à referência esperada.

## Atomicidade e recuperação

A publicação usa a mesma advisory lock transacional BCB da carga, com espera de até 30 segundos e conexão reservada durante a transação. As três operações REFRESH MATERIALIZED VIEW e a atualização gold=core/PRONTA são confirmadas juntas. Não há HTTP durante essa operação.

Uma falha reverte o conjunto: core permanece válido, a gold anterior permanece e a versão gold não avança. Uma transação separada registra a falha e mantém PENDENTE quando a versão/data ainda está desatualizada. Essa transação também respeita a trava e não sobrescreve uma publicação mais recente que já recuperou o domínio.

Depois de corrigir a falha, repetir publicar recupera sem baixar a fonte. Se o banco continuar indisponível e nem a auditoria puder ser concluída, a tentativa pode permanecer EM_EXECUCAO; conferir o estado após restabelecer o serviço. Não presumir sucesso pelo término do processo.

A primeira criação usa WITH NO DATA: antes da primeira publicação, as MVs não estão disponíveis para leitura. A futura API precisa conferir estado/geração antes de consultá-las. O refresh atual usa bloqueio normal, podendo aguardar ou bloquear leitores; desempenho/concorrrência com uma API ainda precisam ser medidos.

PRONTA significa que as visões refletem a geração core publicada. Não significa cobertura completa desde 2020 nem presença de todas as séries. Na entrega inicial havia cinco observações Selic e fixtures de IPCA/dólar. O histórico real foi carregado depois, com 351 agregados conferidos; ver [validação histórica](historico-real-m1.md).

## Verificação da entrega — 18/11/2026

242 testes passaram, incluindo downgrade/upgrade no banco etl_testes, cálculos comparados com valores Decimal independentes, falha no segundo refresh, recuperação, trava ocupada, permissões e publicação por papel próprio. Cobertura global 95,99%; indicadores 100%, serviço de publicação 97%, CLI 100%. CI exige pelo menos 95% separadamente nos dois módulos novos.

Regressão observada antes da correção: o IPCA anual herdava a unidade mensal do catálogo. A visão agora expõe % no ano, mantendo a unidade original somente no mês. Revisão independente não encontrou outros problemas importantes/críticos; a referência temporal de transação foi documentada acima.

Backup anterior à revisão 0004: backups/etl_antes_gold_20261118_164423.dump, 30.521 bytes, catálogo pg_restore --list legível. A conferência do catálogo não equivale a um ensaio completo de restauração.

O histórico real completo, calendário oficial homologado, API, IBGE, cache, orquestração e replay isolado permanecem pendentes. Próxima entrega: API FastAPI para consumo de core/gold, com unidades, cobertura, precisão e versões explícitas.


Sondagem no banco principal: publicação4a19d677-29f0-4b05-9326-26774dab7a85 terminou SUCESSO; repetição1cff6fdc-0760-4e58-84b9-1362e488db34 retornou IGNORADA/JA_PUBLICADA. Estado core1/gold1, PRONTA, referência2026-11-18. A visão mensal e a anual têm uma linha Selic cada, com cinco observações; a visão IPCA12m está vazia porque não há IPCA real carregado. Fatos, lotes de origem e instantes foram comparados e preservados. Nenhuma chamada HTTP. Relatório local em dados/descoberta/sondagem_gold_bcb.json, ignorado pelo Git.

A imagem atualizada aplicou a revisão0004 e alembic check não encontrou diferenças. Ruff/formatação, mypy e Bandit passaram; auditoria das dependências sem vulnerabilidades conhecidas. A futura API precisará de acesso seguro ao estado de publicação: nesta entrega api_leitura recebe leitura das MVs, sem acesso geral às tabelas operacionais.

Atualização posterior: a API M1 e seu acesso seguro ao estado de publicação foram implementados nas revisões0005/0006. Ver [guia da API](api.md). O histórico real completo continua pendente.

Estado atualizado: core22/gold22 PRONTA; 248 agregados mensais, 21 anuais e 82 janelas IPCA12m comparadas independentemente com os dados reais.
