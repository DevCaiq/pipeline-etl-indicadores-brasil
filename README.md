# Pipeline ETL com API

Portfólio de engenharia de dados e back-end Python. BCB desde 2020 e estimativas IBGE disponíveis desde 2020, com lacunas explícitas. Publicação externa adiada.

## Estado atual

Atualização de 23/11/2026: entrega técnica M2 validada localmente, migração `0010`, 5.571 municípios
e 27.855 registros populacionais nos anos 2020, 2021, 2024, 2025 e 2026.
Replay oficial preservou todos os valores e metadados. Os anos 2022/2023 não foram
fabricados; marcadores `...` permanecem ausentes e tornam o total incompleto.
API BCB/IBGE em http://127.0.0.1:8001/docs, Prometheus em http://127.0.0.1:9090 e
Grafana em http://127.0.0.1:3000. Serviços exclusivamente locais; configuração
privada em `.env.monitoramento`. Grafana usa `administrador` e a senha desse arquivo.
Última revisão pré-GitHub: **591 testes aprovados em cópia limpa**; cobertura da
aplicação **95,80%** na suíte inicial da revisão. Ruff e mypy aprovados.
Backup/restauração BCB e IBGE validado em banco isolado, com 25 consultas da API
e origem preservada; procedimento em [recuperação M2](docs/recuperacao-local-m2.md).
Demonstração completa em **125,36 segundos**, com origem preservada e refresh real no clone.
[Entrega técnica e ressalvas de aceite](docs/aceite-tecnico-m2.md), [demonstração](docs/demonstracao-local-m2.md) e [runbook](docs/runbook.md).
Referências mensais do IPCA conferidas: **93/93**, incluindo 11 de apoio de 2019, sem faltas no recorte. [Conferência documental e histórica](docs/conferencia-fontes-2026-11-23.md).
Histórico do dólar conferido: **1.728/1.728 datas PTAX**, com 68 ausências classificadas; [evidências](docs/conferencia-dolar-2026-11-23.md). Aceite do protótipo local segue sem solicitação individual, conforme [decisão do responsável](docs/decisao-aceite-local-m1-m2.md); atribuição e limites dos termos permanecem documentados. CI remoto ainda não executado. [Roteiro Oracle Cloud Always Free](docs/oracle-cloud-always-free.md), sem implantação na nuvem.
Após otimizar a resolução individual das séries, o benchmark com um milhão de
fatos simulados mediu p95 de **158,75 ms sem cache** e **126,87 ms com cache**,
ambas as metas atingidas, sem erros. API local atualizada.
[Investigação, correção e resultados](docs/desempenho/2026-11-19-otimizacao-sem-cache.md).
MinIO/S3 local validado: bucket privado/versionado, conta restrita e replay IBGE
idempotente com 27.855 registros em banco isolado. [Configuração e evidências](docs/armazenamento-s3-local.md).
Os parágrafos seguintes registram a base M1 anterior; a atualização acima prevalece.

Agendas IBGE ativas no Prefect local: localidades domingo 18h, incremental dia 5
às 20h e reconciliação trimestral dia 1 às 21h, em America/Sao_Paulo.
Execução real e retomada verificadas; [operação IBGE](docs/orquestracao-ibge-local.md).

Base Python implementada: configuração tipada, registros estruturados, coleta BCB resiliente, bronze imutável, validação/quarentena, auditoria SQL, carga BCB idempotente, coleta incremental, reconciliação, indicadores, publicação gold e API FastAPI somente leitura. Dependências travadas em uv.lock; 332 testes locais passaram, com cobertura global de 95,39%, carga 96%, transformação 100%, validador 99% e contrato BCB 100%. Evidências no plano desta etapa. Ruff, mypy, bandit e auditoria de dependências verificados conforme registro da etapa.

