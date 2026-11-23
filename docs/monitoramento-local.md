# Monitoramento local — base M2

Atualização 23/11/2026: a instrumentação complementar foi concluída. Ver [monitoramento completo](monitoramento-completo-m2.md) e [aceite técnico](aceite-tecnico-m2.md); as medições iniciais abaixo permanecem históricas.

O módulo `pipeline_etl.api.metricas` fornece middleware ASGI e coletor síncrono
Prometheus. A infraestrutura provisiona três painéis em português: API, pipeline
e frescor. Não há envio de alertas a serviços externos.

## Integração

Atualização de 19/11/2026: integração abaixo implementada na fábrica da aplicação.
Infraestrutura executada localmente, dois alvos saudáveis e três painéis
provisionados. Alerta real provocado e resolvido; evidências e limites em
[execução M2](execucao-local-m2.md). Instrumentação complementar continua pendente.

Criar uma `MetricasAPI` por aplicação, registrar
`metricas.registro.register(EstatisticasPipeline(motor_api))` e adicionar
`MiddlewareMetricas` com argumento `metricas`. Expor `/metrics` em handler `def`,
retornando `Response(metricas.gerar(), media_type=CONTENT_TYPE_LATEST)`.
O coletor usa conexão própria, transação `READ ONLY`, views sanitizadas e timeout
de três segundos. Usar motor com papel de leitura da API.

Counters HTTP são por processo. Esta configuração pressupõe um processo Uvicorn;
vários processos exigem agregação explícita. Rótulos: rota parametrizada, método
conhecido e status HTTP. URLs desconhecidas viram `nao_encontrada`; query strings,
IDs e erros internos não viram rótulos. `/metrics` não é contado. Exceções da
aplicação continuam propagando normalmente.

`pipeline_coleta_disponivel=0` sinaliza consulta indisponível sem detalhes internos;
as demais séries operacionais ficam ausentes nessa coleta, evitando valores
antigos apresentados como atuais. `pipeline_execucoes` é um gauge de execuções
persistidas por situação, não um counter por processo. Frescor BCB reutiliza a
política local: 1 atrasada, 0 em dia, -1 desconhecida. Heurística não equivale a
calendário oficial. Instrumentação IBGE, duração de etapas, quarentena, bronze e
cache exige integração nos respectivos componentes; esta base não comprova o M2.

## Conectividade e ativação

Portas publicadas exclusivamente em `127.0.0.1`: Prometheus 9090, Grafana 3000,
API `${PORTA_API_LOCAL:-8000}` e Redis `${PORTA_REDIS_LOCAL:-6379}`. Gerar
`SENHA_GRAFANA`, `URL_BANCO_API_CONTAINER`, `SEGREDO_CURSOR_CONTAINER` e
`URL_REDIS_CONTAINER` em `.env.monitoramento`, nunca versionado. O Compose exige
essas variáveis e não fornece senhas padrão. URLs dentro dos containers usam DNS
`banco:5432` e `cache:6379`, com senhas codificadas como componentes de URL quando
necessário. A API usa apenas o papel `api_leitura`.

O serviço `api_local` usa o Dockerfile do projeto e executa Uvicorn em
`0.0.0.0:8000` dentro do container, com proxy headers e access log desabilitados.
A porta publicada no Windows permanece em loopback. Prometheus consulta
`api_local:8000/metrics` pela rede privada do Compose; os painéis medem a mesma
API usada em `http://127.0.0.1:8000` (ou porta escolhida). Não há dependência de
uma API Windows acessível por `host.docker.internal`.

Combinar o arquivo de monitoramento ao principal, cujo serviço `banco` fornece
PostgreSQL. A API espera banco saudável; aplicar migrações antes de ativar esta
composição. A API não depende de Redis na inicialização, preservando o fallback.
Gerar previamente `.cache/redis/redis.conf` com senha forte em `requirepass`, sem
versionar seu conteúdo. O arquivo é montado somente leitura; senha não aparece no
comando Redis nem como texto no YAML. `dados_redis` é um volume separado do banco.

`/metrics` fica disponível no host local e na rede privada da composição M2.
Na M3, impedir o acesso público às métricas na futura entrada HTTPS. Não publicar
portas sem prefixo `127.0.0.1`.

Após preparar configuração, migrações e imagens, estes são comandos de operação,
sem constituir evidência de execução. `config --quiet` evita imprimir secrets:

```powershell
docker compose --env-file .env.banco --env-file .env.monitoramento -f compose.yaml -f compose.monitoramento.yaml --profile monitoramento config --quiet
docker compose --env-file .env.banco --env-file .env.monitoramento -f compose.yaml -f compose.monitoramento.yaml --profile monitoramento up -d
```

O projeto combinado `pipeline-etl` usa a rede padrão compartilhada.
Perfil: `monitoramento`. Retenção Prometheus: sete dias. Volumes persistem séries
e estado Grafana. Os três painéis e o datasource são provisionados por arquivos.

## Verificação e alerta simulado

Teste Python sem rede:

```powershell
uv run pytest testes/unidade/test_metricas.py -q
```

Com `promtool` da versão fixada previamente disponível:

```powershell
Push-Location infraestrutura/monitoramento
promtool check rules alertas.yaml
promtool test rules test_alertas.yaml
Pop-Location
```

O teste offline injeta a métrica artificial
`demonstracao_local_falha_simulada{ambiente="teste_local"}`. A regra
`DemonstracaoLocalSimulada` dispara após 30 segundos simulados com valor 1 e
resolve ao voltar a 0. O namespace de teste recebe `simulacao="true"`; não altera
operação/banco nem usa webhook. A API real não exporta essa métrica. O arquivo de
teste não integra `rule_files` operacional.

Os alertas operacionais ficam visíveis no Prometheus local, sem Alertmanager.
Para aceite M2, registrar resultado real de `promtool`, conectividade dos alvos,
três painéis com dados e alerta provocado/resolvido. Testes Python aprovados não
demonstram alerta firing em serviço. O caminho absoluto das regras em
`prometheus.yaml` pressupõe o volume no container; a validação desse arquivo pelo
promtool deve ocorrer nesse contexto ou com cópia temporária ajustada ao Windows.

## Versões e fontes oficiais

Consultadas em 19/11/2026, sem baixar imagens nem iniciar serviços:

- [Prometheus 3.16.0, de 04/11/2026](https://prometheus.io/download/).
- [Grafana OSS 13.3.1, de 10/11/2026](https://grafana.com/grafana/download/13.3.1?edition=oss).
- [Redis: imagem oficial e versão 7.4.12-alpine3.22](https://hub.docker.com/_/redis).

Imagens fixadas por versão. Conferir digests na homologação do pull antes do
empacotamento definitivo. Esta preparação não afirma validação Docker, promtool
ou painéis em execução.
