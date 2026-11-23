# Pipeline de ETL com API de Consulta — Plano revisado

> Revisão: 19/11/2026. Portfólio para engenharia de dados e back-end Python, com foco em engenharia de dados.
> Escopo vigente: concluir M1 e M2 localmente; M3 adiado por instrução posterior do responsável. A disponibilização no GitHub continua adiada. Evidências e pendências atuais em `docs/superpowers/plans/2026-11-19-fechamento-m1-e-m2.md`.
> Ambiente informado: Windows, 32 GB de RAM. Disponibilidade: 2 a 4 horas por semana. Docker/uv instalados e verificados na preparação; evidências em docs/ambiente-local.md.
> Documento de planejamento; somente verificações explicitamente registradas com evidência estão concluídas. Base Python e PostgreSQL/Compose com migração BCB inicial implementados; coleta BCB/bronze implementados; contratos, quarentena e auditoria SQL implementados; transformação e carga BCB idempotente verificadas; coleta incremental/reconciliação por CLI implementadas; indicadores BCB e publicação gold implementados; API M1 implementada e verificada localmente; histórico real BCB carregado até18/11/2026 e verificado ponta a ponta; calendário IPCA 2026 conferido manualmente e recuperação por restauração/replay isolado verificada; frescor por calendário versionado com vigência/fallback implementado; benchmark local M1 medido e documentado; orquestração Prefect local, agendas e retomada implementadas e verificadas; homologação final e demais modelos pendentes. Atualização de execução: 18/11/2026.

## Sumário