Docker/WSL, Python e Git foram preparados anteriormente. Há três amostras oficiais BCB com hashes e metadados IBGE consultados. PostgreSQL 16 está ativo em container, com volume persistente, papéis separados e revisões 0001 a 0006 aplicadas; a coleta bruta por período já foi verificada; contratos de qualidade estão implementados; o recorte BCB desde 2020 foi carregado e atualizado até 19/11/2026: 4.324 observações públicas e 11 meses técnicos de apoio IPCA de 2019; repetição offline e incremental preservaram valores e metadados. Coleta incremental e reconciliação por CLI estão implementadas; gold BCB publicada localmente (core23/gold23, PRONTA). API M1 verificada com todos os dados carregados; restauração e replay offline passaram em bancos separados. Frescor IPCA automatizado por calendário oficial versionado, com vigência e fallback explícitos. Prefect local e worker estão ativos, com banco/ambiente isolados e tarefas de inicialização no logon; execução real e retomada verificadas. O workflow de CI foi criado; execução no GitHub depende de publicar o repositório, o que não foi feito.

## PostgreSQL em Docker

### Preparar uma clonagem nova

Requer Git, Python 3.12, uv e Docker Engine/Desktop com Compose. No PowerShell:

```powershell
git clone https://github.com/DevCaiq/pipeline-etl-indicadores-brasil.git
cd pipeline-etl-indicadores-brasil
uv sync --frozen
uv run --frozen python -c "from pathlib import Path; from secrets import token_hex; nomes=['ADMIN','MIGRACOES','PROCESSAMENTO','API','PUBLICADOR']; Path('.env.banco').open('x',encoding='utf-8').write(''.join('SENHA_BANCO_'+nome+'='+token_hex(24)+'\n' for nome in nomes))"
docker compose --env-file .env.banco up -d --wait banco
docker compose --env-file .env.banco run --build --rm migracoes
uv run --frozen python scripts/preparar_api.py
uv run --frozen pipeline-etl servir
```

A criação exclusiva protege `.env.banco` existente. Abra http://127.0.0.1:8000/docs.
Uma instalação nova contém os catálogos iniciais, sem copiar os dados operacionais
desta máquina. Para os dados reais, execute as cargas documentadas abaixo; API
iniciada não significa histórico coletado. O repositório poderá ficar vazio até o
primeiro envio autorizado.

Para a suíte completa: `uv run --frozen python scripts/testar_banco.py`.
O script usa exclusivamente `etl_testes`, separado do banco `etl`.

Não é necessário instalar PostgreSQL no Windows nem criar conta Docker para este uso local.

    docker compose --env-file .env.banco up -d --wait banco
    docker compose --env-file .env.banco run --build --rm migracoes

Nesta máquina, .env.banco já foi gerado e o banco está ativo em 127.0.0.1:55432. Em outra máquina, seguir a geração de credenciais em [banco de dados](docs/banco-de-dados.md). Dados ficam em volume persistente; não remover volumes para parar o ambiente.

## Executar no PowerShell

Na pasta do projeto, com Python 3.12 e uv disponíveis:

    uv sync --frozen
    uv run --frozen pipeline-etl verificar-configuracao
    uv run --frozen pipeline-etl --ajuda
    uv run --frozen pipeline-etl --versao

Alternativa equivalente:

    uv run --frozen python -m pipeline_etl verificar-configuracao

O comando verificar-configuracao retorna resumo JSON em stdout e registro JSON em stderr. Código 0 indica sucesso; configuração inválida retorna 2 sem exibir o valor recebido. A execução não consulta fontes externas, não testa serviços e não cria diretório bronze: valida somente a configuração desta etapa.

## Coletar BCB no bronze

    uv run --frozen pipeline-etl coletar bcb --serie 432 --inicio 2020-01-02 --fim 2020-01-06

