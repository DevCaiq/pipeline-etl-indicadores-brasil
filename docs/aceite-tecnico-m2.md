# Aceite técnico local M2 — 23/11/2026

Decisão posterior do responsável em 23/11/2026: seguir sem solicitação de autorização individual para o protótipo local. A espera por resposta deixa de bloquear o aceite local; atribuição e limitações dos termos permanecem. [Decisão de escopo](decisao-aceite-local-m1-m2.md). A minuta não foi enviada e o conteúdo anterior abaixo é histórico.

Atualização posterior de 23/11/2026: a pendência de datas do dólar foi resolvida no recorte carregado: 1.728/1.728 datas na API oficial PTAX e 68 ausências classificadas pelos calendários ANBIMA. Ver [conferência do dólar](conferencia-dolar-2026-11-23.md). A confirmação dos termos específicos aplicáveis ao IPCA continua aberta; [solicitação preparada, não enviada](solicitacao-termos-ipca.md). O conteúdo anterior abaixo preserva o estado histórico.

**A implementação e as verificações técnicas locais do M2 estão concluídas.**
O aceite integral herdado do M1 continua com ressalvas de fontes: licença específica
SGS433 e completude histórica oficial não foram integralmente homologadas.
As evidências ausentes permanecem explícitas no plano. CI no GitHub e M3 continuam adiados conforme autorização.

## Entrega verificada

| Critério técnico | Evidência |
|---|---|
| IBGE: localidades/estimativas, lacunas e linhagem | Homologação oficial arquivada; 27.855 fatos, 5 anos; marcadores preservados, 2022/2023 ausentes |
| Carga idempotente, rollback e domínios independentes | Suíte PostgreSQL exclusiva; replay de 79 cargas BCB e 10 manifestos IBGE sem alterar core/gold antes da republicação |
| API somente leitura, paginação e ETag | 25 rotas comparadas origem/clone com continuidade; 3 rotas gold após republicação; 200/304 local |
| Redis, fallback e gerações | Testes de concorrência/gerações/ETag; ensaio Redis real com acerto, reinício e indisponibilidade, HTTP 200 pelo PostgreSQL |
| Filesystem/S3 e MinIO | Contrato e replay S3 reais, checksum/concorrência/permissões/persistência conferidos; nenhuma nuvem criada |
| Agendas BCB/IBGE | 6 deployments locais, concorrência 1, retomada conservadora e descarte antes do ETL |
| Observabilidade completa do escopo | Linhas, rejeições, HTTP/retries persistidos, frescor/cobertura IBGE e cache por processo; 3 dashboards, 8 regras |
| Alertas | Alerta API real provocado/resolvido em 19/11; regras e testes promtool aprovados; sem notificação externa |
| Backup/restore e recuperação | Dump novo e clone, catálogo/permissões/dados/API conferidos; referência BCB preservada em restauração realizada em outro dia |
| Demonstração <=15 min | 125,359 s em 23/11, após pré-requisitos e imagens; origem preservada, publicadores SUCESSO no clone |
| Qualidade | 588 testes, 95,80% global; 15 módulos críticos>=95%; Ruff/formato, mypy 56 módulos, Bandit e build aprovados |
| Dependências | pip-audit sem vulnerabilidades conhecidas na consulta de 23/11; pacote próprio editável não consultado como publicado |
| Desempenho | Benchmark datado de 19/11:1 milhão sintético, p95 sem cache 158,75 ms/com cache 126,87 ms; escopo e limites próprios |

Os valores da tabela são evidências locais com datas e protocolos, não SLA externo.
O ensaio Redis usou container exclusivo temporário com credencial aleatória e porta
fixa para atravessar o reinício; somente esse container foi removido. O Redis normal
permaneceu intacto. Fallback observado em 328 ms inclui consulta SQL/HTTP local e
não representa timeout de conexão Redis nem benchmark de carga.

## Evidências privadas e comandos

Arquivos operacionais ignorados pelo Git; a documentação traz seus nomes para
inspeção local, sem expor credenciais:

- `dados/descoberta/qualidade_m2_20261123.json` e `.cache/verificacao_m2_20261123_final.log`.
- `dados/descoberta/demonstracao_m2_20261123_062513.json`.
- `dados/descoberta/restauracao_m2_20261123_062513_6014e5.json`.
- `dados/descoberta/monitoramento_final_m2_20261123_063357.json`:10 rotas únicas200,
  55 contagens de linhas e 5 anos de cobertura comparados ao SQL; 2 alvos saudáveis.
