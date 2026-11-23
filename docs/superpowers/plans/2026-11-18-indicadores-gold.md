# Indicadores BCB e publicação gold

Escopo autorizado: próxima etapa após incremental, conforme plano principal seções7.2/8. Execução nesta sessão; sem API, IBGE, Redis ou agendamento.

Decisão: três MVs PostgreSQL atualizadas juntas sob a mesma trava transacional BCB da carga; produto IPCA em função NUMERIC versionada, sem log/exp/float. Alternativa de tabelas Python duplicaria lógica de publicação; refresh concorrente isolado impediria atomicidade do domínio. Funções Python Decimal servem como referência e futura serialização.

- [x] Testes primeiro: média anual ponderada por observações, Selic sem composição, IPCA12m/ano com meses consecutivos, apoio2019 e lacunas, ROUND_HALF_EVEN somente na resposta.
- [x] Migração0004: função produto, MVs mensal/anual/IPCA12m e índices únicos; ownership publicador, SELECT para API, leitura core e atualização operacional estritamente necessárias. Campo data_publicacao no estado para atualizar flags de período mesmo sem nova geração core.
- [x] Publicação: reservar conexão, esperar trava até30s, refresh das três MVs e gold=core/PRONTA atomicamente. Falha reverte MVs/estado, registra auditoria separada e mantém PENDENTE. Sem estado core, adiar sem inventar versão. Repetição no mesmo dia sem mudanças não regrava gold; outro dia atualiza referência temporal.
- [x] API futura deverá considerar data_publicacao junto à geração gold para cache/ETag. Campos parcial indicam período aberto; completo diário NULL e motivo calendário não homologado. IPCA incompleto NULL com motivo; dados públicos apenas2020+, apoio2019 participa só do cálculo12m.
- [x] CLI publicar --dominio bcb, URL_BANCO_PUBLICADOR/arquivo local explícito. Testes reais de rollback/lock/permissões/migração. Backup antes da revisão no banco principal; publicar e repetir sobre os cinco fatos existentes sem HTTP.
- [x] Qualidade/cobertura>=95% nos cálculos e publicação; docs, pacote e imagem verificados. Histórico real completo, calendário, API, IBGE e replay continuam pendentes.

## Evidências e decisões finais

- 242 testes passaram; cobertura global95,99%, indicadores100%, publicação97%, CLI100%. Mypy32arquivos, Ruff/formatação, Bandit e pip-audit passaram. CI exige95% separadamente nos novos módulos.
- RED observado no módulo Decimal ausente e na resolução de credencial publicador; testes passaram após implementação. Regressão importante de unidade anual IPCA observada falhando (% no mes) e corrigida para % no ano antes da aplicação principal.
- Revisão independente revisao_gold não encontrou outros bugs importantes/críticos. Observação menor aceita/documentada: data_referencia usa início da transação PG; execução que cruza meia-noite só renova a referência na próxima chamada. Mesmo referencial é usado por todas as visões.
- Backup anterior0004: backups/etl_antes_gold_20261118_164423.dump (30521bytes), catálogo legível; não é ensaio completo de restauração. Migração0004 aplicada via imagem real e alembic check sem diferenças.
- Publicação principal4a19d677-29f0-4b05-9326-26774dab7a85, SUCESSO. Repetição1cff6fdc-0760-4e58-84b9-1362e488db34, JA_PUBLICADA. Cinco fatos e metadados preservados; core1/gold1 PRONTA; MVs mensal/anual uma linha Selic e IPCA12m vazia. Sem HTTP. Relatório dados/descoberta/sondagem_gold_bcb.json.
- Precisão de composição verificada contra constante Decimal independente, apoio2019, lacunas, médias por observação e período aberto. Falha no segundo refresh preserva gold anterior e recuperação atualiza todas juntas. Publicador sem UPDATEcore; API com SELECT nas MVs sem refresh.

Próxima entrega: API e acesso seguro ao estado de publicação. Cobertura histórica real completa, calendário, cache, orquestração, IBGE e replay continuam pendentes. PRONTA significa sincronismo com os fatos atuais, não completude da fonte.

Distribuições sdist/wheel finais construídas; wheel instalado em ambiente separado e executado fora da árvore de fontes: ajuda da publicação e repetição JA_PUBLICADA passaram, com core/gold1. Relatórios operacionais, backup e .env.banco permanecem ignorados pelo Git. Nenhum commit, push ou publicação externa foi realizado.