Salva a resposta original, metadados e manifesto em dados/bronze, com SHA-256 e sem sobrescrever execuções anteriores. Pode repetir --serie ou omitir para usar SERIES_BCB. Janelas anuais, retries seletivos e Retry-After são tratados pelo cliente. Ver [coleta e bronze](docs/coleta-e-bronze.md) para limites, saídas e retomada.

COLETADA confirma somente transporte/persistência. A execução não valida medidas nem carrega o banco; leitura do bronze verifica checksum antes de devolver bytes. Esse comando acessa a API oficial, enquanto testes automatizados usam transporte simulado.

## Validar dados

    uv run --frozen pipeline-etl validar bcb --manifesto CAMINHO/manifest.json --credenciais-locais .env.banco

Também é possível acrescentar --validar --credenciais-locais .env.banco ao comando coletar bcb. Veja regras, contagens e recuperação em [validação e quarentena](docs/validacao-e-quarentena.md).

## Carregar dados validados

    uv run --frozen pipeline-etl carregar bcb --manifesto CAMINHO/manifest.json --credenciais-locais .env.banco

A carga usa o bronze existente, bloqueia qualidade incompleta e registra cada tentativa. Repetir valores iguais preserva seus metadados. Veja [carga BCB e recuperação](docs/carga-bcb.md).

## Atualizar e reconciliar

    uv run --frozen pipeline-etl coletar bcb --modo incremental --planejar --credenciais-locais .env.banco
    uv run --frozen pipeline-etl coletar bcb --modo reconciliacao --planejar --credenciais-locais .env.banco

Remover --planejar executa coleta, validação e carga por janela. Sem checkpoint, iniciar pela carga histórica explícita com --carregar. Regras, recuos e retomada estão no [guia incremental](docs/incremental-bcb.md).

## Publicar indicadores gold

    uv run --frozen pipeline-etl publicar --dominio bcb --credenciais-locais .env.banco

O publicador atualiza as três visões BCB em uma transação protegida pela trava da carga. Valores incompletos de IPCA ficam NULL; médias diárias usam somente observações publicadas. Veja [indicadores e publicação](docs/indicadores-e-publicacao.md).

## Consultar pela API

    uv run --frozen python scripts/preparar_api.py
    uv run --frozen pipeline-etl servir

A configuração local .env.api já foi criada com api_leitura e um segredo de cursor. O script preserva arquivos existentes. Após iniciar, abrir http://127.0.0.1:8000/docs. O servidor escuta somente 127.0.0.1. Leia o [guia da API](docs/api.md) para rotas, filtros, paginação e limites.

## Configuração

Os padrões funcionam sem arquivo .env. Para alterar:

    Copy-Item .env.example .env

| Variável | Padrão | Valores aceitos |
|---|---|---|
| AMBIENTE | desenvolvimento | desenvolvimento, teste, producao |
| NIVEL_REGISTROS | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL; aceita minúsculas |
| CAMINHO_BRONZE | dados/bronze | Caminho não vazio; relativo ao diretório de execução |
| SERIES_BCB | 432,433,1 | Subconjunto CSV não vazio dessas séries, sem repetição |

Variáveis de ambiente prevalecem sobre .env. Chaves desconhecidas dentro de .env geram erro para evitar configuração ignorada; variáveis não relacionadas do sistema não interferem. URLs opcionais de banco já são suportadas como SecretStr. Compose usa .env.banco separado; Redis/S 3 entrarão nas próximas fases. Ver documentação do banco para conexão e credenciais.

A configuração é imutável após carga. Só campos explicitamente selecionados entram no resumo. Textos do comando usam UTF-8, e Unicode em JSON pode aparecer escapado para manter compatibilidade com terminais/redirecionamentos. Decodificar JSON recupera acentos normalmente.

## Verificar qualidade

    uv run --frozen pytest -m "not integracao"
    uv run --frozen python scripts/testar_banco.py
    uv run --frozen coverage report --include="*/configuracao.py" --fail-under=95
    uv run --frozen ruff check .
    uv run --frozen ruff format --check .
    uv run --frozen mypy src
    uv run --frozen bandit -q -r src
    uv run --frozen pip-audit --skip-editable --progress-spinner off
    uv build --no-build-isolation

