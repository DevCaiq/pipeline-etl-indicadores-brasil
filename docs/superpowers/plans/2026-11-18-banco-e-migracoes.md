# Plano de execução — PostgreSQL e migrações

Objetivo: PostgreSQL 16 em container, persistência, credenciais locais separadas, papéis restritos e migração inicial para dados BCB. Não instalar servidor PostgreSQL no Windows nem criar conta Docker.
Especificação: plano-pipeline-etl-api.md, AGENTS.md e autorização para seguir ao próximo passo.
Arquitetura: Compose executa banco e serviço pontual migracoes. Bootstrap cria somente papéis/ownership; Alembic cria schemas/tabelas/índices/seeds/grants. SQLAlchemy/psycopg síncronos. Português-BR nos identificadores próprios; env.py, upgrade/downgrade e metadados Alembic preservam interfaces obrigatórias.

## Escopo desta entrega

Schemas ops/core/mart; ops.execucao/ops.lote; core.dim_serie/core.fato_serie; seed 432/433/1; papéis administrador, migracoes, processamento, api_leitura e publicador. Demais tabelas operacionais/IBGE e MVs entram em novas migrações nas fases que as consomem; nenhuma coleta ou API nesta entrega.

## Tarefas

- [x] Testar URLs PostgreSQL opcionais/SecretStr; rejeitar driver inválido sem expor credenciais.
- [x] Implementar configuração e motor/sessão com transações e descarte de conexões.
- [x] Criar Compose com banco em 127.0.0.1:55432, volume nomeado, healthcheck e migrador não root.
- [x] Gerar .env.banco local ignorado, sem mostrar senhas; usar .env.banco.example como referência.
- [x] Testes reais em banco etl_testes, isolado dos dados locais: upgrade, seeds, constraints, rollback, API read-only e processamento sem DDL.
- [x] Observar testes falhando antes de criar modelos/migração; implementar e repetir contra PostgreSQL real.
- [x] Validar downgrade/upgrade somente em banco de testes; não apagar volume ou reverter banco do projeto.
- [x] Atualizar CI com serviço PostgreSQL/roles/migrações, segurança e build.
- [x] Verificar Compose, suíte, tipos, lint, auditoria e documentação operacional.

## Revisão focada

Persistência após reinício; credenciais fora de logs/imagem/Git; inicialização de papéis somente com volume vazio; URLs de host distintas da rede Compose; testes destrutivos bloqueados em banco cujo nome não seja exatamente etl_testes.

## Arquivos

src/pipeline_etl/banco/{__init__,modelos,sessoes}.py; migracoes/env.py, script.py.mako e versions/0001_base_bcb.py; alembic.ini; infraestrutura/inicializar-papeis.sh; compose.yaml; Dockerfile; .dockerignore; .env.banco.example; testes/unidade/test_banco.py; testes/integracao/test_banco.py; docs/banco-de-dados.md; README e CI.

## Evidências e decisões

PostgreSQL 16.16 saudável em 127.0.0.1:55432; revisão 0001 aplicada no banco etl. Catálogo três séries preservado após reinício/recriação sem remover volume. Migrador não root UID 10001; imagens por digest. Alembic check sem diferenças e reaplicação sem duplicação.

TDD: novo campo URL válido falhou antes de existir; primeira integração falhou pela ausência do ambiente de migração; depois 8 testes reais passaram. Suíte ampliada para permissões/Decimal e regressões totaliza 45 testes aprovados; global 97,04%, configuração 100%, modelos/sessões 100%. Ruff/mypy/bandit e auditoria sem achados conhecidos.

Revisão independente identificou URL com senha reservada e proteção de teste ampla demais. Ambos reproduzidos antes da correção: configuração monta URL com URL.create usando host/senha separados; fixture exige exatamente etl_testes antes de conectar. Testes confirmam @/:% e recusa de outro_projeto_testes. Não foi acessado nenhum banco de outro projeto.

A primeira execução conjunta de testes revelou colisão de nomes entre módulos test_banco; pytest agora usa import-mode=importlib sem alterar sys.path do pacote. Pool de teste é descartado em finally inclusive na falha de setup.

Escopo inicial de quatro tabelas confirmado nesta revisão técnica; novas tabelas de artefatos, quarentena, watermark/publicação e IBGE serão novas migrações junto aos consumidores. Sem coleta/API/MVs antecipadas. CI atualizado, ainda não executado no GitHub. Nenhum volume apagado, banco do Windows instalado ou conta Docker criada.