1. [Objetivo e entregas](#1-objetivo-e-entregas)
2. [Fontes e homologação](#2-fontes-e-homologação)
3. [Stack e decisões](#3-stack-e-decisões)
4. [Arquitetura](#4-arquitetura)
5. [Modelagem e migrações](#5-modelagem-e-migrações)
6. [Ingestão e bronze](#6-ingestão-e-bronze)
7. [Validação e transformação](#7-validação-e-transformação)
8. [Carga, publicação e recuperação](#8-carga-publicação-e-recuperação)
9. [Orquestração](#9-orquestração)
10. [Contrato da API](#10-contrato-da-api)
11. [Cache](#11-cache)
12. [Observabilidade](#12-observabilidade)
13. [Testes e desempenho](#13-testes-e-desempenho)
14. [Windows, Docker e configuração](#14-windows-docker-e-configuração)
15. [CI e segurança](#15-ci-e-segurança)
16. [Retenção, backup e deploy](#16-retenção-backup-e-deploy)
17. [Fases e critérios de aceite](#17-fases-e-critérios-de-aceite)
18. [Definition of Done](#18-definition-of-done)
19. [Cronograma](#19-cronograma)
20. [Documentação, riscos e próximos passos](#20-documentação-riscos-e-próximos-passos)

## 1. Objetivo e entregas

### Preferências confirmadas pelo responsável

Decisão de sequência confirmada em 19/11/2026: concluir M1, M2 e M3 antes de disponibilizar o código no GitHub. Não criar/publicar repositório remoto durante essas etapas. A validação local de testes, qualidade e empacotamento continua obrigatória; a execução do workflow no GitHub fica adiada até a publicação autorizada do código, sem ser apresentada como já aprovada. M3 continua exigindo hospedagem real da API, agendamento independente do PC e recuperação externa demonstrada: apenas preparar arquivos de deploy não conclui esse marco. Provedor, conta, limites e autorização dos recursos serão definidos antes da implantação. Frontend de insights fica para depois da conclusão do projeto.

- Portfólio para engenharia de dados e back-end Python, priorizando engenharia de dados.
- Primeira entrega com BCB; IBGE na etapa seguinte, mantendo ambos no escopo final.
- Histórico BCB desde 01/01/2020; população conforme disponibilidade oficial e comparabilidade documentada.
- Validar localmente primeiro; publicar posteriormente. Não criar front-end obrigatório.
- Usar máquina Windows de 32 GB; preparar Docker como tarefa inicial.
- Planejar para 2 a 4 horas semanais, sem prometer data de lançamento.

### Convenção obrigatória de idioma — solicitação do responsável

Todo identificador criado pelo projeto deve usar português-BR: classes, funções, métodos, parâmetros, variáveis, atributos, constantes, exceções, módulos, comandos próprios, campos de configuração e nomes de testes. Comentários, docstrings, mensagens e documentação também em português-BR.

- Usar identificadores sem acentos/cedilha: ExecucaoPipeline, buscar_serie, codigo_serie, ConfiguracaoAplicacao, ErroDeColeta, DATA_INICIAL.
- Classes em PascalCase; funções, métodos, módulos e variáveis em snake_case; constantes em MAIUSCULAS_COM_SUBLINHADO.
- Preservar palavras-chave Python, métodos especiais como __init__, API de bibliotecas, parâmetros exigidos por ferramentas e nomes padronizados de arquivos como pyproject.toml, Dockerfile e compose.yaml.
- Preservar contratos externos: dataInicial/dataFinal do BCB, chaves recebidas, headers HTTP, SQL e termos oficiais. Fazer tradução na fronteira com modelos internos quando necessário, sem alterar bronze.
- Prefixo test_ é exigência de descoberta do pytest: usar test_buscar_serie, com o restante do nome em português. Pastas próprias de testes usam testes/amostras.
- Não traduzir imports de terceiros artificialmente nem criar aliases apenas para ocultar a API de uma biblioteca. Siglas técnicas oficiais como API, HTTP, SQL, BCB e IBGE são permitidas.
- O pacote será pipeline_etl; nenhuma classe/função própria deve ser criada em inglês sob pretexto de seguir o exemplo antigo do plano.

### Marcos

| Marco | Escopo obrigatório | Adiado |
|---|---|---|
| M1 — v0.1 local | Meta Selic, IPCA e dólar; bronze filesystem; PostgreSQL; contratos; incremental/backfill/replay; gold BCB; Prefect/CLI; FastAPI paginada; logs; testes e CI | IBGE, Redis, MinIO, Grafana e publicação |
| M2 — v0.2 local | IBGE Localidades e população estimada; gold completa; Redis; adapter S3/MinIO opcional; Prometheus/Grafana; runbook e recuperação | Hospedagem pública obrigatória |
| M3 — v1.0 publicada | M2 validado; provedor escolhido; API HTTPS; agendamento externo; storage durável; backup/restore e documentação de portfólio | Front-end, alta disponibilidade e serviços pagos |

Perguntas atendidas: evolução econômica desde 2020 na periodicidade nativa; estatísticas mensais/anuais; IPCA em 12 meses; municípios e população nos anos disponíveis; soma municipal por UF/região com cobertura; última coleta, referência e publicação por conjunto.

Não converter IPCA mensal em dado diário; não tratar Meta Selic como rendimento diário; não misturar censo e estimativa. CDI, PIB, novas fontes, dashboard próprio, streaming, machine learning e API pública de escrita ficam fora desta versão.

## 2. Fontes e homologação

### 2.1 BCB — catálogo definido

| Código SGS | Série | Periodicidade | Unidade no recorte | Tratamento |
|---|---|---|---|---|
| 432 | Meta Selic definida pelo Copom | Diária | % a.a. | Estatísticas de valores publicados, sem composição como retorno diário |
| 433 | IPCA — variação mensal | Mensal | % no mês | Valor mensal original e composição para acumulados |
| 1 | Câmbio livre — dólar americano, venda | Diária | BRL/USD | Estatísticas de observações publicadas, sem preencher dias ausentes |

Escolher Meta Selic 432 é intencional; não substituir pela Selic diária 11, que representa outra grandeza.

Endpoint:

    https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial=DD/MM/AAAA&dataFinal=DD/MM/AAAA

Histórico público: 2020 em diante. Extrair também IPCA de fevereiro a dezembro de 2019 como janela técnica para calcular os 12 meses de janeiro/2020. Guardar apoio no bronze/core e impedir exposição desses meses como observações públicas anteriores ao recorte.

Backfill em lotes anuais, sem sobreposição de limites. O catálogo oficial do dólar informa filtros obrigatórios e limite de dez anos por consulta diária desde 26/03/2025. Um ano por requisição é escolha conservadora do projeto, não quota oficial de requisições.

Referências oficiais consultadas em 17/11/2026:

- [BCB — identificação da Meta Selic 432](https://www.bcb.gov.br/controleinflacao/historicotaxasjuros?lang=pt).
- [SGS — IPCA 433 e variação mensal](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=433).
- [Catálogo BCB — dólar venda 1, metodologia, licença e restrição](https://dadosabertos.bcb.gov.br/dataset/1-taxa-de-cambio---livre---dolar-americano-venda---diario).

Estado: as três consultas JSON pequenas retornaram HTTP 200 nesta execução; corpos originais e hashes estão em dados/descoberta, com cópias em testes/amostras/bcb. Ver docs/fontes.md. Calendários, cobertura histórica completa e casos de erro continuam pendentes; amostra bem-sucedida não homologa todas as condições operacionais.

### 2.2 IBGE — metadados confirmados; dados municipais pendentes

- Base Localidades: https://servicodados.ibge.gov.br/api/v1/localidades . Consultar regiões, estados e municípios.
- Base Agregados: https://servicodados.ibge.gov.br/api/v3/agregados . Metadados confirmados: tabela 6579, variável 9324, população residente estimada, nível municipal N6.
- Homologar os recursos /6579/metadados e /6579/periodos: variável, unidade, classificações, níveis territoriais e anos disponíveis.
- Modelo a validar: /6579/periodos/{ano}/variaveis/9324?localidades=N6[all] . Codificar parâmetros no cliente HTTP.
- Recorte: anos publicados a partir de 2020. Não fixar último ano sem consultar períodos; não completar lacunas com interpolação, zero ou censo.
- Extrair por ano; subdividir por UF se necessário, com sintaxe e limites homologados. Manifesto registra partições e cobertura.
- Hierarquias opcionais de localidades podem estar ausentes; UF e região obrigatórias após normalização. Não exigir microrregião/mesorregião para aceitar um município válido.

Referências: [Localidades](https://servicodados.ibge.gov.br/api/docs/localidades), [Agregados](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3) e [SIDRA 6579](https://sidra.ibge.gov.br/tabela/6579).

**Atualização da descoberta:** a consulta direta aos endpoints oficiais de metadados e períodos retornou HTTP 200. Confirmados tabela 6579, variável 9324, unidade Pessoas, periodicidade anual, nível N6 e ausência de classificações. No recorte 2020+, os períodos retornados foram 2020, 2021, 2024, 2025 e 2026; 2022 e 2023 não estão disponíveis nessa tabela. Corpos e hashes em dados/descoberta. Consulta de valores municipais, marcadores, cobertura territorial e termos IBGE continuam pendentes e não bloqueiam M1.

### 2.3 Evidência exigida em docs/fontes.md

Registrar por fonte: URL oficial e data de consulta; código, nome, produtor/distribuidor; unidade, periodicidade e cobertura; licença/termos e atribuição; campos/marcadores; calendário; limites oficiais versus limites conservadores do projeto; exemplos e erros conhecidos.

Homologação exige chamada real pequena bem-sucedida por série/endpoint, metadados arquivados e fixture representativa. Guardar respostas originais no bronze e amostras pequenas em testes/amostras. Conferir licenças por dataset; MIT do código não substitui licença dos dados.

## 3. Stack e decisões

O escopo da seção 1 foi confirmado pelo responsável. As escolhas técnicas abaixo são decisões desta revisão, a registrar em ADRs; não são preferências adicionais atribuídas ao responsável.

| Responsabilidade | Escolha |
|---|---|
| Runtime/pacotes | Python 3.12, uv, pyproject.toml e uv.lock |
| HTTP/retry | httpx síncrono e tenacity |
| Contratos/config | Pydantic v2 e pydantic-settings |
| Transformação | Funções puras, Decimal e SQL; pandas para IBGE/conferência |
| Banco/migrações | PostgreSQL 16, SQLAlchemy 2.x, psycopg 3 síncrono e Alembic |
| API | FastAPI/Uvicorn; handlers síncronos para banco síncrono |
| Orquestração | Prefect 3, independente da lógica de negócio |
| Bronze | Filesystem imutável no M1; interface de storage; adapter boto3/S3 e MinIO opcional no M2 |
| Cache | Redis 7 no M2 |
| Qualidade | pytest, respx, pytest-cov, Ruff, mypy, pre-commit, bandit, pip-audit |
| Operação | structlog desde M1; Prometheus/Grafana no M2; Docker Compose v2 e GitHub Actions |

Alternativas consideradas: infraestrutura completa desde o início aumenta trabalho antes de obter dados; SQLite/CSV reduz setup, mas exige migração da arquitetura. A entrega gradual escolhida mantém PostgreSQL desde o começo e adia serviços adicionais.

Não adicionar Celery, SQLModel, asyncpg, Polars, Airflow, Dagster, Pandera ou dbt ao escopo obrigatório. Parquet, Sentry, Hypothesis e OpenTelemetry são evoluções opcionais. Mesmo com Parquet, preservar resposta original como evidência bronze.

Handlers com banco síncrono usam def; não executar cliente/banco bloqueante diretamente em async def. Uma sessão por tarefa/requisição, sem compartilhar entre threads; fechar clientes/pools no ciclo de vida apropriado.

ADRs: escopo, stack síncrona, orquestrador, bronze/retenção, transações/watermark/publicação, agregações, cache/cursores e deploy. Resolver compatibilidade e fixar versões exatas/imagens na Fase 1; não inventar versões de patch neste plano. Builds usam lock e atualizações passam pelo CI.

## 4. Arquitetura

Fluxo: fontes → extração → bronze imutável → contrato/transformação → staging → core → publicação gold → API. Quarentena recebe registros rejeitados; ops mantém execução, artefatos, checkpoints e versões. Redis acelera consultas no M2.

Conector interpreta fonte; storage guarda bytes/manifestos; transformação não acessa rede/banco; loader promove transações; publicador atualiza MVs/versão; API consulta; Prefect coordena. Lógica de negócio não importa decorators Prefect.

Estrutura alvo, criada conforme cada fase:

    src/pipeline_etl/
      configuracao.py, registros.py, comandos.py
      banco/               # modelos, sessão, permissões
      processamento/
        clientes/, contratos/, armazenamento/, transformacoes/
        qualidade.py, carga.py, publicacao.py, execucoes.py
      fluxos/
      api/
        aplicacao.py, dependencias.py, paginacao.py, cache.py
        rotas/v1/, esquemas/
    migracoes/
    sql/
    testes/{unidade, contratos, integracao, api, amostras}/
    docs/{decisoes, desempenho}/
    scripts/
    monitoring/
    .github/workfluxos/
    compose.yaml, Dockerfile, .dockerignore
    .env.example, pyproject.toml, uv.lock, README.md

## 5. Modelagem e migrações

Estado de execução em 18/11/2026: revisão 0001 cria ops.execucao, ops.lote, core.dim_serie e core.fato_serie, além dos três schemas e permissões. Os demais objetos abaixo são contratos alvo para novas revisões junto aos consumidores, não tabelas já disponíveis. Ver docs/banco-de-dados.md.

### 5.1 Schema ops

| Tabela | Campos/chaves mínimos | Regra |
|---|---|---|
| execucao | execucao_id UUID PK, modo, parâmetros, status, início/fim, versão código/contrato, erro sanitizado | Uma execução tem várias etapas |
| etapa | etapa_id UUID PK, execucao_id FK, fonte, conjunto, fase, tentativa, status, contagens, início/fim | Diferenciar extração, validação, carga e publicação |
| artefato | artefato_id UUID PK, etapa_id FK, janela, parâmetros, URI, SHA-256, tamanho, status HTTP, coleta | Uma requisição aceita gera um objeto; várias por execução |
| quarentena | id PK, etapa_id/artefato_id FK, posição, registro original, motivo, criação | Rejeição rastreável |
| lote | lote_id UUID PK, fonte, conjunto, janela, manifesto, status, hash lógico, contagens, commit | Confirma cobertura e checkpoints |
| watermark | PK (fonte, conjunto), ultimo_periodo_confirmado, atualização | Não confundir com publicação gold |
| publicacao | domínio PK (bcb/ibge), versao_core, versao_gold, status, última publicação, erro | PostgreSQL é autoridade das gerações |
| snapshot_territorial | snapshot_id PK, artefato FK, coleta, hash do catálogo | Referência territorial usada na importação |

Estados: EM_EXECUCAO, SUCESSO, PARCIAL, FALHA, IGNORADA. Etapa não iniciada por dependência falha fica IGNORADA. Processo interrompido só é reconciliado como FALHA após confirmar ausência do worker/liberação do lock, não por idade isolada.

Timestamps TIMESTAMPTZ em UTC; observações DATE. Mês normalizado no primeiro dia, mantendo data original no bronze.

### 5.2 Schema core

| Tabela | Chave | Campos/regras |
|---|---|---|
| dim_serie | codigo_sgs | nome, periodicidade, unidade, início público e regra de agregação |
| fato_serie | (codigo_sgs, data) | valor NUMERIC(24,10), lote_id FK, alterado_em |
| dim_regiao | codigo | sigla, nome |
| dim_uf | codigo | sigla única, nome, regiao_codigo FK |
| dim_municipio | codigo_ibge CHAR(7) | nome atual, uf_codigo FK, ativo, snapshot_id FK |
| dim_indicador | indicador_id | fonte, tabela, variável, natureza, unidade, metadados; UNIQUE (fonte, tabela, variavel, natureza) |
| fato_populacao | (codigo_ibge, ano, indicador_id) | população BIGINT NULL, marcador/motivo, UF/região de referência, base territorial, snapshot_id, lote_id |
| preparacao_* | chave natural + lote_id | Dados validados antes da promoção |

População presente é inteira e não negativa; ausência oficial fica NULL com motivo, sem virar zero. Marcador desconhecido ou município sem referência resolvida bloqueia o lote/publicação do ano; não descartar silenciosamente.

UF/região histórica não é derivada apenas da dimensão atual. Usar associação oficial para o período quando disponível; senão rotular base_territorial=atual_na_coleta, registrar limitação e não apresentar como malha histórica. Não misturar bases diferentes no mesmo total. Não fazer fuzzy match por nome; inativar códigos removidos sem apagar fatos antigos.

### 5.3 Índices, lineage e migrações

- PK fato_serie (codigo_sgs, data) atende ordenação por série/data; não criar índice DESC redundante sem EXPLAIN.
- Índices iniciais: fato_populacao (ano, indicador_id, uf_referencia); dim_municipio (uf_codigo, codigo_ibge); etapa (execucao_id); artefato (etapa_id); execucao (iniciado_em DESC, execucao_id); quarentena por etapa/artefato.
- Busca q com ILIKE parametrizado inicialmente; pg_trgm somente após medição e suporte do provedor.
- Fato aponta ao último lote que alterou valor; lote aponta ao manifesto/artefatos. Consultas repetidas sem alteração permanecem em ops.
- Alembic cria schemas, tabelas, constraints, índices, funções, views sanitizadas de ops e MVs. Provisionar credenciais separadamente de DDL.
- SQL chamado por migration é imutável por revisão. Mudança gera novo arquivo/migration; não alterar SQL histórico.
- Criar/popular MVs na migração, mesmo vazias. Refresh posterior usa CONCURRENTLY com índice UNIQUE simples cobrindo todas as linhas. Primeira população de MV criada WITH NO DATA exige refresh sem CONCURRENTLY.
- API recebe somente SELECT em core/mart e views sanitizadas de ops. Loader escreve; publicador possui ou assume papel proprietário das MVs; migrador aplica DDL. Nenhuma credencial elevada na API.

Referência: [PostgreSQL 16 — refresh, índices e primeira população](https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html).

## 6. Ingestão e bronze

Estado em 18/11/2026: cliente BCB, bronze filesystem e CLI por período implementados e sondados; registro SQL detalhado e contratos/quarentena implementados; carga BCB idempotente verificada; coleta incremental/reconciliação por CLI implementadas; histórico completo e agendamento pendentes. Ver docs/incremental-bcb.md. Ver docs/carga-bcb.md. Ver docs/validacao-e-quarentena.md. A coleta não depende do banco e não marca dados como validados. Ver docs/coleta-e-bronze.md.

### HTTP

- Cliente reutilizável por tarefa, TLS validado, hosts oficiais fixos. API pública não aceita URLs arbitrárias.
- Timeouts iniciais: conexão 10 s; leitura/escrita 30 s; pool 10 s. Orçamento de 180 s para iniciar operações/esperas, verificado também entre blocos e ao concluir; o transporte HTTPX usa limites por fase e não cancelamento rígido de operação já bloqueada.
- Até 5 tentativas HTTP, somente em falhas transitórias de rede/timeout, 429, 500/502/503/504. Outros erros falham sem retry automático.
- Backoff exponencial com jitter, 1–30 s. Retry-After aceita segundos/data HTTP e determina espera mínima. Se não couber no orçamento, adiar etapa e registrar próximo horário elegível; não reduzir a espera exigida pelo servidor.
- Não multiplicar tentativas no Prefect: falha HTTP esgotada não recebe outro ciclo automático. Retry de tarefa apenas para falha local transitória, com checkpoint, até 1 repetição.
- Uma requisição ativa por fonte, intervalo inicial de 1 s entre inícios. Limite do projeto, não quota oficial; reduzir conforme orientação da fonte.
- JSON/contrato inválido não é falha de rede. Preservar corpo HTTP bem-sucedido antes de qualquer parse.

### Bronze

    bronze/{fonte}/{conjunto}/{AAAA-MM-DD}/{execucao_id}/{artefato_id}.body
    bronze/{fonte}/{conjunto}/{AAAA-MM-DD}/{execucao_id}/{artefato_id}.meta.json
    bronze/{fonte}/{conjunto}/{AAAA-MM-DD}/{execucao_id}/manifest.json

Guardar bytes do corpo fornecido pelo cliente antes de transformações do projeto. SHA-256 sobre esses bytes; a implementação usa iter_raw, preserva Content-Encoding e registra descompressao_automatica=false. Metadados incluem IDs, parâmetros canônicos, URL sem segredos, HTTP status, tipo, coleta UTC, tamanho, checksum, janela e versão do contrato.

Manifesto lista objetos, ordem, cobertura esperada e checksums. Filesystem: arquivo temporário com fsync e publicação exclusiva por hard link no mesmo volume, sem sobrescrita. S3: chave única, manifesto por último. Parâmetros brutos nunca viram nome de arquivo. Falha ao gravar bronze impede carga. Reconciliar órfãos por manifesto/checksum; não prometer transação entre storage e banco.

## 7. Validação e transformação

### 7.1 Qualidade

Validar envelope/chaves separadamente dos valores de linha. Chave obrigatória ausente ou extra não prevista falha o lote inteiro. Usar ConfigDict(extra='forbid') nos contratos Pydantic e testes explícitos; o modelo sozinho não decide status operacional.

Referência: [Pydantic — campos extras](https://docs.pydantic.dev/latest/api/config/).

| Condição | Ação |
|---|---|
| JSON/envelope/chaves incompatíveis | FALHA; nada promovido |
| Data impossível/futura, decimal não finito | Quarentena de linha |
| Duplicata idêntica | Deduplicar e contar separadamente |
| Mesma chave com valores conflitantes no lote | FALHA; sem escolha arbitrária |
| Sem rejeição e checks aprovados | SUCESSO; promover/publicar |
| Rejeição >0% e <=5% | PARCIAL; guardar staging/quarentena, sem promover lote incompleto |
| Rejeição >5% | FALHA; sem promoção |
| Resposta vazia | Sem mudança somente se ausência justificável; caso contrário bloquear confirmação da janela |
| Variação de volume >20% em janela comparável | Alerta; bloquear se cobertura obrigatória ausente |

Taxa = rejeitadas/recebidas; denominador zero tratado à parte. Contar recebidas, válidas, rejeitadas, duplicadas, inseridas, alteradas e inalteradas. O limite de 5% classifica o problema, não autoriza total populacional subcontado ou IPCA com lacuna.

Faixa plausível gera alerta específico por série, não descarte universal de extremos. Dólar positivo; IPCA pode ser negativo. Interpretar marcadores IBGE conforme metadados: -, ..., .., X e vazio não são sinônimos automáticos de zero ou NULL. Preservar símbolo e significado homologado; marcador novo bloqueia lote.

### 7.2 Regras dos indicadores

Usar Decimal e NUMERIC; não converter para float na carga. Escala de entrada superior a 10 casas exige decisão de contrato, sem truncamento silencioso. Não preencher observações ausentes.

| Indicador | Mensal | Anual | Regra de incompletude |
|---|---|---|---|
| Meta Selic | Média simples, mínimo, máximo e último dos valores publicados, em % a.a. | Mesmas estatísticas sobre observações do ano | Não compor como rentabilidade |
| Dólar venda | Média simples, mínimo, máximo e último, em BRL/USD | Usar observações anuais, sem média de médias mensais | Não criar cotação de feriado |
| IPCA | Variação original do mês | Composição janeiro–dezembro | Ano sem 12 meses retorna NULL/completo=false |
| IPCA 12m | 12 meses-calendário consecutivos até o mês consultado | Não aplicável | Lacuna ou menos de 12 meses retorna NULL e motivo |
| População | Não aplicável | Soma municipal por ano/indicador/base/território | Total NULL se cobertura incompleta; soma parcial em campo separado |

IPCA acumulado = 100 × (produto(1 + taxa_mensal/100) − 1). Verificar continuidade, não somente contagem. Implementar produto com aritmética NUMERIC em função SQL versionada ou estratégia equivalente sem float; conferir com Decimal em teste independente.

Arredondar somente na resposta: 6 casas, ROUND_HALF_EVEN, decimal como string. População como inteiro JSON ou NULL. Estatísticas incluem unidade, número de observações e flag parcial para período em andamento; não confundir mês aberto com cobertura completa.

MVs: mart.mv_serie_mensal, mv_serie_anual, mv_ipca_12m, mv_populacao_uf, mv_populacao_regiao. Chaves únicas por série/período ou indicador/base/território/ano.

População exige comparar códigos presentes e esperados, não apenas contagem. Catálogo esperado deve corresponder à cobertura/ano documentados; se desconhecido, não declarar total completo. Soma municipal é derivada pelo projeto, sem prometer igualdade com totais oficiais independentes.

## 8. Carga, publicação e recuperação

### Idempotência e incremental

- Upsert por chave natural com IS DISTINCT FROM nos campos de negócio. Payload igual não altera valor, lote de origem nem alterado_em; somente cria histórico operacional.
- Lote vazio é operação sem mudança. Usar staging e lotes pequenos antes da promoção.
- Fatos, lote confirmado, watermark e incremento de versao_core mudam atomicamente por lote. Falha reverte tudo; registrar falha em transação operacional separada.
- BCB diário recua 30 dias da última observação confirmada; IPCA recua 24 meses, incluindo apoio técnico necessário. Fim: hoje em America/Sao_Paulo.
- Sem watermark, executar backfill explícito. Confirmar janelas em ordem; falha anterior impede saltar checkpoint. Backfill fora de ordem nunca reduz watermark nem salta intervalo não confirmado. ops.lote registra cobertura, watermark resume.
- Reconciliação BCB mensal: todo o recorte desde 2020 + apoio IPCA. IBGE descobre períodos mensalmente e revê anos do recorte trimestralmente.
- Upsert não trata exclusão: desaparecimento de registro gera alerta. Exclusão somente por snapshot completo/validado, evidência preservada e reconciliação explícita auditada.

### Concorrência e publicação

Advisory lock PostgreSQL por domínio bcb/ibge durante promoção e publicação, com conexão dedicada. CLI e Prefect respeitam mesmo lock. Fontes distintas avançam independentemente. Timeout inicial de aquisição: 30 s; depois adiar tentativa, sem sobrescrever outra execução.

1. Persistir bronze, validar, transformar e preparar staging.
2. Adquirir lock; promover somente lote completo em transação.
3. Na mesma transação, incrementar versao_core e marcar publicação PENDENTE quando houver mudança.
4. Atualizar todas as MVs do domínio numa transação de publicação, sem promoção concorrente desse domínio. Somente após todas concluírem, definir versao_gold=versao_core e PRONTA, na mesma transação.
5. Liberar lock e sinalizar cache. Falha Redis gera aviso, sem rollback dos dados publicados.

Se refresh falhar, reverter transação de publicação: core válido permanece, gold anterior permanece e versao_gold não avança. Manter PENDENTE e diagnóstico; reexecutar publicação sem baixar fonte novamente.

API pode servir core novo e gold anterior com versões explícitas e desatualizado=true na gold. Não prometer snapshot global entre endpoints. MVs de um domínio publicam juntas; falha BCB não impede IBGE.

### Replay

Entrada: manifesto ou plano de replay, checksums e contrato compatível. Nenhuma chamada externa. Reconstruir primeiro em banco/schema isolado, aplicar manifestos na ordem de promoção original e comparar valores/cobertura/checksums lógicos antes de trocar destino.

Guardar origem, ordem, substituições e exclusões autorizadas nos manifestos/registro operacional. Bronze antigo não sobrescreve produção atual por padrão; restauração explícita exige destino/plano auditado. Replay não é sinônimo de aplicar qualquer arquivo antigo sobre o banco atual.

## 9. Orquestração

Implementação local verificada em 19/11/2026: Prefect 3.9.3 em ambiente isolado, banco/papel próprios, pool/worker com concorrência um, agendas BCB e IBGE e tarefas Windows no logon. Fluxos reais, retomadas e API testados. Ver [operação BCB e limites](docs/orquestracao-local.md) e [agendas IBGE, armazenamento e evidências](docs/orquestracao-ibge-local.md). O deployment BCB das 22h recupera publicação pendente; ainda não inclui qualidade independente adicional.

Prefect chama as mesmas funções da CLI. M1 permite execução manual sem servidor remoto; deployment/worker locais entram após funções testadas. Documentar criação e inicialização conforme versão fixada do Prefect.

| Fluxo | Agenda inicial America/Sao_Paulo | Política |
|---|---|---|
| BCB incremental | Diário, 20h | Horário do projeto; conferir publicação real na descoberta |
| BCB reconciliação | Primeiro domingo do mês, 21h | Mesmo lock da carga diária |
| IBGE Localidades | Domingo, 18h | Snapshot antes de fatos novos |
| IBGE descoberta/incremental | Dia 5 de cada mês, 20h | Somente períodos homologados |
| IBGE reconciliação | Dia 1 dos meses 1/4/7/10, 21h | Rever anos e cobertura |
| Qualidade/publicação pendente | Diário, 22h e após carga | Recuperar sem nova extração |

Máquina e processos locais precisam estar ativos. Após parada, executar catch-up incremental ao reiniciar; não prometer agendamento com PC desligado. Notificações externas são opcionais, configuradas pelo responsável; logs/alertas locais bastam para M1/M2.

Comandos alvo a implementar:

    uv run pipeline-etl coletar bcb --modo carga-historica --inicio 2020-01-01 --fim AAAA-MM-DD
    uv run pipeline-etl coletar bcb --modo incremental
    uv run pipeline-etl coletar ibge --modo incremental
    uv run pipeline-etl reprocessar --manifest CAMINHO --destino recuperacao
    uv run pipeline-etl publicar --dominio bcb
    uv run pipeline-etl verificar-qualidade --dominio bcb

Backfill público inclui apoio IPCA automaticamente. IBGE somente após homologação. API somente leitura não dispara carga pública.

Status global: SUCESSO se todos os conjuntos obrigatórios concluíram sem rejeição; PARCIAL se algum conjunto independente concluiu e outro falhou/foi rejeitado, ou se core mudou e publicação ficou pendente; FALHA se nenhum conjunto obrigatório concluiu. Etapa IGNORADA não equivale a sucesso. Falha apenas no cache não torna carga íntegra uma falha.

## 10. Contrato da API

### 10.1 Rotas

Dados/operacional público em /api/v1; probes e metrics na raiz, por decisão explícita de infraestrutura. Nenhuma rota pública de escrita.

| Marco | GET | Parâmetros/contrato |
|---|---|---|
| M1 | /api/v1/series | Catálogo das três séries |
| M1 | /api/v1/series/{codigo} | Unidade, periodicidade, cobertura e regras |
| M1 | /api/v1/series/{codigo}/observacoes | de, ate, limite, cursor; data crescente |
| M1 | /api/v1/series/{codigo}/agregados | granularidade=mes ou ano; período e paginação |
| M1 | /api/v1/indicadores/ipca-12m | Período, paginação e completude da janela |
| M1 | /api/v1/pipeline/execucoes | Histórico sanitizado, fonte/status, paginação |
| M1 | /api/v1/pipeline/frescor | Consulta, referência, publicação e cobertura |
| M2 | /api/v1/regioes e /api/v1/ufs | Dimensões geográficas |
| M2 | /api/v1/municipios | uf, q, limite, cursor; ordem por código |
| M2 | /api/v1/municipios/{codigo_ibge} | Cadastro atual e limitação temporal |
| M2 | /api/v1/municipios/{codigo_ibge}/populacao | ano_de, ano_ate, indicador e paginação |
| M2 | /api/v1/populacao/ufs e /api/v1/populacao/regioes | Ano, indicador, base, cobertura e total derivado |
| M1 | /health | Processo vivo; 200 sem dependências |
| M1 | /ready | 200 com banco e schema compatíveis; 503 sem dependência obrigatória |
| M2 | /metrics | Privado, por rede ou autenticação de infraestrutura |

Rotas IBGE não são registradas antes do M2. Banco vazio pode estar ready; frescor informa ausência. Redis fora do ar ou dados defasados indicam degradação, sem provocar 503 quando banco/schema estão aptos.

### 10.2 Filtros, formatos e erros

- Datas ISO YYYY-MM-DD; timestamps UTC com Z. de/ate inclusivos.
- limite padrão 100, mínimo 1, máximo 1000; listas factuais/agregadas paginadas. Catálogos pequenos podem ser completos.
- Início público BCB 2020-01-01; filtro anterior, de>ate ou data futura: 422. Sem filtros, início público e hoje.
- Janela máxima de consulta BCB 3660 dias inclusivos; população até 20 anos. Limite da API de consulta é distinto do lote de extração externa.
- q de 2 a 100 caracteres, substring literal com curingas escapados; uf normalizada para sigla maiúscula válida.
- Série/município inexistente: 404. Recurso existente sem observações: 200 com lista vazia e cobertura. Ano sem estimativa não vira zero nem 404 do município.
- Janela incompleta de IPCA: valor=null, completo=false e motivo.
- 422 para parâmetro/cursor inválido; 409 CURSOR_EXPIRADO para geração antiga/vencimento; 429 para rate limit com Retry-After; 503 para banco obrigatório indisponível; 500 sem stack trace.
- Request ID em header/erros. Operação pública nunca retorna URLs sensíveis, payload de quarentena ou mensagem interna de exceção.

Exemplo de observações com valores ilustrativos:

    {
      "data": [{"data": "2026-01-02", "valor": "5.123400"}],
      "pagina": {"limite": 100, "proximo_cursor": null, "tem_mais": false},
      "meta": {"codigo": 1, "unidade": "BRL/USD", "versao_dados": 7, "camada": "core"}
    }

Erro padrão:

    {
      "erro": {
        "codigo": "CURSOR_INVALIDO",
        "mensagem": "Cursor inválido para os filtros informados.",
        "requisicao_id": "identificador",
        "detalhes": []
      }
    }

Adaptar erros de validação FastAPI ao envelope. Schemas e exemplos de sucesso/vazio/erro de cada endpoint são entregáveis da respectiva fase e devem aparecer no OpenAPI. Mudança incompatível cria /api/v2; campos novos são aditivos.

### 10.3 Keyset e consistência

Ordenações: observações (codigo_sgs, data) com série fixa; municípios por código; execuções (iniciado_em DESC, execucao_id DESC); população (ano, indicador_id) com município fixo. Cada lista deve incluir desempate único; buscar limite+1, sem OFFSET profundo.

Cursor contém versão do formato, rota, hash dos filtros/ordenação, últimas chaves e geração do domínio/camada. JSON em Base64 URL-safe, assinado HMAC-SHA256. Base64 não fornece autenticação ou confidencialidade. Secret igual entre instâncias, fora do Git; rotação invalida cursores anteriores.

Validar assinatura/tipos e tamanho máximo de 2048 caracteres antes da consulta parametrizada. Cursor de outra rota/série/filtro: 422. Mudança de geração ou vencimento após 24h: 409 e reinício da navegação. Não manter transação entre páginas.

Dentro de cada requisição de dados, geração e linhas são lidas sob o mesmo snapshot somente leitura REPEATABLE READ; evita cursor com geração antiga e dados novos. Para histórico operacional, congelar limite superior de início na primeira página; novas execuções não entram, enquanto status existentes podem mudar. Não prometer snapshot imutável de status operacional.

## 11. Cache

Redis entra no M2. M1 consulta PostgreSQL diretamente. Geração persistida em ops.publicacao é autoridade; não usar apenas contador Redis.

    v1:{dominio}:{core|gold}:{geracao}:{rota}:{hash_parametros_cursor}

| Resposta | TTL inicial |
|---|---|
| Catálogos | 3600 s |
| Agregados | 900 s |
| Observações paginadas | 300 s |
| Frescor | 15 s |
| Execuções/probes/erros | Sem cache |

- Parâmetros canônicos incluem filtros, ordenação, limite e cursor. Geração/consulta usam mesmo snapshot conforme seção 10.
- Mudança core/gold muda geração no banco. Chaves antigas expiram; reinício Redis não ressuscita versão antiga.
- Estado de publicação entra na identidade/validação do cache gold: nova carga pendente não pode manter resposta desatualizado=false.
- Redis indisponível: timeout de conexão/operação até 200 ms, sem retry por requisição; fallback para banco, log e métrica.
- Stampede: TTL com jitter de até 10% e lock curto por chave, sem espera indefinida.
- ETag de representação/geração, If-None-Match/304 após verificar versão. Dados públicos com Cache-Control: public, max-age=0, must-revalidate; operação/probes no-store.
- Rate limit público inicial de 100 requisições/minuto/cliente. M1: processo local; M2: Redis centralizado, com limite local de contingência se cair. Documentar que fallback local não é limite global entre réplicas; gateway M3 pode impor camada adicional.

## 12. Observabilidade

Logs JSON via structlog: timestamp UTC, nível, serviço, evento, IDs de request/execução/etapa/lote quando aplicáveis, fonte, tentativa, duração, contagens e erro sanitizado. Não registrar secrets nem payload completo por padrão.

Distinguir última consulta bem-sucedida, último período de referência e última publicação. Série mensal não é obsoleta simplesmente porque não mudou em 24h.

| Conjunto | Política inicial |
|---|---|
| BCB diário | Alerta após mais de 4 dias corridos sem observação; conferir feriados/calendário |
| IPCA | Calendário oficial homologado; fallback heurístico de 45 dias desde início do mês de referência, identificado como heurística |
| Localidades | Alerta após 14 dias sem coleta bem-sucedida |
| População | Consulta há menos de 35 dias; comparar último ano descoberto e carregado, sem exigir nova população mensal |
| Publicação | Alerta se versao_core>versao_gold por mais de 1h após carga |

Limiares são escolhas operacionais, não SLAs oficiais. Calendário arquivado prevalece sobre heurística; documentar ausência de calendário.

M2: métricas de latência, erros, cache, duração por fase, rejeições, retries, contagens, cobertura e frescor. Labels somente de baixa cardinalidade: rota parametrizada, fonte, fase, status; IDs detalhados nos logs.

Jobs curtos: exporter estável lê estado final em ops; evitar depender de processo encerrado para scrape. Três dashboards: API, pipeline e frescor/cobertura. Demonstrar alerta local provocado no Grafana. Webhook externo e Sentry opcionais, não bloqueiam aceite local.

## 13. Testes e desempenho

### Casos obrigatórios

| Grupo | Cenários |
|---|---|
| Contrato/unidade | Datas/Decimal, IPCA negativo, não finitos, campo ausente/extra, envelopes, marcadores IBGE, cobertura e duplicata conflitante |
| HTTP | 500→sucesso; 429 com segundos/data; espera além do orçamento; timeout; 404 sem retry; JSON inválido preservado |
| Banco | Migração vazia, constraints/grants, upsert sem alterar metadados, revisão de valor, rollback e watermark sem salto |
| Falhas | Bronze persistido antes de interrupção; core confirmado antes de refresh; falha entre MVs; Redis cai na publicação |
| Concorrência | Dois loaders respeitam lock; domínios independentes; paginação durante atualização expira cursor corretamente |
| Replay | Reconstrução isolada sem rede; checksum inválido bloqueia; arquivo antigo não regride produção |
| API | Filtros/erros, navegação completa, cursor adulterado/trocado/vencido, limites, vazio, probes e sanitização |
| Cache M2 | Hit/miss, gerações core/gold, publicação pendente, Redis reiniciado/indisponível e 304 correto |
| Fluxo | Fontes simuladas, status global correto e publicação incompleta bloqueada |

Fixtures oficiais pequenas; suíte/CI sem internet. PostgreSQL/Redis reais via Compose/Actions; filesystem temporário M1, teste adapter MinIO M2. Sondagem oficial manual separada dos testes automatizados.

Cobertura >=85% global e >=95% nos módulos de validação, indicadores, carga e paginação. CI verifica ambos explicitamente; percentual global não prova meta por módulo. Não criar testes que apenas reproduzem implementação.

### Benchmark

M1 executado em 18/11/2026: [ambiente, protocolo e resultados](docs/desempenho/2026-11-18-m1-local.md). Meta local atingida no workload documentado. M2 sintético/cache executado em 19/11/2026 e otimizado após diagnóstico: [investigação e resultados finais](docs/desempenho/2026-11-19-otimizacao-sem-cache.md); metas com e sem cache atingidas no protocolo documentado. Ensaio de saturação não realizado.

M1 mede consultas reais e planos, sem exigir ganho artificial de MV em dados pequenos. M2 usa banco sintético separado com 1 milhão de observações, seed/índices reproduzíveis; dados sintéticos nunca são apresentados como oficiais.

Registrar CPU, RAM alocada ao Docker, versões, dataset e workers. Aquecer 30 s; medir 60 s, concorrência 10, páginas de 100 itens. Metas iniciais locais: p95<=500 ms sem cache, <=250 ms com cache, 5xx<1%; validar antes de anunciar resultados. Não são SLA de hospedagem gratuita.

Comparar keyset no começo/meio/fim com OFFSET e EXPLAIN (ANALYZE, BUFFERS). Não afirmar custo absolutamente constante; registrar plano e comportamento medido em docs/desempenho. Carga não roda a cada commit.

## 14. Windows, Docker e configuração

### Preparação

1. Conferir build/arquitetura Windows, virtualização, requisitos atuais do Docker e espaço livre. Reservar inicialmente 20 GB como orçamento do projeto, não mínimo oficial universal.
2. Instalar/atualizar WSL 2 e Docker Desktop conforme documentação oficial; reiniciar quando necessário. São tarefas futuras, não ações feitas nesta revisão.
3. Usar backend WSL 2 e containers Linux; conferir permissões e licença aplicável ao uso pessoal.
4. Validar no PowerShell: wsl --status, wsl --version, docker version, docker compose version e docker run --rm hello-world.
5. Instalar Git/uv; disponibilizar Python 3.12; validar versões e ambiente do projeto.
6. Documentar comandos PowerShell como caminho principal; Makefile/Bash opcionais.

Referências: [Docker para Windows](https://docs.docker.com/desktop/setup/install/windows-install/) e [WSL 2](https://docs.docker.com/desktop/features/wsl/).

Orçamento inicial de 6–8 GB para containers/WSL, ajustável por medição na máquina de 32 GB; não é mínimo oficial. Manter D:\pipeline-etl inicialmente; migração para filesystem WSL somente se desempenho justificar e for explicitamente planejada.

### Perfis Compose

| Perfil | Serviços |
|---|---|
| Padrão M1 | PostgreSQL, migrate e API; volume bronze |
| pipeline M1 | Prefect server/worker |
| cache M2 | Redis |
| storage M2 | MinIO e inicialização idempotente de bucket/política |
| monitoring M2 | Prometheus, Grafana, exporter |

Docker compose up --build entrega banco migrado e API; demonstração completa usa comando de perfis explícito no README. Inicializar diretórios, seeds e permissões idempotentemente. Migrate único termina antes da API; API não migra por worker.

Redis opcional não bloqueia startup/readiness. MinIO obrigatório apenas quando backend S3 selecionado. Prefect usa banco e credenciais separados do negócio; documentar healthchecks, deployment e worker conforme versão fixada.

Dockerfile reproduzível com lock, usuário não root e cópia de pacote, migracoes, alembic.ini e sql. SQL legível pelo usuário da imagem; escrita apenas em volumes necessários. Dockerignore exclui .env, venv, bronze, backups e caches; secrets fora da imagem.

Persistir banco/bronze/MinIO e configuração necessária dos dashboards. Portas administrativas somente em 127.0.0.1 no host; em produção não expor banco, Redis ou consoles/UI diretamente.

### Configuração mínima a implementar

.env.example inclui valores de desenvolvimento e instruções, sem secrets reais:

    AMBIENTE=desenvolvimento
    TZ=America/Sao_Paulo
    URL_BANCO_API=postgresql+psycopg://api_leitura:SENHA_LOCAL@db:5432/etl
    URL_BANCO_PROCESSAMENTO=postgresql+psycopg://processamento:SENHA_LOCAL@db:5432/etl
    URL_BANCO_MIGRACOES=postgresql+psycopg://migracoes:SENHA_LOCAL@db:5432/etl
    ARMAZENAMENTO_BRONZE=arquivos
    CAMINHO_BRONZE=/data/bronze
    SERIES_BCB=432,433,1
    INICIO_HISTORICO_PUBLICO=2020-01-01
    REDIS_HABILITADO=false
    URL_REDIS=redis://redis:6379/0
    CHAVE_ASSINATURA_CURSOR=GERAR_LOCALMENTE_NAO_VERSIONAR_VALOR_REAL
    LIMITE_REQUISICOES_API=100/minute
    NIVEL_REGISTROS=INFO

Adicionar publicador, Prefect/S3 na fase pertinente. Settings validam campos condicionais, recusam placeholder inseguro em produção e não exigem serviço desativado. URLs de host e container são distintas; documentar ambas para testes e comandos locais.

## 15. CI e segurança

CI a implementar:

1. Python/uv e actions fixados; uv sync --frozen com dependências dev.
2. Ruff check/format, mypy, bandit e auditoria das dependências instaladas conforme lock.
3. PostgreSQL saudável; provisionar papéis de teste; Alembic do zero; seeds/grants; downgrade/upgrade de mudanças reversíveis.
4. Pytest offline com cobertura global e por módulos; Redis/MinIO somente nos jobs M2 pertinentes.
5. Build e smoke test da imagem real: migracoes/SQL disponíveis, probes, permissões e volumes.
6. Deploy M3 em workflow separado com secrets. Build aprovado não significa publicação realizada.

Segurança: SQL parametrizado, credenciais por serviço, CORS allowlist (não autenticação), rate limit, limite de período/página, statement_timeout API inicial 5 s e timeout próprio mais longo para carga/refresh. Pool API inicial de 5 conexões + até 5 extras; revisar total por worker e quota do provedor.

API sem DDL/DML; publicador e migrador não são usados pela API. Views ops públicas sanitizadas. Metrics/UIs privadas. Em proxy, confiar apenas em forwarded headers de proxies conhecidos para identificar cliente.

.env, bronze e backups fora do Git; fixtures pequenas com licença/origem. Licença proposta do código MIT, atribuição dos dados separada. Dependabot/equivalente e atualizações avaliadas no CI; auditoria sem achados não garante ausência de risco.

## 16. Retenção, backup e deploy

### Retenção e recuperação

- Bronze aceito e manifestos de promoção durante a vida do projeto; sem expurgo automático nesta versão. Alertar em 5 GB e revisar orçamento antes de novas fontes.
- Quarentena/diagnósticos detalhados: 90 dias. Preservar metadados/checksums necessários ao lineage pelo tempo de vida dos fatos.
- Local: pg_dump antes de migração relevante e ao fim de sessão com alteração de dados; 7 cópias recentes, uma fora do volume Docker.
- Produção: backup diário e pré-migração, storage separado e acesso restrito; conferir compatibilidade com quotas gratuitas.
- M3: metas RPO 24h/RTO 4h, sujeitas a ensaio real de restore, sem garantia de provedor.
- Restaurar primeiro em banco isolado; conferir schema, contagens, amostras, checksums, cobertura, MVs e API. Sem backup, reconstruir pelo bronze em ordem documentada.
- Não usar docker compose down -v como recuperação: remoção de volumes é destrutiva.

### Deploy após M2

Nenhum provedor/conta contratado ou gratuito garantido. Avaliar oficialmente na fase M3: imagem Python, Postgres/grants/MVs, conexões, pooling, agendamento, hibernação, objetos duráveis, egress/quotas, secrets, backup, TLS, região e cartão.

Candidatos a reavaliar: Render/equivalente, Neon/Supabase, Upstash e storage S3 compatível. Validar protocolos/TLS e SDKs, sem presumir compatibilidade de toda modalidade Redis/S3 oferecida.

GitHub Actions schedule + workflow_dispatch pode chamar CLI/flow sem UI Prefect local. Cron UTC documentado, concorrência limitada e bronze externo antes de runner encerrar. Schedule pode atrasar; incremental recupera períodos perdidos.

Aceite: secrets, migração única/grants, smoke, carga inicial, probes, HTTPS, armazenamento durável, alerta de frescor, backup/restore, cold start e rollback de imagem compatível com schema. Migração destrutiva exige restauração planejada, não downgrade cego.

Sem composição gratuita viável, documentar bloqueio e manter M2 local. Não declarar v1.0 publicada nem contratar plano pago automaticamente.

## 17. Fases e critérios de aceite

Tarefas preferencialmente em sessões de 1–2h. Encerrar sessão registrando evidência e próximo passo no checklist. Testes acompanham sua fase.

| Fase | Entregáveis | Pronto quando |
|---|---|---|
| 0 — Descoberta | BCB real/fixtures/termos; IBGE homologado ou pendência explícita; ADR escopo | BCB homologado, IBGE sem bloquear M1 |
| 1 — Ambiente/base | WSL/Docker; Git/uv/Python; pacote/CLI/settings/logs; Compose e CI básico | Docker hello-world e Postgres saudáveis, pacote importável e checks verdes |
| 2 — Banco | Alembic, papéis, ops/core, staging, seeds e MVs BCB | Migração vazia e permissões reais testadas |
| 3 — Extração | Cliente/retries, filesystem, artefatos/manifestos/checksums | Corpo preservado antes de parse, falhas simuladas verificadas |
| 4 — Qualidade/carga | Contratos, quarentena, Decimal, locks, incremental/backfill, replay | 2 execuções não alteram fatos/metadados; falha não salta checkpoint; reconstrução isolada |
| 5 — Gold/API/M1 | Indicadores, publicação recuperável, rotas/cursores, Prefect, frescor, docs | Histórico 2020+, IPCA jan/2020 calculável, DoD M1 atendido |
| 6 — IBGE/M2 | Metadados, localidades, estimativas, base territorial, cobertura, rotas/MVs | Lacunas/ausências explícitas; nenhum total incompleto apresentado como completo |
| 7 — Cache/storage | Redis/geração/ETag, adapter S3/MinIO e inicialização | Sem cache de geração incorreta, fallback funciona, adapters suportam replay |
| 8 — Operação/M2 | Métricas/dashboards, alertas locais, benchmark, backup/restore e runbook | Falha provocada rastreável, restore conferido, DoD M2 atendido |
| 9 — Publicação/M3 | Provedores, secrets, storage externo, deploy, schedule, backup e README | API pública real, operação verificada, DoD M3 atendido |

Não exigir dashboards para entregar M1. Não implementar conector IBGE antes de homologar metadados. Teste hello-world não comprova integridade ETL.

## 18. Definition of Done

### M1 — BCB local

- [x] Setup PowerShell/Docker reproduzível; banco, migrações, seeds e API sobem pelo README.
- [x] Três séries homologadas para o protótipo local, com histórico público 2020+ e apoio IPCA separado; termos e limites conforme [decisão de escopo](docs/decisao-aceite-local-m1-m2.md). Não declara licença nominal individual.
- [x] Bronze antes de parse, manifestos/checksums e lineage.
- [x] Contratos/quarentena BCB; nenhuma promoção silenciosa de lote incompleto. Preparação e promoção BCB implementadas na etapa seguinte; ver docs/carga-bcb.md.
- [x] Idempotência inclusive metadados; incremental/backfill/revisão, locks e checkpoints testados.
- [x] Replay isolado sem rede, com 49 promoções e comparação de fatos/cobertura/linhagem/gold/HTTP; restauração completa do dump em outro banco também verificada. Evidências: docs/recuperacao-local-m1.md.
- [x] Recuperação após refresh falho consolidada em [runbook](docs/runbook.md), com ensaio isolado e publicação transacional conferidos.
- [x] Gold mensal/anual/IPCA 12m corretos; cursores assinados/vinculados à geração.
- [x] Rotas M1, probes, rate limit local, usuário read-only, logs e frescor.
- [x] Execução manual/agendada local documentada com limitação de PC desligado.
- [ ] CI remoto adiado; cobertura por módulo, permissões, smoke da imagem e documentação local foram aprovados. Execução no GitHub não foi realizada.

- [x] Referências mensais IPCA no recorte conferidas em 23/11/2026:93/93, incluindo 82 públicas e11apoio de 2019; nenhuma referência faltante/inesperada. [Evidência e limites](docs/conferencia-fontes-2026-11-23.md). Não implica licença nominal ou calendário do dólar homologados.

- [x] Histórico do dólar confrontado com a API oficial PTAX em 23/11/2026: 1.728/1.728 datas de 02/01/2020 a 19/11/2026, sem divergências; 68 dias de semana sem cotação classificados nos calendários anuais ANBIMA. [Evidências e limites](docs/conferencia-dolar-2026-11-23.md).
- [x] Critério documental local ajustado pelo responsável em 23/11/2026: seguir sem solicitação de autorização individual, preservando atribuição, proveniência e limites conhecidos dos termos. [Decisão registrada](docs/decisao-aceite-local-m1-m2.md). Não equivale a obter resposta ou licença individual.

### M2 — Local completo

- [x] DoD M1 aceito no escopo local ajustado: base técnica verificada, referências IPCA e histórico do dólar conferidos. Solicitação individual dispensada expressamente pelo responsável; CI remoto transferido para publicação. [Decisão e limites](docs/decisao-aceite-local-m1-m2.md).
- [x] IBGE homologado; estimativas sem mistura com censo; lacunas explícitas.
- [x] Associações territoriais rastreáveis, cobertura e totais derivados documentados.
- [x] Rotas IBGE e publicação gold independentes de BCB.
- [x] Redis com fallback, gerações, stampede e ETag corretos.
- [x] Filesystem/S3 com mesmo contrato; MinIO local e inicialização repetível validados. Evidências e limites em [armazenamento S3 local](docs/armazenamento-s3-local.md).
- [x] Três dashboards e alerta local provocado demonstrados.
- [x] Benchmark e backup/restore documentados com resultados reais.
- [x] Demonstração completa em até 15 minutos após pré-requisitos e imagens disponíveis na máquina de referência; instalação inicial Docker não entra nessa meta.

Entrega técnica local verificada em 23/11/2026:588 testes/95,80%,15 módulos críticos>=95%, demo125,359 s, backup/restore entre datas e observabilidade completa. [Evidências e ressalvas de aceite](docs/aceite-tecnico-m2.md). CI remoto adiado conforme decisão do responsável; não se alega execução no GitHub. O aceite do escopo local foi ajustado por decisão expressa do responsável; ver docs/decisao-aceite-local-m1-m2.md. Isso não valida implantação pública.

### M3 — Publicado

- [ ] DoD M2 e decisão datada de provedor/limites.
- [ ] HTTPS/Swagger público, dados reais e operação sanitizada.
- [ ] Agendamento independente do PC, objetos duráveis e migração controlada.
- [ ] Administração privada, secrets e limites operacionais.
- [ ] Backup/restore externo demonstrado; quotas/hibernação documentadas.
- [ ] README com problema, arquitetura, demo, comandos, resultados e limitações.
- [ ] Changelog/tag v1.0.0 após verificação.

Sentry, front-end, dbt, tracing, particionamento e exportação Parquet não bloqueiam marcos.

## 19. Cronograma

Estimativas de planejamento, não datas prometidas. Incluem desenvolvimento assistido, leitura, testes e documentação; aprendizado/ambiente podem ampliar o calendário.

| Fase | Esforço |
|---|---|
| 0 — Descoberta | 4–6h |
| 1 — Ambiente/base | 6–10h |
| 2 — Banco | 6–10h |
| 3 — Extração | 6–10h |
| 4 — Qualidade/carga/replay | 10–16h |
| 5 — Gold/API/operação | 16–24h |
| Subtotal M1 | 48–76h |
| 6 — IBGE | 12–20h |
| 7 — Cache/storage | 6–10h |
| 8 — Observabilidade/recuperação | 10–16h |
| Adicional M2 | 28–46h |
| 9 — Deploy/M3 | 8–14h |
| Total base | 84–136h |
| Reserva de 25% | 21–34h |
| Total planejado | 105–170h |

| Entrega acumulada com reserva | Horas | A 4h/semana | A 2h/semana |
|---|---|---|---|
| M1 | 60–95h | 15–24 semanas | 30–48 semanas |
| M2 | 95–152,5h | 24–39 semanas | 48–77 semanas |
| M3 | 105–170h | 27–43 semanas | 53–85 semanas |

Semanas arredondadas para cima. A 3h/semana, M1 corresponde a 20–32 semanas; projeto completo, 35–57 semanas. Reestimar após Fase 1 e primeira carga real BCB. A previsão anterior de 6–8 semanas não é adequada ao ritmo informado.

Sugestão de rotina: duas sessões de 1h como base; quando possível, outra de até 2h. Um próximo passo verificável por sessão. Não manter múltiplas fontes incompletas em paralelo.

## 20. Documentação, riscos e próximos passos

### Documentação por fase

- README: problema, escopo/marcos, setup PowerShell, Compose/perfis, comandos CLI, testes, demo e limitações.
- docs/escopo.md e docs/fontes.md: preferências, fora de escopo, contratos e evidências oficiais datadas.
- docs/modelagem.md: ER físico, chaves, lineage, permissões, MVs e EXPLAIN.
- docs/api.md: unidades, exemplos, vazio/erros, cursor/409, cobertura e versionamento.
- docs/runbook.md: iniciar/parar, catch-up, falhas, publicação pendente, replay isolado, restore e revisão/exclusão auditada.
- docs/decisoes/: decisões e consequências. docs/desempenho/: protocolo, ambiente e resultados reais versus sintéticos.

### Riscos

| Risco | Tratamento |
|---|---|
| Poucas horas semanais | Marcos locais, sessões curtas e reestimativa |
| Docker/WSL ausentes | Fase explícita de instalação/aceite |
| Fonte indisponível/drift | Fixtures, retry limitado, bronze e bloqueio de promoção inválida |
| IBGE não homologado | Bloquear apenas conector IBGE, preservar M1 |
| Mudança territorial/metodológica | Snapshot/indicador/base no fato; sem comparabilidade implícita |
| Revisão fora da janela | Reconciliação integral e exclusão auditada |
| Falha core/gold/cache | Gerações persistidas, transação de publicação e recuperação |
| Quota gratuita/storage insuficiente | Reavaliar no deploy, alertar volume, sem contratação automática |
| Números sem medição | Publicar desempenho/tempos apenas após ensaio |

### Próximo passo

API FastAPI M1 implementada e verificada; ver docs/api.md. Carga histórica real e ensaio ponta a ponta concluídos; ver docs/historico-real-m1.md. Calendário IPCA 2026 conferido manualmente (docs/calendario-ipca.md), restauração e replay isolado verificados (docs/recuperacao-local-m1.md). Avaliação automática de frescor por calendário com vigência/fallback implementada e verificada; ver docs/calendario-ipca.md. Benchmark local conforme protocolo medido (p95 149 ms, aproximadamente 101 requisições/s, zero erros na mistura); ver docs/desempenho/2026-11-18-m1-local.md. Orquestração local implementada e verificada em 19/11/2026, com agendas/retomada e inicialização no logon; ver docs/orquestracao-local.md. Próximo passo: consolidar runbook e conferir critérios finais do M1, sem presumir conclusão global. Indicadores e publicação gold BCB verificados; ver docs/indicadores-e-publicacao.md. Coleta incremental/reconciliação por CLI implementadas e testadas; execução com histórico real completo confirmada; agendamento permanece pendente. Ver docs/incremental-bcb.md. Transformação/carga, preparação transacional, locks e checkpoint foram implementados e verificados; ver docs/carga-bcb.md. Contratos/quarentena e auditoria SQL foram verificados; a Fase4 completa ainda depende da carga e dos testes de retomada. Evidências em docs/validacao-e-quarentena.md.

- [x] Conferir Windows/virtualização/requisitos e preparar Docker/WSL; hello-world verificado.
- [x] Executar verificações Docker e registrar versões/saída em docs/ambiente-local.md.
- [x] Salvar resposta JSON real de cada série BCB com metadados; termos pendentes separados em docs/fontes.md.
- [x] Confirmar unidade/periodicidade e resposta inicial de 432, 433 e 1.
- [x] Registrar metadados e períodos IBGE; valores/termos ainda pendentes, sem bloquear BCB.
- [ ] Concluir Fase 1: Git, pacote, lock, configuração/registros/CLI/testes e workflow de qualidade criados; PostgreSQL/Compose locais verificados; CI remoto ainda aguarda publicação autorizada.

Distinguir escolhas técnicas registradas de homologações pendentes. Não repetir perguntas de escopo já respondidas nem marcar tarefas concluídas sem evidência de execução.

## Candidata de hospedagem — 23/11/2026

Oracle Cloud Always Free selecionada para avaliação pelo responsável. Roteiro de
criação de servidor, gratuidade e ociosidade em docs/oracle-cloud-always-free.md.
Nenhuma conta/VM criada; capacidade, imagens ARM e migração Linux ainda não validadas.
