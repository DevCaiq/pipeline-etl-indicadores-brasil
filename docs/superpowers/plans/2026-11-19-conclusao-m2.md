# Conclusão M2 local

Autorização explícita: executar próximo passo e M2 por completo. M3/GitHub adiados.
Spec: plano-pipeline-etl-api.md, seções 12, 13 e DoD M2. Continuação do desenho
aprovado, sem nova plataforma. Python3.12/SQLAlchemy síncronos, pt-BR, offline
nos testes. Não publicar nem alterar bronze/fatos aceitos para fechar checklist.

- [x] Persistir contadores HTTP no pai BCB/IBGE, com início de cobertura explícito.
- [x] Migração0008: views sanitizadas, agregações de linhas/rejeições/retries,
  consultas/frescor e cobertura IBGE; preservar read-only sem expor JSON bruto.
- [x] Exporter e painéis/alertas, testes de estados ausentes/defasados e grants.
- [x] Complementar casos contratuais/rollback IBGE e gates>=95% por módulo crítico.
- [x] Demonstração isolada cronometrada <=15min com replay e API, origem preservada.
- [x] Backup antes de 0008, instalação na origem, imagem/API e métricas reais.
- [x] Suíte completa offline/integrada, Ruff/format/mypy, Bandit/auditoria, pacote.
- [x] Revisão independente final e reconciliação checklist/evidências/limitações.

Três frentes independentes delegadas via skill dispatching-parallel-agents:
contadores cliente/coordenador; auditoria/testes críticos; demonstração isolada.
Raiz implementa views/exporter/painéis e integra, único executor da suíte completa.
Amostras oficiais não serão inventadas, apagadas ou substituídas. Limites de
licença/calendário e CI remoto devem continuar explícitos, não viram sucesso
por alteração de checkbox.


## Retomada 22/11/2026

- Revisão anterior: descoberta confirmada não podia sumir por falha posterior;
  timestamp inválido não podia derrubar todas as famílias. Ambos reproduzidos
  RED→GREEN, migração0009 preservou core/mart após backup.
- Estado0009:580 testes/95,70%;15gatescríticos>=95%;Ruff/formato/mypy/Bandit e
  pip-audit aprovados. Atualização incremental real IBGE c96ea018-d787-4b40-be02-8873a279fbf6 SUCESSO.
- Demo22/11 falhou corretamente ao comparar gold restaurada de 19/11: pg_restore
  recompõe MVs usando data atual na definição0004, alterando data_referencia.
  Valores eram iguais; somente esse metadado divergiu. Relatório falho preservado.
- Correção em andamento:0010 referencia data_publicacao persistida; publicador
  define referência antes dos refreshes na mesma transação. Teste de referência
  arquivada falhou antes, depois passou; rollback da referência também testado.
- Revisão0010: bloquear recomposição com core pendente e adquirir trava BCB antes
  de verificar/publicar. Teste reproduziu ausência da proteção antes da correção.
- Ruling: demo compara replay+API exatamente antes de republicar e valida a nova
  gold contra todas as linhas do SELECT e API após publicação. Uma republicação
  em outro dia pode mudar referência/flags temporais; não ignorar esses campos
  nem alegar igualdade byte a byte entre publicações distintas. Custo: verificação
  adicional SQL/API e distinção explícita entre replay e nova publicação.
- Próximo: suíte agregada final, backup/migração0010+imagem, repetir demo e consolidar
  aceite técnico sem apagar as ressalvas de licença/calendário/CI remoto.


## Fechamento técnico — 23/11/2026

-0010 aplicada após backup;15 objetos core/mart preservados. Guarda BCB pendente e
  trava testadas; geração e referência avançam atomicamente. Revisão P1 corrigida
  com regressão RED→GREEN e suíte agregada588/588,95,80% global, 15 gates>=95%.
- Métrica de cache da API normal acrescentada após descobrir que o benchmark era
  seu único medidor. Dois testes RED→GREEN e fábrica integrada aprovados; revisão
  sem achados. Redis real isolado confirmou acerto, reinício e fallback; container
  exclusivo removido. Primeira tentativa do ensaio usou porta dinâmica que mudou
  no restart; diagnóstico confirmado, ensaio final usou porta fixa exclusiva.
- Demonstração final125,359 s:79cargasBCB, 27.855inalteradosIBGE, 25 rotas/cursores,
  publicaçõesSUCESSO no clone, seisMVs integralmente conferidas e trêsrotasgold após.
  Origem preservada. Relatório demonstracao_m2_20261123_062513.json.
- Qualidade, monitoramento, runbook e auditoria reconciliados. Evidências em
  docs/aceite-tecnico-m2.md. M2 técnico local concluído; aceite integral continua
  qualificado pelas ressalvas de fonte herdadas, sem alterar definição silenciosamente.
- CI remoto e M3/GitHub permanecem adiados. Sem commits, push ou recursos externos.

Retomadas finais Prefect BCB/IBGE COMPLETED, pais SUCESSO e contadores persistidos5/10requisições. Serviços locais ativos e seis agendas preservadas. Relatório retomada_final_m2_20261123.json. Nenhuma pendência técnica desta entrega; ressalvas de aceite integral de fontes/CI remoto permanecem identificadas.
