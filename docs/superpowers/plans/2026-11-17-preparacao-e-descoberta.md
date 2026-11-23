# Plano de execução — Preparação e descoberta

> Para execução por agentes: aplicar superpowers:executing-plans tarefa por tarefa. Escopo autorizado: iniciar as Fases 0 e 1 do plano principal; não construir todo M1 nesta etapa.

Objetivo: registrar a convenção português-BR, obter evidências reais das fontes e preparar ferramentas locais.

Arquitetura: consultas pequenas e manuais, com corpos originais e hashes; documentação versionável separada dos dados operacionais. Instalação oficial das ferramentas, sem dependência de container para homologar HTTP.

Stack: Python 3.12 já disponível, urllib/Decimal apenas para sondagem temporária; Git, WSL 2 e Docker Desktop. Sem cliente de produção neste passo.

Especificação: plano-pipeline-etl-api.md, seções 1, 2, 14 e 17; solicitação adicional de português-BR.

## Restrições globais

- Todas as classes, funções e demais identificadores próprios em português-BR, sem acentos; exceções obrigatórias documentadas.
- Windows, 32 GB, 2 a 4 horas por semana; nenhuma publicação externa.
- Resposta original preservada antes do parse. Testes futuros offline.

## Pontos de revisão

1. Não confundir WSL instalado com distribuição instalada ou Docker funcional.
2. Não interpretar flags de virtualização isoladas como prova de ausência de suporte quando há hypervisor ativo.
3. Resposta JSON aceita somente se lista não vazia, campos data/valor, data válida e decimal finito.
4. Checar SHA-256 das amostras contra corpos; sem dado sintético substituindo resposta oficial.
5. Diferenciar metadados IBGE homologados de valores/cobertura municipal ainda não consultados.

## Tarefa 1 — Convenção e fontes

Arquivos: AGENTS.md, plano-pipeline-etl-api.md, docs/decisoes/0001-idioma-do-projeto.md, docs/fontes.md, testes/amostras/bcb/serie_{codigo}.json e metadados correspondentes.

- [x] Registrar instrução explícita e exceções de interoperabilidade.
- [x] Consultar BCB 432/433/1, preservar corpos e copiar amostras pequenas.
- [x] Validar estrutura, datas, Decimal e hashes.
- [x] Consultar metadados/períodos IBGE sem adicionar conector de produção.
- [x] Registrar resultados e pendências em docs/fontes.md.

## Tarefa 2 — Ambiente

Arquivos: docs/ambiente-local.md e README.md.

- [x] Verificar Python, Git, Windows, WSL e memória.
- [x] Consultar requisitos oficiais e pacote Docker do fornecedor.
- [x] Instalar/inicializar Docker Desktop e executar docker version, compose version e hello-world.
- [x] Preparar uv e registrar verificação de versão.
- [x] Inicializar Git local sem criar remoto ou alterar identidade global.
- [x] Registrar limitações reais e próximos passos.

## Verificação final

Recalcular SHA-256; validar datas/Decimal e nomes de arquivos; conferir links locais/documentação e git status. Para ferramentas, registrar comandos e saídas reais. Nenhuma suíte da aplicação é exigida: este passo não implementa funções de produção.

## Registro de execução

Consultas a rede e WSL no sandbox falharam por restrição; repetição autorizada fora do sandbox permitiu diagnosticar ambiente e coletar amostras oficiais. Apenas a instalação do Docker usa instalador de terceiro. Nenhuma mudança de BIOS, reinicialização ou alteração de sistema operacional deve ocorrer automaticamente.

Resultado: Docker Desktop 4.99.0, Engine 29.9.3, Compose 5.7.0 e uv 0.13.9 verificados; hello-world concluiu. Sem aplicação implementada. Pendências de fontes permanecem em docs/fontes.md. Diagnóstico de PATH e ownership resolvido em docs/ambiente-local.md. Repositório vazio foi recriado sob usuário Windows após confirmar ausência de referências/remoto/índice; sem alterações de confiança globais.