- `dados/descoberta/cache_real_m2_20261123_062415.json`.
- `dados/descoberta/migracao_0010_20261122_040440.json`:backup antes da migração,
  15 objetos core/mart preservados. Backup fora do volume PostgreSQL.
- `.cache/bandit_m2_20261123.json` e `.cache/auditoria_dependencias_m2_20261123.log`.

```powershell
uv run --frozen python scripts/testar_banco.py
uv run --frozen python scripts/demonstrar_m2_local.py
```

Não executar a demonstração durante cargas ou migrações. Ela conserva dump e banco
novo para inspeção. Pré-requisitos, procedimento e limites em
[demonstração](demonstracao-local-m2.md), [recuperação](recuperacao-local-m2.md),
[monitoramento](monitoramento-completo-m2.md) e [runbook](runbook.md).

## Correções finais e decisões

A revisão independente encontrou descoberta confirmada ocultada após falha posterior
e timestamp inválido interrompendo o exporter. Ambas foram reproduzidas e corrigidas
na 0009 e no coletor. A demonstração entre datas diferentes revelou que o pg_restore
recomputava materializadas BCB com relógio atual. A 0010 passou a usar a referência
persistida; publicação, data e três refreshes avançam na mesma transação.

A revisão da0010 apontou risco de recompor gold com core pendente. A migração agora
adquire a trava BCB e recusa esse estado. Testes de referência arquivada, avanço,
rollback, core pendente e trava foram aprovados. Revisão das métricas finais de cache
sem achados; falha do observador não altera resposta nem revela seu erro.

Decisões adotadas: gauges operacionais representam auditoria retida; counters HTTP
e cache são por processo. Replay compara dados e metadados exatamente antes da
nova publicação. A republicação pode avançar referência/flags da gold; o conteúdo
completo é então conferido contra sua definição SQL e pela API. Custo: mais consultas
de verificação e necessidade de interpretar snapshots distintos corretamente.
Alertas de publicação usam1 h de condição observada; reinício do Prometheus reinicia
a janela e pode adiar o aviso. Nenhuma dessas escolhas garante backup externo ou
agendamento com PC desligado.

## Ressalvas de aceite integral

A [auditoria de critérios](auditoria-aceite-m2.md) e o
[complemento de fontes](complemento-fontes-aceite-m2.md) detalham o que falta para
afirmar homologação histórica integral. Manter atribuição IBGE/BCB, limitações
territoriais,`cobertura.completa=null` quando o calendário não foi homologado e
`CALENDARIO_NAO_HOMOLOGADO`. Termos gerais não foram convertidos em licença nominal.

Não houve commit, push, repositório remoto, conta de nuvem ou publicação. O workflow
foi preparado e seus gates executados localmente; isso não é CI remoto aprovado.
Assim, o M2 técnico local está entregue, mas não se declara M1/M2 global sem ressalvas
nem v1.0 publicada. Resolver as ressalvas documentais de fonte é uma pendência de
aceite, distinta das funcionalidades técnicas concluídas.


## Retomada da operação conferida

Servidor e worker Prefect estão `Running`, com seis agendas e pool limitado a um.
As retomadas reais BCB e IBGE terminaram `COMPLETED`; pais SQL `SUCESSO`, com
respectivamente cinco e dez requisições HTTP e zero retentativas nessa rodada.
Relatório: `dados/descoberta/retomada_final_m2_20261123.json`.
Essa atualização normal ocorreu depois da demonstração que preservou a origem;
não se confunde ausência de alteração durante o ensaio com congelamento da operação.
Agendamento depende da máquina, sessão e Docker ativos.


## Avanço documental — 23/11/2026

A [conferência de fontes e referências](conferencia-fontes-2026-11-23.md) confirmou
93 referências IPCA, incluindo 11 de apoio de 2019, sem faltas ou referências inesperadas,
com calendário oficial consultado novamente. A Selic não apresentou lacunas civis
no intervalo observado. Permanecem abertos os termos específicos SGS433 e a
conferência do calendário de cotações do dólar; não tratar68 datas de semana sem
cotação como68 erros sem verificar feriados. A verificação não alterou valores,
calendário empacotado, metadados de cobertura da API ou a conclusão técnica do M2.

## Encerramento da conferência histórica do dólar — 23/11/2026

1.728 datas oficiais PTAX coincidem com o banco; nenhuma divergência. As 68 ausências
em dias de semana foram classificadas, sem preencher dados. [Relatório](conferencia-dolar-2026-11-23.md).
A ressalva documental específica do IPCA permanece como único bloqueio de fonte
identificado para o aceite local integral. CI remoto e M3 permanecem adiados.
