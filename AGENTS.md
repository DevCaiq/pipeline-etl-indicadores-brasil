# Instruções do projeto

## Idioma obrigatório

- Todo código próprio deve usar português-BR: classes, funções, métodos, parâmetros, variáveis, atributos, constantes, exceções, módulos e comandos.
- Identificadores sem acentos/cedilha: ExecucaoPipeline, buscar_serie, codigo_serie, ErroDeColeta. Classes PascalCase; demais identificadores snake_case; constantes MAIUSCULAS_COM_SUBLINHADO.
- Comentários, docstrings, mensagens, testes e documentação em português-BR.
- Preservar palavras-chave Python, métodos especiais (__init__, __enter__), interfaces de bibliotecas e contratos de ferramentas/fontes. Não traduzir imports de terceiros artificialmente.
- Arquivos convencionais como pyproject.toml, Dockerfile e compose.yaml mantêm seus nomes. Pytest exige prefixo test_: usar test_buscar_serie e descrições portuguesas.
- Siglas API, BCB, IBGE, HTTP e SQL são permitidas. Dados externos e bronze nunca são alterados para obedecer nomenclatura interna.
- Pacote próprio: pipeline_etl. Testes em testes/, amostras em testes/amostras/.

## Escopo e operação

- Seguir plano-pipeline-etl-api.md. M1 BCB local; M2 IBGE/cache/monitoramento; M3 publicação.
- Python 3.12; uv/uv.lock; PostgreSQL; SQLAlchemy/psycopg síncronos; handlers síncronos com FastAPI.
- Funções de transformação puras; Decimal para medidas; bronze imutável antes do parse; carga idempotente inclusive metadados.
- Testes automatizados não acessam APIs externas; usar as amostras oficiais arquivadas e mocks.
- Não versionar .env, dados brutos operacionais, backups, .venv ou credenciais.
- Não declarar Docker/API/ETL prontos sem execução de verificações. Não publicar contas, repositório remoto ou recursos automaticamente.
- Não sobrescrever amostras oficiais com dados inventados; registrar fonte, parâmetros, instante UTC e SHA-256.
- Escopo já aprovado: 2 a 4 horas semanais, Windows com 32 GB, BCB desde 2020 e apoio IPCA de 2019. Não repetir essas perguntas.
