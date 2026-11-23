# Protocolo de desempenho local M2

Ensaio manual de leitura, sem consultar fontes externas. Dados sintéticos não
representam BCB, IBGE nem calendário econômico oficial. Banco novo com prefixo
`etl_benchmark_m2_`, sem reutilização de bases existentes. A origem `etl` recebe
somente consultas em transações de leitura. Não executar ETL durante o ensaio;
mudança nos retratos invalida a comparação.

## Dataset reproduzível

Semente inteira `20261119`: 400 séries, 2.500 datas diárias desde 01/01/2020 até
04/11/2026, exatamente um milhão de fatos em `core.fato_serie`. Valores `numeric`:
`((codigo * 17 + dia * 31 + 20261119) % 100000) / 100`.

Todos os nomes do catálogo começam com `SIMULADA`. O código 432 é reutilizado
somente nessa base sintética para permitir executar a mesma mistura de consultas
do benchmark M1; os demais códigos vão de 10001 a 10399. Nenhum desses valores é
apresentado como Selic real. Lote e execução possuem marca de simulação e não
afirmam existir bronze oficial. UUIDs e instantes do ensaio variam; valores,
chaves e volume do dataset permanecem determinísticos.

Aplicar as migrações existentes em banco vazio; usar somente seus índices.
Executar VACUUM ANALYZE após a carga. Registrar revisão Alembic, PostgreSQL,
definições reais de índices e hashes de scripts, fontes, migrações e uv.lock.
Conferir SHA-256 das linhas completas de todas as tabelas/MVs antes/depois;
streaming COPY evita acumular o milhão de registros em memória Python.

## Medição HTTP

Um processo Uvicorn próprio, loopback e papel `api_leitura`, pool padrão.
Limite de requisições elevado somente no processo do ensaio. Executar primeiro
sem cache e depois com Redis exclusivo autenticado, inicialmente vazio.
Redis operacional não é acessado nem limpo. O container temporário recebe rótulo
aleatório; sua remoção e confirmação são registradas mesmo após criação inconclusiva.
Banco sintético e logs locais são preservados para inspeção.

Cada modalidade: 30 segundos de aquecimento, 60 segundos de medição,
dez clientes HTTPX independentes em concorrência fechada, páginas de cem itens.
Mistura round-robin: início, meio e fim das observações da série simulada 432,
mais a primeira página dos agregados mensais. Os mensais têm menos de cem itens;
registrar as quantidades efetivas. O milhão está distribuído em 400 séries:
este ensaio não mede uma página profunda em uma série de um milhão de datas.

Latência inclui loopback, API, banco/cache, leitura e validação básica da
quantidade de itens no cliente. Não valida cada medida de cada resposta.
Erros HTTP, transporte e validação entram no resultado. p50/p95/p99 por posto
mais próximo, incluindo erros; vazão considera o tempo até concluir as respostas
iniciadas na janela, incluindo drenagem. Não enviar If-None-Match/304.

Instrumentação adicional somente na API do benchmark conta cada resposta que
retorna de `CacheLeitura` sem chamar o cálculo, ou que precisou calcular.
Os contadores são consultados com os clientes parados na barreira antes da
medição e novamente depois da drenagem. A soma deve coincidir com as requisições
medidas. Isso distingue respostas cacheadas de atividade de travas Redis.
Esse contador adiciona pequeno custo de instrumentação nas duas modalidades.
Estatísticas INFO do Redis cobrem o ensaio inteiro e não são taxa de acerto HTTP.

Metas locais: p95 até 500 ms sem cache e 250 ms com cache; 5xx abaixo de 1%.
O indicador de meta também exige zero transporte/validação e somente HTTP 200.
Registrar o resultado mesmo se as metas não forem atendidas. Redis habilitado
mantém fallback; cache não elimina consultas de autoridade/geração ao PostgreSQL.

## SQL, ambiente e limites

Comparar keyset e OFFSET para as mesmas linhas, começo/meio/fim da série de
2.500 registros; LIMIT 101, dez EXPLAIN ANALYZE BUFFERS por estratégia/posição,
planos brutos e mediana de Execution Time. Reutiliza protocolo SQL M1.
Os buffers PostgreSQL/OS ficam aquecidos; não medir como disco frio.

Registrar CPU/RAM Windows, CPUs/RAM efetivos Docker, versões e hashes.
Serviços locais de monitoramento podem continuar ativos; não rodar suíte,
ETL ou outros benchmarks durante a medição homologada. Ordem fixa sem/com cache
não demonstra causalidade isolada nem capacidade máxima. Não é teste de
saturação, de todas as rotas M2, nem SLA de nuvem. A camada IBGE tem testes
funcionais próprios, mas não faz parte dessa mistura HTTP.

```powershell
uv run --frozen python scripts/medir_desempenho_m2.py
```

Resultado em `dados/descoberta/desempenho_m2_DATA_HORA_SUFIXO.json`; logs/configuração
privados em `.cache/etl_benchmark_m2_DATA_HORA_SUFIXO/`. Não versionar esses arquivos,
credenciais ou dados simulados operacionais. Publicar apenas síntese e limites
em documentação. M3 e GitHub continuam adiados.