Instalação/auditoria podem acessar serviços públicos; a suíte de testes é offline. Os testes verificam CSV inválido, prioridade de configuração, separação stdout/stderr, níveis dos registros, retorno seguro de erros e execução em terminal com codificação limitada.

Hooks opcionais, após configurar Git:

    uv run --frozen pre-commit install

A configuração dos hooks acompanha o projeto; a instalação do hook não é automática. O CI executa testes, lint, tipos, segurança, cobertura, build e um teste do wheel instalado fora da pasta de fontes. Artefatos ficam em dist/, fora do Git.

## Documentação

- [Plano principal](plano-pipeline-etl-api.md).
- [Fontes e evidências](docs/fontes.md).
- [Histórico real e validação ponta a ponta](docs/historico-real-m1.md).
- [API FastAPI: iniciar, consultar e verificar](docs/api.md).
- [Indicadores e publicação gold](docs/indicadores-e-publicacao.md).
- [Coleta incremental e reconciliação](docs/incremental-bcb.md).
- [Carga BCB e recuperação](docs/carga-bcb.md).
- [Validação, quarentena e auditoria](docs/validacao-e-quarentena.md).
- [Coleta BCB e bronze](docs/coleta-e-bronze.md).
- [Ambiente local](docs/ambiente-local.md).
- [PostgreSQL: iniciar, migrar, testar e preservar dados](docs/banco-de-dados.md).
- [Convenção português-BR](docs/decisoes/0001-idioma-do-projeto.md).
- [Plano da preparação](docs/superpowers/plans/2026-11-17-preparacao-e-descoberta.md).
- [Plano e verificações da base Python](docs/superpowers/plans/2026-11-17-base-do-pacote.md).

- [Calendário IPCA: evidência oficial e limite da heurística](docs/calendario-ipca.md).
- [Restauração e replay offline em bancos separados](docs/recuperacao-local-m1.md).

- [Desempenho local M1: protocolo e resultados](docs/desempenho/2026-11-18-m1-local.md).

- [Orquestração local: agendas, painel e retomada](docs/orquestracao-local.md).

## Convenção e dados

Identificadores próprios em português-BR, sem acentos: ConfiguracaoAplicacao, executar, series_bcb. Comentários, docstrings e mensagens em português-BR; interfaces externas preservadas conforme AGENTS.md.

Amostras pequenas oficiais ficam em testes/amostras/bcb com origem e hash. Dados operacionais, .env, ambientes, caches e backups ficam fora do Git. Licença específica IPCA e termos IBGE ainda precisam de confirmação antes de redistribuição ampliada.

## Próximo passo

Revisar e publicar o código no GitHub, executar o workflow remoto e depois criar
a página de indicadores que consumirá a API. O [relatório pré-publicação](docs/revisao-publicacao-github.md)
registra a seleção dos arquivos, verificações e limites conhecidos.

## Sequência de conclusão acordada

Sequência atual definida pelo responsável: revisão local → GitHub/CI → página de
indicadores → hospedagem pública validada. M1/M2 locais têm evidências registradas;
M3 está em preparação, com Oracle Cloud como candidata. O workflow remoto só será
considerado aprovado depois de executar no GitHub. Nenhuma conta ou recurso é
criado automaticamente.

## Licença e segurança

Código próprio sob [MIT](LICENSE); [condições dos dados oficiais](docs/licenca-dados.md)
documentadas separadamente. Orientações de operação e relato responsável em
[SECURITY.md](SECURITY.md). Serviços administrativos e `/metrics` devem permanecer
privados na implantação pública.

Instrumentação por fase BCB/IBGE validada na API, Prometheus e Grafana: [métricas, interpretação e limites](docs/monitoramento-fases-m2.md).
