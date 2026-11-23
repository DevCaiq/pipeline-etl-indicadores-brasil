# Plano de execução — Validação BCB, quarentena e auditoria SQL

Objetivo: validar bronze existente sem rede, registrar execução/etapas/artefatos/rejeições em PostgreSQL e permitir coletar com validação opcional. Nenhuma carga de observações no core nesta etapa.
Especificação: plano-pipeline-etl-api.md seção 7.1, AGENTS.md e autorização do responsável para seguir ao próximo passo.
Arquitetura: contratos Pydantic e validador puro; leitura estrita de manifesto/checksum/descompressão limitada; serviço transacional registra ops e quarentena. Comandos validar bcb e coletar bcb --validar. Sem alterar bronze nem revisão0001.

## Regras

Extra/falta de chave, envelope/JSON incompatível e duplicata conflitante: FALHA do lote. Valores inválidos: quarentena por posição; 0% rejeição SUCESSO, >0% até 5% PARCIAL, >5% FALHA. Nenhum resultado parcial é promovido. Contagens incluem lidas/válidas/rejeitadas/duplicadas/não processadas, com conservação explícita. Resultado vazio bloqueado conservadoramente até homologar calendário.

Datas estritas DD/MM/AAAA, não futuras e dentro da janela do artefato; IPCA normalizado ao primeiro dia. Decimal finito, escala<=10 e precisão NUMERIC(24,10); dólar positivo; IPCA negativo permitido. JSON sem chaves duplicadas/constantes não finitas. Gzip/deflate com limite de saída 10 MiB, nunca extrair arquivo arbitrário.

Auditoria: novas ops.etapa, ops.artefato e ops.quarentena; contagens/versão no registro de execução. Cada validação cria nova execução; artefatos SQL registram o identificador bronze original sem regravar o arquivo. Quarentena guarda representação JSON escapada e referência ao bronze, evitando falha PostgreSQL com NUL/surrogate inválido. API continua sem acesso a erros/rejeições.

## Tarefas

- [x] Testes de contrato, duplicatas, schema drift, limites 5%, datas, Decimal e arquivos malformados antes da implementação.
- [x] Implementar contratos/resultado puro e leitura verificada de manifesto, identidade, cobertura e compressão.
- [x] Novos modelos e migração0002 imutável, com índices/constraints e permissões.
- [x] Registrar EM_EXECUCAO e finalizar com contagens/etapas/rejeições transacionais; falha de persistência não vira sucesso.
- [x] Validar manifesto offline e coletar --validar iniciando registro antes da rede; preservar opção de coleta somente bronze.
- [x] Testes PostgreSQL real (permissões, rollback, revalidação, falha de coleta, migração) e CLI; backup antes da migração principal.
- [x] Atualizar CI com meta>=95% no validador, docs e evidências; executar sondagem no bronze oficial existente, sem nova coleta necessária.

## Revisão focada

Manifesto não confiável não pode misturar execuções/series, duplicar artefatos, omitir janelas ou escapar da raiz; gzip truncado/expansivo falha sem consumir memória ilimitada. SQL de auditoria e quarentena atômicos; conexão indisponível antes da coleta impede rede; core continua vazio. Sem reenviar inválidos à API nem sobrescrever registros de validações anteriores.

## Evidências de conclusão

- 167 testes passaram, incluindo 24 testes de integração PostgreSQL; cobertura global 94,95%, qualidade 99%, contrato BCB 100% e configuração 100%. CI exige 95% separadamente no validador e no contrato, além da meta global 85%.
- Ruff, formatação, mypy (23 arquivos), bandit, pip-audit sem vulnerabilidades conhecidas e build sdist/wheel passaram. Imagem Docker final construída; alembic current informa0002 head e alembic check não encontrou diferenças.
- Testes escritos antes do código para regras e falhas. Regressões IPCA/janela, histórico de execução finalizada e motivos de rejeição foram observadas falhando antes da correção e depois passaram.
- Revisão independente focada encontrou normalização IPCA fora da janela, corrigida. A agregação é deliberadamente global: 1 rejeição em 101 linhas resulta PARCIAL; etapa com 1/1 rejeitada preserva FALHA. Teste registra ambos e nenhuma carga é autorizada.
- Backup backups/etl_20261118_012407.dump criado antes de migrar etl;12646bytes e catálogo legível. Não foi ensaiada restauração completa.
- Bronze oficial existente validado sem HTTP: execução bd242e58-9544-46ef-ae8c-37e690420628;5 lidas/5 válidas, SUCESSO,1 artefato auditado. Consulta posterior confirmou core.fato_serie com0 linhas.
- Nova CLI testada com arquivos, PostgreSQL e transporte simulado; indisponibilidade da auditoria impede HTTP. Privilégios SQL negam SELECT de api_leitura nas novas tabelas operacionais.

## Pendências deliberadas

Staging econômico, indicadores derivados, locks de carga, upsert idempotente, watermarks/incremental, API, calendário completo e publicação não fazem parte desta entrega. Fase 4/M 1 permanecem em andamento. Revalidação é histórica e cria nova execução; não equivale a uma carga repetida idempotente.

Wheel instalado em ambiente separado e executado fora da árvore de fontes: validar bcb --ajuda e verificar-configuracao passaram. Ajuda da CLI usa --ajuda ou -h conforme convenção pt-BR.
