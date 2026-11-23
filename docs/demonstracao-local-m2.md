# Demonstração local M2

O comando abaixo restaura a base local em banco novo, reprocessa o bronze BCB e
IBGE existente, publica os dois domínios e confere a API. Não coleta APIs externas.
A meta é até quinze minutos depois dos pré-requisitos e imagens disponíveis.

```powershell
uv run --frozen python scripts/demonstrar_m2_local.py
```

Execute na raiz do projeto, com Python 3.12/uv e dependências do lock disponíveis,
Docker Desktop ativo e PostgreSQL local saudável na porta 55432. Prepare previamente
`.env.banco`, `.env.monitoramento`, Redis autenticado, API demonstrativa na porta
8001, Prometheus em 9090 e Grafana em 3000 conforme
[execução M2](execucao-local-m2.md). O banco `etl` precisa conter o histórico BCB e
a carga IBGE homologada, com seus arquivos imutáveis em `dados/bronze`. Não execute
coletas/agendas ou migrações durante a demonstração: o retrato integral exige origem
estável. Instalação inicial, downloads/builds de imagens, coleta histórica e preparação
de segredos não fazem parte do cronômetro.

O roteiro realiza estas etapas sequenciais:

1. Backup PostgreSQL custom e restauração em nome exclusivo
   `etl_ensaio_m2_AAAAMMDD_HHMMSS_abcdef`, recusando banco existente.
2. Comparação integral dos dados, catálogo, permissões e consultas API entre origem
   e clone, reaproveitando o [ensaio de recuperação M2](recuperacao-local-m2.md).
3. Replay dos manifestos BCB promovidos, em ordem de confirmação, e do pacote IBGE
   mais recente confirmado em filesystem. Contratos e transformação reais são
   executados; a carga usa o papel `processamento` somente no clone.
4. Marca somente `ops.publicacao.data_publicacao` do clone como pendente, após
   conferir o nome do destino e `current_database()`, para exercitar refresh real.
   Publicação BCB/IBGE com papel `publicador`, conferência de hashes de todas as
   tabelas core e MVs, e comparação das consultas API e continuidade dos cursores.
5. Sondagens HTTP da API demonstrativa e métricas, alvos Prometheus saudáveis,
   três dashboards Grafana e revalidação condicional ETag (200 seguido de 304).
6. Novo retrato da origem, encerramento das conexões e relatório privado com
   passos, resultados e duração total em `dados/descoberta/demonstracao_m2_*.json`.

Backup, clone e relatório ficam preservados para inspeção. Não há `DROP`, remoção
de volume, alteração de bronze, reinício de serviço ou publicação externa. O espaço
necessário inclui uma cópia do banco e seu backup por execução. Segredos não são
impressos. Falhas são registradas com o tipo da exceção, sem copiar credenciais.

O replay é um ETL real sobre bronze previamente coletado em clone já restaurado;
o estado final core/gold deve ser idêntico. Não demonstra extração externa nem
reconstrução M2 integral a partir de banco vazio. A auditoria ops do clone pode
registrar novas execuções. Falha de Redis, contenção e alerta provocado possuem
ensaios próprios em [cache](cache-m2.md) e [monitoramento](monitoramento-local.md);
a demonstração rápida não provoca indisponibilidade. A presença dos dashboards
não substitui análise manual de todos os painéis.

## Medição de referência

Máquina Windows de referência, dependências e imagens já disponíveis.
O cronômetro inclui o ETL sobre bronze, além das sondagens HTTP.

Em 19/11/2026, execução real sobre schema `0007`: **173,75 segundos**
(2min54 s), resultado `SUCESSO`. Início 22:40:36 UTC, término 22:43:30 UTC.
Relatório privado: `dados/descoberta/demonstracao_m2_20261119_224036.json`.

| Etapa | Resultado | Duração |
|---|---|---:|
| Backup, restauração e comparação integral | Clone novo confirmado | 66,485 s |
| Replay BCB/IBGE | 79 cargas BCB; 10 manifestos IBGE; 27.855 fatos IBGE inalterados | 92,031 s |
| Publicadores BCB/IBGE | `IGNORADA/JA_PUBLICADA`, gerações 24/24 e 1/1 | 0,094 s |
| Conferências finais e serviços | 25 rotas API, continuidade de cursores, 200/304, alvos saudáveis e três dashboards | Incluídas no total |

Origem preservada por comparação integral; hashes core/gold do clone preservados.
Clone mantido: `etl_ensaio_m2_20261119_224036_e3644c`. A execução conferiu o
caminho idempotente dos publicadores: não foi necessário atualizar MVs já publicadas.
A atualização posterior para schema `0008` requer repetir o mesmo comando com API
compatível; esta medição não alega validar migração posterior.

Após essa medição, o roteiro foi reforçado para exigir `SUCESSO` e refresh real dos
publicadores, mediante controle pendente exclusivamente no clone. A medição acima
corresponde ao caminho anterior, com publicação já atualizada. Repetir o comando
registra a nova evidência sem sobrescrever os relatórios anteriores.

Verificações do roteiro: Ruff aprovado; cinco testes unitários de interrupção antes
do replay, nomes protegidos e conexão divergente aprovados, sem rede ou banco.


## Verificação final — 23/11/2026, esquema0010

Demonstração da versão final: **125,359 segundos**, resultado `SUCESSO`.
Relatório `dados/descoberta/demonstracao_m2_20261123_062513.json`;
clone `etl_ensaio_m2_20261123_062513_6014e5`, preservado para inspeção.
Restauração/comparação48,828 s; replay59,531 s; publicação0,453 s (demais sondagens
incluídas no total). Foram79 cargas BCB e 10 manifestos IBGE, 27.855 inalterados,
zero inserções/alterações. Publicadores BCB/IBGE retornaram `SUCESSO`.

A 0010 preserva referência arquivada no restore, mesmo em outra data. Após replay,
a comparação exata de core/gold e 25 rotas/cursores ocorre antes de forçar nova
publicação. Somente no clone, controle recebe `data_publicacao=NULL` e
`situacao=PENDENTE`; ambas necessárias para exercitar o refresh IBGE.
Nova gold é conferida integralmente contra os seis SELECTs das materializadas,
seguida de três sondagens API da gold republicada. A data/flags temporais podem
avançar legitimamente na republicação, não no restore/replay.
Origem e core do clone preservados; ETag200/304, alvos e três dashboards aprovados.
A medição antiga de 173,75 s correspondia à versão anterior do roteiro.
