# Protocolo de desempenho local M1

## Escopo

Operação manual de leitura sobre o histórico BCB real, conforme seção 13 do plano principal. Não substitui benchmark M2 de um milhão de registros sintéticos em banco separado. Não publica recursos, não consulta BCB/IBGE e não executa ETL. Manter o banco estável durante o ensaio; checksums de todas as tabelas core/ops e MVs mart antes/depois devem coincidir. Revisão do schema consultada pela view sanitizada, sem ampliar permissões.

## Ambiente e preparação

Registrar CPU, RAM Windows, recursos efetivos do Docker, versões, dataset e workers. A imagem/serviço PostgreSQL deve estar ativo e .env.banco/.env.api devem apontar ao mesmo banco local etl. Credenciais não são copiadas ao relatório. Ambiente detalhado local em .cache/ambiente_desempenho.json, obtido por Get-CimInstance e docker info; o JSON do resultado incorpora esse registro quando disponível. Sem esse registro, o campo ambiente fica null e é preciso complementar antes de comparar ambientes.

O script usa um subprocesso próprio, porta livre em 127.0.0.1, um worker Uvicorn e configuração normal de pool da aplicação. Apenas no processo do ensaio, LIMITE_REQUISICOES_MINUTO=100000 evita que o limitador normal de 100/min mascare capacidade de consulta. A configuração do usuário não é alterada. Qualquer 429 é contado e impede declarar meta atendida. O log estruturado da aplicação permanece ativo em arquivo local ignorado pelo Git; access_log do Uvicorn está desativado, conforme a configuração existente do servidor.

## HTTP

Executar scripts/medir_desempenho_local.py. Protocolo fixo: 30 segundos de aquecimento e 60 segundos de medição, dez clientes HTTPX síncronos independentes com keep-alive, concorrência fechada (um pedido em voo por cliente), página solicitada de 100 itens. Sem cache de aplicação/Redis e sem If-None-Match/304; caches PostgreSQL/OS ficam aquecidos, portanto não se trata de leitura física fria.

Mistura round-robin com quatro cenários: primeira página Selic, página central, última página e agregados mensais Selic. Cursores são obtidos antes do aquecimento via paginação real. Na base pequena, fim e gold têm menos de cem itens; registrar as quantidades efetivas. Não fabricar volume para preencher a página. Não interpretar o resultado como todas as rotas/endpoints ou taxa de chegada constante.

Latência inclui transporte loopback, trabalho da API/banco, leitura e decodificação/verificação básica de quantidade no cliente. Amostras completas são guardadas no relatório. p50/p95/p99 usam posto mais próximo ceil(N*p), incluindo erros. Vazão principal considera o tempo real até terminar a drenagem das respostas iniciadas nos 60s; requisições iniciadas depois do prazo não entram. A barreira separa aquecimento e medição.

Registrar HTTP por código, falhas de transporte e validação de corpo. Meta local sem cache: p95 <=500 ms, 5xx <1%, adicionalmente zero transporte/não-200/validação para indicar meta_local_atendida. Essa condição é aplicada ao total e aos cenários. Cache <=250 ms só pode ser avaliado em M2. Não é SLA de hospedagem nem capacidade máxima: há apenas dez clientes, sem rampa de saturação.

## SQL

No mesmo dataset, comparar consulta keyset da aplicação (incluindo parâmetro opcional de cursor) com OFFSET para as mesmas linhas em começo/meio/fim da Selic. LIMIT 101 reproduz o item extra usado para identificar a próxima página de cem itens. Validar igualdade das linhas antes de interpretar tempos.

Executar EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) dez vezes por estratégia/posição, em transação somente leitura REPEATABLE READ. Guardar todos os planos e tempos; reportar mediana de Execution Time (não inclui rede nem toda a latência HTTP). Ordem é keyset e depois OFFSET; buffers já estão aquecidos pelo HTTP. Não adicionar índices ou ajustar PostgreSQL para forçar resultado favorável. Dataset pequeno não prova custo constante ou superioridade universal de keyset.

## Repetir

Com ambiente e credenciais já preparados, a partir da raiz do projeto:

```powershell
uv run --frozen python scripts/medir_desempenho_local.py
```

O script cria relatório exclusivo em dados/descoberta/desempenho_AAAAMMDD_HHMMSS.json e log em .cache/. Sem segredo/cursor no resumo público; o arquivo operacional contém somente parâmetros técnicos, amostras e planos. O subprocesso próprio é encerrado em finally, inclusive em falha. Não executar cargas concorrentes: mudança nos checksums invalida o resultado. Arquivos operacionais permanecem ignorados pelo Git; publicar somente síntese e limites em docs/desempenho.

## Limites conhecidos do verificador

A duração principal inclui drenagem. A vazão exibida para aquecimento usa o prazo nominal com amostras que podem terminar logo após ele; não usar esse número como resultado de desempenho. O campo pool_sqlalchemy descreve o motor SQL do verificador, não telemetria do processo HTTP; o pool HTTP decorre da mesma fábrica de configuração e seus defaults, sem instrumentação adicional. Corpo HTTP 200 com forma inesperada que não seja o objeto/lista esperados pode abortar o ensaio; nesse caso não existe resultado homologado, e a falha deve ser investigada. Estes pontos menores foram registrados na revisão independente; não houve falha desse tipo na execução final.
