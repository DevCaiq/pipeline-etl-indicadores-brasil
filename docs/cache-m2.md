# Cache de leitura M2

`pipeline_etl.api.cache.CacheLeitura` recebe um cliente compatível com
`ProtocoloRedis` ou `None`. Importação e construção não fazem I/O.
`obter_ou_calcular(chave, calcular, validade=300)` devolve os bytes da consulta.

O adaptador Redis da aplicação deve normalizar as exceções operacionais de
`redis.exceptions.RedisError` em `ErroBackendCache`, preservando a causa com
`raise ErroBackendCache(...) from erro`. Erros de sistema (`OSError`, incluindo
timeout) também recebem fallback. O adaptador deve configurar os timeouts de
conexão e operação em 100 ms e desabilitar retries por requisição. Não
normalizar exceções de programação como falhas operacionais. A dependência
redis-py e o ciclo de vida da conexão pertencem à aplicação.

O circuito abre por cinco segundos após uma falha de backend. Seu relógio
monotônico e a função de espera são injetáveis. O mutex protege apenas o estado
do circuito; nenhuma operação de rede ou consulta ocorre com esse mutex retido.
Falhas do callback da aplicação continuam sendo propagadas. Falha na escrita
não descarta uma resposta já calculada. O registro de falha contém somente o
nome da classe da exceção, sem chave, cursor ou mensagem do backend.

Somente bytes de até 2 MiB contendo um objeto JSON com `data` e `meta` (objeto)
são reutilizados e armazenados. Conteúdo inválido é uma ausência no cache. A
validação não altera a resposta calculada: o callback continua responsável pelo
contrato HTTP e por não devolver erros como respostas de dados.

A trava usa `SET NX PX` com token aleatório, expira em dois segundos e é liberada
por Lua com comparação do token. Um concorrente espera 50 ms, tenta uma leitura
e então consulta o banco sem publicar, caso ainda não haja resposta. Uma consulta
pode superar o prazo da trava, permitindo cálculo duplicado; a liberação nunca
remove a trava de outro proprietário. O TTL da resposta recebe variação de até
10%. Os TTLs iniciais são 3600 s para catálogos, 900 s para agregados, 300 s para
observações. Frescor permanece fora do cache HTTP.

`criar_chave_cache(dominio, camada, versao, data_publicacao, rota, parametros)`
usa SHA-256 sobre JSON canônico de toda a identidade. Os argumentos devem ser
serializáveis em JSON. `data_publicacao` deve conter o estado completo relevante
à resposta, inclusive publicação pendente e versão gold. `parametros` inclui
filtros, ordenação, limite e cursor. Nenhum desses valores aparece em texto na
chave. Alterações de geração ou estado produzem chaves distintas.

Na integração HTTP, obter a geração e o estado de publicação no mesmo snapshot
PostgreSQL da consulta; para gold, manter a trava de publicação pelo período
necessário à leitura coerente. Verificar versão antes de ETag/304. Não consultar
cache antes de ler essa autoridade persistida. Execuções, erros, operações e
probes não usam cache. A integração de métricas e a seleção de rotas pertencem
à aplicação; este módulo não acessa banco, configuração ou variáveis de ambiente.

Os testes usam somente Redis falso em memória, sem conexão de rede. Eles cobrem
identidade, circuito, conteúdo inválido, TTL, contenção, duas threads, liberação
condicional e propagação de falhas da aplicação.


## Integração HTTP e operação local

O cache vem desabilitado (`CACHE_HABILITADO=false`). Para ativá-lo, definir
`CACHE_HABILITADO=true` e `URL_REDIS` com esquema `redis://` ou `rediss://`.
A URL é secreta, obrigatória somente quando habilitado e não aceita parâmetros
de consulta que possam substituir os limites de conexão. A construção do
cliente não conecta: o primeiro acesso ocorre na leitura de uma rota de dados.
O pool admite oito conexões, com timeouts de 100 ms e zero retentativas.
O cliente é fechado no encerramento da aplicação.

`app.state.cache_leitura` permite compartilhar o circuito entre os roteadores.
`responder_cache` deve ser chamado dentro do snapshot depois de `estado`;
seu callback devolve uma representação 200, com `responder_sem_condicional`.
Toda consulta cara e montagem do DTO pertencem ao callback. A chave incorpora
ambas as versões, situação, publicação, dia brasileiro, domínio, camada,
caminho e parâmetros da requisição, incluindo limite e cursor. Somente o hash
é enviado ao Redis. A negociação de ETag e 304 ocorre após essa leitura.

Catálogo, detalhe, observações, agregados e IPCA de 12 meses BCB usam o cache.
Health, ready, execuções e frescor sempre consultam suas fontes normais.
404 e demais erros não são armazenados. Nenhum cabeçalho operacional de cache
é exposto. Redis indisponível mantém a consulta SQL e o contrato HTTP.
A versão de esquema esperada é `0007`. A trava compartilhada gold é segregada
por domínio: BCB `2026111801`, IBGE `2026112001`.

Verificação sem Redis real:
`uv run pytest testes/unidade/test_redis_local.py --no-cov` e
`uv run python scripts/testar_banco.py testes/integracao/test_cache_api.py --no-cov`.
Os testes SQL usam exclusivamente `etl_testes` e comprovam leitura de geração
em hits, ausência de SELECT dos dados no hit, mudança de chave na publicação e
em pendência, 304, fallback e exclusão das rotas operacionais.
