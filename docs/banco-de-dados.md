# PostgreSQL local com Docker

Etapa verificada em 18/11/2026. PostgreSQL 16.16 executa no Docker Desktop, sem instalar servidor ou cliente PostgreSQL no Windows. Não é preciso criar conta de serviço PostgreSQL. Login Docker é opcional para este uso local com imagens públicas; políticas corporativas podem exigir login.

Referências oficiais: [imagem PostgreSQL](https://hub.docker.com/_/postgres) e [política de login Docker](https://docs.docker.com/desktop/enterprise/enforce-sign-in/).

## Estado entregue

- Container banco saudável; endereço 127.0.0.1:55432, banco etl.
- Volume nomeado pipeline-etl_dados_postgres: catálogo continuou disponível após reinício e recriação do container.
- Serviço pontual migracoes executa Alembic como usuário não root, UID 10001.
- Imagens PostgreSQL e Python fixadas por digest; dependências Python por uv.lock.
- Revisão 0001 aplicada e reaplicada sem duplicar dados; alembic check não encontrou diferença entre modelos e schema.
- Suíte completa: 45 testes aprovados, incluindo permissões e transações reais; cobertura global 97,04%, configuração 100%.
- Não há API, coleta BCB de produção ou views materializadas nesta etapa.

## Iniciar e migrar

Abra Docker Desktop, aguarde o engine ativo e execute no PowerShell da pasta do projeto:

    docker compose --env-file .env.banco up -d --wait banco
    docker compose --env-file .env.banco run --build --rm migracoes
    docker compose --env-file .env.banco ps

O arquivo .env.banco desta máquina já foi gerado com senhas aleatórias distintas e não está no Git. Não precisa substituí-lo para executar os comandos. O banco está iniciado ao término desta etapa.

Em outra máquina/clonagem, crie .env.banco antes de iniciar. O comando abaixo usa criação exclusiva: recusa sobrescrever um arquivo existente.

    uv run python -c "from secrets import token_hex; nomes=['ADMIN','MIGRACOES','PROCESSAMENTO','API','PUBLICADOR']; open('.env.banco','x',encoding='utf-8').write(''.join('SENHA_BANCO_'+nome+'='+token_hex(24)+'\n' for nome in nomes))"

.env.banco.example documenta os campos; seus placeholders não são credenciais de uso. O arquivo de infraestrutura é separado de .env, usado pela aplicação. Não copiar senhas para README, código, imagem ou saída de comandos.

## Papéis e schemas

| Papel | Responsabilidade |
|---|---|
| administrador | Bootstrap do cluster e preparação do banco exclusivo de testes; não usado pela aplicação |
| migracoes | Dono do banco/schemas de negócio, aplica revisões Alembic |
| processamento | SELECT/INSERT/UPDATE/DELETE em core/ops, sem permissão de criar tabelas |
| api_leitura | SELECT em core/mart e na view sanitizada ops.v_execucoes, sem escrita nem acesso à tabela operacional com erros internos |
| publicador | Proprietário de mart; reservar para futuras views materializadas |

Bootstrap cria papéis/ownership apenas no volume vazio; Alembic cria objetos do projeto e permissões. Migrações futuras que criarem MVs devem usar o papel publicador para manter ownership coerente. As permissões padrão foram preparadas para objetos futuros, mas cada nova migração deve ser testada.

Schemas/tabelas iniciais:

- ops.execucao: identificação, modo, situação, parâmetros e diagnóstico da execução.
- ops.lote: execução, fonte, chave, janela e manifesto bronze de origem.
- core.dim_serie: Meta Selic 432, IPCA 433 e dólar venda 1, com unidade e início público.
- core.fato_serie: chave (codigo_sgs, data), valor NUMERIC(24,10), lote FK e alteração UTC.
- mart: schema reservado; nenhuma MV criada prematuramente.

UUIDs, chaves estrangeiras, janela válida, situações permitidas e NaN rejeitado estão definidos no banco. O processamento futuro fará validações adicionais e carga idempotente; esta etapa não implementa esses serviços. A revisão0002 acrescenta auditoria de qualidade em ops.etapa, ops.artefato e ops.quarentena; detalhes em [validação](validacao-e-quarentena.md). O modelo IBGE permanece para revisão posterior.

## Conexão e inspeção

No Windows: host 127.0.0.1, porta 55432, banco etl. Na rede Compose: host banco, porta 5432. Para uma ferramenta de consulta, usar api_leitura e a senha correspondente do arquivo local.

Não precisa instalar psql no Windows:

    docker compose --env-file .env.banco exec banco psql -U administrador -d etl

Consultas de inspeção:

    SELECT codigo_sgs, nome FROM core.dim_serie ORDER BY codigo_sgs;
    SELECT version_num FROM alembic_version;

URLs opcionais da aplicação usam postgresql+psycopg e SecretStr; não aparecem no resumo público de configuração. No Compose, host e senha do migrador são passados separadamente; SQLAlchemy URL.create codifica caracteres reservados como @, /, : e %. Não montar URL por concatenação de senha.

## Testes

Somente testes sem banco:

    uv run --frozen pytest -m "not integracao"

Suíte completa com cobertura:

    uv run --frozen python scripts/testar_banco.py

O script lê credenciais locais, cria etl_testes se necessário e verifica seu proprietário. A fixture aceita exclusivamente esse nome, antes de conectar. O conteúdo desse banco é de teste e inclui downgrade/upgrade; etl e qualquer outro nome são recusados para essas operações.

O script não inicia Docker automaticamente; iniciar banco primeiro. Cobertura global deve ser avaliada com a suíte completa, que exercita modelos/sessões. Sem URL_BANCO_TESTES, testes reais de integração são ignorados; testes de proteção sem conexão continuam disponíveis.

Não há chamadas a APIs externas na suíte. Instalação de dependências, pull de imagens e auditoria de vulnerabilidades podem acessar serviços públicos.

## Operar sem perder dados

    docker compose --env-file .env.banco stop banco
    docker compose --env-file .env.banco start banco
    docker compose --env-file .env.banco logs --tail 50 banco
    docker compose --env-file .env.banco run --rm migracoes alembic current
    docker compose --env-file .env.banco run --rm migracoes alembic check

Stop/start e down sem -v preservam volume. Não usar down -v se deseja manter os dados. Alterar .env.banco após inicializar não altera senhas já gravadas no cluster; rotação exige procedimento explícito com o administrador. Guardar o arquivo local junto ao ambiente e não regenerá-lo sobre um volume existente.

A porta 55432 evita conflito com instalações locais comuns na porta 5432. Alterar a porta requer ajustar Compose e o runner de testes; valores são locais desta arquitetura.

## Escopo seguinte

Coleta incremental BCB e reconciliação conforme o plano. Transformação/carga já foram verificadas com a revisão 0003; ver [guia da carga](carga-bcb.md). Cliente, bronze e validação/quarentena já foram implementados. API e MVs entram em suas fases; esta entrega não marca o M1 completo.

A revisão 0003 está aplicada localmente. Cinco fatos oficiais foram inseridos, e uma segunda carga preservou valores e metadados. Estado de publicação BCB: core1/gold0, PENDENTE. O backup e as verificações estão documentados no guia de carga.

Revisão0004: MVs BCB, função NUMERIC e papel publicador verificados. Estado local core1/gold1 PRONTA, ainda com cinco fatos Selic. Backup e limites em [indicadores/publicação](indicadores-e-publicacao.md). Não equivale a cobertura histórica completa.

Revisões0005/0006: visões sanitizadas da API e revogação da escrita herdada de processamento nessas visões. Esquema final0006; api_leitura acessa dados e metadados selecionados sem acesso às tabelas operacionais privadas. Backups e verificações no [guia da API](api.md).

## Recuperação verificada — 18/11/2026

Estado atual: esquema 0006, histórico BCB com 4334 fatos e gold core 22/gold 22 PRONTA. Backup restaurado em banco novo e replay de 49 promoções confirmado em outro banco, com comparação de dados/catálogo/permissões e API completa. A base etl permaneceu inalterada. Ver [ensaio e comandos](recuperacao-local-m1.md). Evidências antigas acima correspondem às etapas em que foram registradas; a recuperação demonstrada permanece no mesmo cluster, com papéis já existentes.

## Banco do orquestrador — 19/11/2026

Criados prefect_etl e orquestracao_etl, separados do negócio etl. O papel do Prefect não tem CONNECT em etl. Configuração secreta em .env.orquestracao, excluída do Git; preparo é retomável e persiste a credencial antes de alterar recursos. O mesmo container PostgreSQL atende os dois bancos, sem nova migração do negócio (0006). Backup de etl não inclui metadados Prefect. Ver [orquestração local](orquestracao-local.md).
