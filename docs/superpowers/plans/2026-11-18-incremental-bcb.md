# Coleta incremental e reconciliação BCB

Escopo autorizado: próximo passo após carga idempotente; executar nesta sessão, conforme plano principal seção8. Sem nova escolha de infraestrutura ou fonte. Nomes próprios em português-BR.

Abordagem: planejar janelas anuais a partir do checkpoint já transacional; coletar bronze por janela, carregar com validação existente e interromper a série no primeiro resultado diferente de SUCESSO. Alternativa de coletar tudo em um único manifesto dificulta retomada; alternativa de ignorar falha salta cobertura. Reutilizar revisão0003, sem migração nova.

- [x] Planejador puro: diário -30dias; IPCA primeiro dia do mês -24meses; piso público2020; fim hoje São Paulo. Sem checkpoint bloqueia incremental; checkpoint futuro/inconsistente bloqueia execução.
- [x] Executor por série: início auditado antes de HTTP, janelas em ordem, sucesso confirmado antes da próxima; falha interrompe a série. Preservar manifestos de falha e associação pai/coleta/carga; avisos de registros ausentes agregados. Outras séries continuam independentes.
- [x] CLI: coletar bcb --modo incremental/reconciliacao; carga-historica --carregar; --planejar fornece prévia sem HTTP/escrita. Coleta bruta/--validar existentes preservadas; datas somente na carga histórica. Sem agendamento automático.
- [x] Testes antes da implementação: limites de datas/meses/anos, falta de marco, falha intermediária, retomada e idempotência, banco antes da rede, multi-série e saída segura.
- [x] Cobertura>=95% por planejador/executor; Ruff/mypy/bandit, suíte com PostgreSQL exclusivo etl_testes e pacote/imagem. Prévia local com checkpoint ausente, sem baixar histórico automaticamente.
- [x] Documentar comandos, decisão sobre vazio/calendário, recuos e evidências; próximos passos indicadores/publicação/API.

Decisão: reconciliação executa manualmente todo o recorte2020..hoje, incluindo apoio IPCA2019 via coletor existente. A agenda mensal depende da etapa futura de orquestração. Resposta vazia continua bloqueada conservadoramente; não inventar calendário para avançar cobertura.

## Decisões e evidências

- Implementação sem nova revisão SQL. Planejador em processamento/incremental.py; executor em processamento/atualizacao.py; CLI em comandos_atualizacao.py. Compatibilidade da coleta bruta/validada preservada.
- 217 testes passaram; cobertura global95,72%, planejador100%, executor96%, CLI100%. Casos RED observados antes da implementação: módulo planejador ausente, três testes reais do executor e CLI que não aceitava modo incremental. Recuos, interrupção/retomada e banco antes de rede exercitados.
- Bloqueios de pré-condição não criam execuções: IGNORADA com motivo; prévia aprovada PLANEJADA. Pai operacional usa SUCESSO/PARCIAL/FALHA; erros técnicos podem resultar FALHA mesmo com janelas já confirmadas e resultados preservados, sem rollback global.
- Revisão independente revisao_incremental não encontrou bugs importantes/críticos. Testes adicionais verificam Retry-After longo e auditoria indisponível, sem expor detalhes internos ou anunciar sucesso.
- Prévia real somente leitura das três séries: sem checkpoint, nenhum HTTP; reconciliação planejada; cinco fatos e metadados/auditoria/lotes/versões inalterados. Relatório dados/descoberta/sondagem_incremental_bcb.json.
- Limitação explícita: não foi coletado o histórico real completo desde2020. Homologação de calendário, indicadores, publicação, API, agendamento e replay isolado permanecem pendentes. Guia docs/incremental-bcb.md.

Verificações finais: Ruff/formatação e mypy (29 arquivos) passaram; Bandit executado com sucesso após reiniciar o processo de análise que ficou sem resposta no sandbox. Auditoria de dependências sem vulnerabilidades conhecidas; sdist/wheel e imagem Docker construídos; alembic check sem diferenças na revisão 0003. Arquivos de credenciais e relatórios operacionais continuam ignorados pelo Git.
