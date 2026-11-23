# Instrumentação das fases M2

Escopo autorizado: continuação do monitoramento previsto no plano principal,
seção 15. Executar inline com testes antes da implementação. Sem commits ou M3.

Arquitetura: reutilizar ops.v_execucoes_api somente leitura, sem novas permissões
ou migrações. Exporter estável na API publica gauges de quantidade concluída,
duração média e instante da última conclusão por fonte/fase/situação. Estatísticas
acumuladas da auditoria retida, sem confundir média histórica com p95 ou última
execução. Pais e filhos são fases distintas, nunca somados como rodadas únicas.
Rótulos aceitam apenas modos conhecidos e situações terminais conhecidas.

- [x] Regressões: dois domínios, modos desconhecidos, fases em andamento,
  leitura sanitizada e falha atômica sem métricas parciais.
- [x] Agregação SQL com durações não negativas e finalizadas; gauges e painel.
- [x] Suíte offline/integrada, Ruff, mypy; construção e atualização só da API.
- [x] Scrape real, consulta Prometheus e painel provisionado; documentar limites.

Decisão: esta entrega trata duração/resultados por fase. Contagens detalhadas,
rejeições, retries e cobertura IBGE ainda exigem instrumentação complementar;
não declarar toda a observabilidade ou M2 concluídos.

Concluído: dois testes RED→GREEN; 525 testes/94,34%; Ruff, formato, mypy e wheel aprovados. Revisão independente sem achados. Oito rotas 200; 11 grupos conferidos no SQL, 11 séries por métrica no Prometheus, seis gráficos no painel. Recarga explícita do provisionamento Grafana necessária após confirmar arquivo montado atualizado. Evidências e limites: docs/monitoramento-fases-m2.md.
