# Calendário IPCA e recuperação M1

Escopo autorizado: executar a próxima etapa do plano, sem trocar o destino da aplicação.

- [x] Consultar e arquivar fontes oficiais do calendário IPCA, com instante UTC e SHA-256; explicar o aviso de 45 dias sem apagar auditoria.
- [x] Registrar retrato somente leitura da base etl e plano ordenado de promoções confirmadas no bronze.
- [x] Restaurar backup em banco novo e exclusivo; comparar esquema, privilégios, todas as tabelas/MVs e HTTP.
- [x] Migrar outro banco novo; reconstruir offline a partir das promoções originais, publicar e comparar fatos/cobertura/linhagem lógica/gold/HTTP.
- [x] Confirmar base etl inalterada, registrar tempos medidos e documentar limites/resultado.

Decisão: tarefa operacional sobre implementação existente; não alterar contrato de frescor nem acrescentar calendário automático sem desenho específico. Validação manual documentada do calendário atual não homologa todos os anos. Não executar DROP, --clean, troca de URL da aplicação ou downloads BCB. Bancos novos têm nomes exclusivos e devem permanecer disponíveis para inspeção ao término; não reutilizar bancos existentes. Sem produção nova, sem commit/publicação. O repositório ainda não tem commit-base; ensaio isolado por banco, sem criar worktree vazia nem versionar segredos para viabilizar isolamento.

## Evidências

- Fontes IBGE arquivadas em dados/descoberta/calendario_ipca_20261118, UTC 19/11 00:55 (18/11 em São Paulo); API calendário/PDF HTTP 200, HTML 403 preservado. Produto 9256 filtrado no cliente; 12 referências 2026. Outubro atual esperado; heurística 45 dias tem falso positivo nesta data. Não alterar produção.
- Primeira verificação de restore identificou representações SQL/ordem ACL diferentes; investigação somente leitura demonstrou equivalência. Normalização restrita + ordenação ACL, dois testes observados falhar e depois passar. Bancos da tentativa inicial mantidos, replay não executado neles.
- Ensaio final: recuperação_20261119_005954_dc9089.json. Restore 1,375 s, replay/migrações/publicação 13,203 s; medições locais únicas, excluem HTTP/preparação. Todos os dados e catálogo comparados; replay de 49 promoções, 4334 fatos, 351 agregados, core 22/gold 22 PRONTA. Base etl inalterada.
- HTTP em ambos os destinos: 4323 observações públicas + 351 agregados comparados com SQL, paginação/ETag/limite/probes; servidores próprios encerrados. Sem chamadas BCB, sem troca de destino/limpeza automática.
- Suíte completa offline no banco etl_testes: 279 aprovados em 56,49 s, cobertura 96,59%.
- Limites: mesmo cluster com papéis já existentes, não desastre de volume/máquina, sem calendário automático/benchmark/RPO/RTO garantido. Próximo passo: desenhar avaliação automática pelo calendário com vigência/fallback.

Revisão independente identificou dois P2: ACLs por coluna ausentes do retrato e possível remoção de asserts com Python otimizado. Corrigidos: catálogo passa a incluir ACLs de coluna/banco; HTTP recusa not __debug__ antes de conectar, com teste observado falhar/passar. Auditoria HTTP também passou de contagens para SHA-256 do conteúdo. Repetidas as duas sondagens completas e comparação final somente leitura dos três bancos; origem idêntica ao retrato inicial. Suíte final 279/96,59%, Ruff/formatação e mypy aprovados.

Revisão final dos ajustes: nenhum problema importante remanescente. Revisão estática independente, sem acesso a credenciais, banco ou rede.
