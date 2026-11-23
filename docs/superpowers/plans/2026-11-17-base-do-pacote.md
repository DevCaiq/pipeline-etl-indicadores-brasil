# Plano de execução — Base do pacote Python

> Executar com superpowers:executing-plans, preservando o escopo aprovado e TDD.

Objetivo: pacote instalável pipeline_etl, configuração tipada, registros estruturados e CLI inicial, sem implementar banco ou HTTP nesta etapa.
Arquitetura: configuracao.py usa pydantic-settings; registros.py configura structlog em stderr; comandos.py valida e imprime resumo JSON em stdout. __main__.py permite python -m pipeline_etl.
Stack: Python 3.12, uv, hatchling, pydantic-settings, structlog, pytest, Ruff, mypy e bandit.
Especificação: plano-pipeline-etl-api.md, Fase 1; AGENTS.md e solicitação para seguir ao próximo passo.

## Restrições globais

Identificadores próprios/documentação português-BR; não adicionar ETL/banco/API prematuramente. Manter amostras oficiais e arquivos existentes. Não publicar nem alterar identidade Git. Dependências travadas em uv.lock.

## Revisão focada

- Variável de ambiente inválida ou arquivo .env ausente: validar ou aceitar padrões, sem segredos na mensagem de erro.
- CSV de séries BCB vazio/desconhecido/duplicado: rejeitar; permitir seleção de subconjunto e espaços.
- Reconfiguração de logging e nível: não duplicar eventos nem vazar configuração; JSON UTF-8 em stderr.
- Execução módulo/entrypoint: stdout JSON válido, stderr separado; código 2 para configuração inválida.
- Instalação reprodutível: uv sync --frozen e wheel executável fora da árvore de fontes.

## Tarefa 1 — Configuração e pacote

Arquivos: pyproject.toml, uv.lock, .python-version, src/pipeline_etl/configuracao.py, testes/unidade/test_configuracao.py e testes/conftest.py.
Interface: ConfiguracaoAplicacao com ambiente, nivel_registros, caminho_bronze e series_bcb. Campos em português; ambiente desenvolvimento/teste/producao; séries permitidas 432/433/1; nenhum segredo exigido antes de existir consumidor.
- [x] Escrever testes para env/.env e validações; observar falha antes da implementação.
- [x] Implementar configuração sem efeitos de criação de pasta/rede.
- [x] Executar testes e confirmar sucesso.

## Tarefa 2 — Registros e comando

Arquivos: registros.py, comandos.py, __main__.py; testes/unidade/test_registros.py e testes/unidade/test_comandos.py.
Interfaces: configurar_registros(nivel: str) -> None; executar(argumentos: Sequence[str] | None = None) -> int.
- [x] Escrever testes de JSON em stderr, nível, reconfiguração e CLI válida/inválida.
- [x] Observar falhas e implementar comando verificar-configuracao com saída pública limitada.
- [x] Verificar stdout/stderr separados e executar módulo/entrypoint reais.

## Tarefa 3 — Ferramentas e documentação

Arquivos: .env.example, .pre-commit-config.yaml, .github/workflows/qualidade.yml, README.md, docs/ambiente-local.md.
- [x] Conferir Ruff, mypy, bandit, auditoria, cobertura e build.
- [x] Instalar wheel isolado e executar entrypoint fora do diretório do projeto.
- [x] Documentar comandos reproduzíveis e pendências de PostgreSQL/Compose/API.

Não criar testes de texto de configuração/documentação; verificar ferramentas e artefatos reais. Sem novos testes de dados externos nesta etapa.

## Evidências de execução

- Instalação em .venv com Python 3.12.3; lock de 63 pacotes, build hatchling fixado pelo grupo dev.
- TDD: testes iniciais falharam por ausência dos três módulos; após implementação, 19 passaram.
- Regressão Unicode: teste de comando real sob ASCII falhou antes da correção JSON; depois, 20 passaram.
- Revisão independente da base: nenhum achado crítico/importante; ajuda sob ASCII identificada e reproduzida com dois testes falhando. Fluxos TextIOWrapper da CLI passaram a usar UTF-8; suíte completa 22/22 passou.
- Cobertura global 94%, configuração 100%. __main__ foi exercitado em subprocess e no smoke do wheel; subprocess não soma cobertura automaticamente.
- Dependências auditadas sem vulnerabilidades conhecidas na consulta; comandos de qualidade e build verificados localmente. Workflow CI preparado, não executado remotamente.
- Wheel instalado em .cache/verificacao-pacote; console e módulo executados com cwd temporário fora do projeto; import veio de site-packages. Artefatos inspecionados sem .env, dados, .cache ou .venv.
- Tentativa de instalar wheel usando só cache offline não encontrou um wheel nativo; instalação online concluiu. Restrição offline refere-se à suíte, não ao bootstrap.
- Pre-commit validado com PRE_COMMIT_HOME no workspace devido à restrição de escrita no cache pessoal do sandbox. Hook não instalado automaticamente.

Decisões: somente configurações consumidas nesta etapa; sem URL de banco/Redis/chaves exigidas antecipadamente. Sem criação de pasta bronze como efeito de instanciar settings. Sem commits ou publicação nesta etapa, preservando os arquivos anteriores ainda não rastreados.
