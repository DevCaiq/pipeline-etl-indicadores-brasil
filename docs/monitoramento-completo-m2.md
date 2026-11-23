# Monitoramento completo da entrega técnica M2

Complemento de 22/11/2026 às [métricas por fase](monitoramento-fases-m2.md).
Exporter estável em `/metrics`, na mesma API síncrona; usa papel `api_leitura`,
transação somente leitura e views agregadas/sanitizadas das revisões0008/0009.
Identificadores, URLs, caminhos, hashes e mensagens de erro não viram rótulos.

| Métrica | Semântica |
|---|---|
| pipeline_linhas | Linhas auditadas por fonte/fase/situação/tipo: lidas, válidas, rejeitadas, duplicadas, não processadas |
| pipeline_http_requisicoes | Tentativas HTTP dos pais instrumentados concluídos, inclusive falhas sem resposta |
| pipeline_http_retentativas | Tentativas adicionais após a primeira de cada consulta |
| pipeline_coletas_instrumentadas | Quantidade de pais concluídos com contadores conhecidos |
| pipeline_ibge_consulta_segundos | Instante UTC/Unix da consulta confirmada por conjunto |
| pipeline_ibge_consulta_defasada | 1 atrasada, 0 recente, -1 desconhecida ou relógio futuro |
| pipeline_ibge_ano | Último ano disponível descoberto e último carregado |
| pipeline_ibge_periodo_pendente | 1 descoberto ainda ausente, 0 carregado, -1 desconhecido/inconsistente |
| pipeline_ibge_municipios | Contagens publicadas esperadas/recebidas/disponíveis/indisponíveis por ano |
| pipeline_publicacao_pendente | Core à frente da gold ou publicação ainda não pronta |

São gauges da auditoria retida, não counters: não usar `rate`/`increase` nessas
contagens. A retenção pode diminuir valores; fases pai/filho não são somáveis
como rodadas únicas. Contagem de rejeições IBGE inválidas na estrutura pode ser
zero porque o lote inteiro foi bloqueado, sem denominador de linhas confiável;
conferir situação e quarentena, não interpretar zero como lote válido.

A instrumentação de tentativas começa nas execuções que usam os clientes atuais.
Histórico anterior não ganha zeros artificiais. Enquanto o processo está ativo ou
se a gravação final falhar, o contador pode estar ausente. Detalhes em
[métricas de coleta](metricas-coleta-m2.md). Não comprova contabilização de toda
requisição já feita nem entrega da telemetria após queda abrupta.

## Frescor e cobertura

Localidades: alerta após14dias sem coleta territorial confirmada. População:
consulta de períodos há mais de 35dias ou ano disponível ainda não carregado.
Não exigir estimativa nova todo mês. A descoberta confirmada permanece visível
mesmo quando população/carga falham depois. Não confundir sua data com a da
referência populacional. Timestamps inválidos tornam o campo desconhecido, sem
derrubar as demais famílias.

Contagens de cobertura vêm da gold nacional, por ano; fonte e indicador são
fixados no contrato da view. Valores `...` continuam indisponíveis, não zero.
A métrica mostra a cobertura publicada; `pipeline_publicacao_pendente` distingue
core ainda não refletido na gold. Ausência de ano/série não significa cobertura
completa. Base territorial atual na coleta, sem promessa de malha histórica.

## Painéis e alertas

Três dashboards: API (5 gráficos), pipeline (9 gráficos), frescor/cobertura (8 gráficos).
Prometheus tem8 regras, incluindo consulta IBGE atrasada/desconhecida, ano pendente
e publicação pendente observada por 1h. Essa janela reinicia se o Prometheus
reiniciar; não é medição durável exata desde a carga. Políticas são operacionais,
não SLA do BCB/IBGE. Regras e testes foram executados com promtool sem rede.

O alerta real API indisponível já foi provocado e resolvido em 19/11/2026, com
registro `dados/descoberta/alerta_m2_20261119.json`. O Grafana exibe as séries
`ALERTS` do Prometheus; não houve envio de notificações externas.

Após editar JSONs/regras, recarregar explicitamente o provisionamento Grafana
(`POST /api/admin/provisioning/dashboards/reload`, autenticação administrativa
local privada) e Prometheus (`POST /-/reload`). Não incluir senhas em comandos
públicos. As telas e métricas ficam somente em loopback/rede privada do Compose.

[Runbook de incidentes](runbook.md) e [auditoria de aceite](auditoria-aceite-m2.md)
registram procedimentos e ressalvas herdadas sobre fontes/CI remoto.


## Cache na API normal — 23/11/2026

`cache_eventos_total{evento}` é counter por processo, com lista fechada de eventos:
acerto, cálculo, ausência, falha_backend, circuito_aberto, desativado e trava_ocupada
(identificadores reais sem acentos). Eventos não são exclusivos: uma ausência pode
terminar em cálculo ou acerto após espera. Cálculo conta tentativas, inclusive erro
posterior da consulta; não significa resposta bem-sucedida. As chaves/URLs nunca
viram rótulos. Falha da telemetria é sanitizada e não altera o cache.

Usar `rate` somente nesses counters, não nos gauges da auditoria. O painel mostra
acertos/(acertos+cálculos), explicitamente tentativas, não taxa de sucesso HTTP.
Redis real isolado confirmou acerto, reinício e fallback; evidências finais no
[aceite técnico](aceite-tecnico-m2.md).
