# Decisão 0001 — Identificadores e documentação em português-BR

Data de referência da sessão: 17/11/2026. Estado: aceita por instrução explícita do responsável.

## Contexto

O responsável pediu classes, funções e demais elementos do projeto em português-BR. Ainda não existe código de aplicação, permitindo adotar a regra desde o início.

## Decisão

Código próprio usa português-BR, sem acentos nos identificadores. Exemplo: ConfiguracaoAplicacao, buscar_serie, codigo_serie, ErroDeColeta, DATA_INICIAL. Comentários/docstrings e mensagens usam ortografia portuguesa normal, com acentos.

Pacote pipeline_etl; módulos configuracao, registros, comandos, banco, processamento, clientes, contratos, armazenamento, transformacoes, fluxos, rotas e esquemas. CLI própria: coletar, reprocessar, publicar, verificar-qualidade. Não criar aliases ingleses redundantes.

## Exceções por interoperabilidade

Preservar sintaxe Python, dunders, imports/parâmetros de bibliotecas, configuração obrigatória de ferramentas, headers HTTP e campos originais externos. Prefixo test_ é convenção pytest: test_buscar_serie. Nomes externos dataInicial/dataFinal do BCB ficam intactos na fronteira; modelos internos usam data_inicial/data_final. Bronze preserva resposta original.

## Consequência

A revisão de código verifica identificadores próprios e documentação. A API planejada terá pagina, limite, proximo_cursor, tem_mais e erro, sem alterar nomes de headers padronizados. Ferramentas (Alembic, Docker, CI) conservam suas chaves obrigatórias.
