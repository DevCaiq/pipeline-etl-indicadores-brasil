# Carga histórica real BCB e validação M1

Autorização: próxima etapa após API local, conforme plano principal. Operação manual com APIs oficiais; suíte automatizada permanece offline. Usar implementações existentes, sem substituir bronze/amostras nem inventar observações.

- [x] Conferir banco/esquema e dados iniciais; backup com catálogo legível antes da carga.
- [x] Prévia:2020-01-01 até a data atual em São Paulo para 432/433/1, apoio IPCA 2019 automático; consultas anuais em ordem, retry/cooldown limitados.
- [x] Executar carga histórica real e registrar relatórios/manifestações/falhas. Sem saltar checkpoint nem promover rejeições. Tratar falhas comprovadas, com testes antes de qualquer correção de código.
- [x] Conferir contagens, cobertura, referência máxima, quarentena/avisos e checksums bronze. Cobertura de consultas não é calendário oficial homologado.
- [x] Reaplicar manifestos confirmados sem rede e comparar valores/origem/alterado_em, checkpoint e geração. Publicar gold e verificar IPCA por Decimal independente.
- [x] HTTP local ponta a ponta: catálogo/core/gold/IPCA/histórico/frescor/cursores, preservar banco e encerrar próprio servidor. Adaptar verificações reutilizáveis ao dataset real se necessário.
- [x] Documentar evidências/limitações e atualizar estado do M1. Não anunciar calendário, desempenho, restore/replay, IBGE ou hospedagem concluídos sem ensaio específico.

## Evidências finais

- Carga real das três séries SUCESSO:21janelas/22HTTP200,165594bytes, primeira tentativa em todas. Core4334fatos (2514Selic,1727dólar,93IPCA, destes11apoio2019). Públicas4323. Zero quarentena da etapa.
- Reaplicação dos21manifestos sem rede:0inseridas/alteradas, fatos/origens/instantes/checkpoints/geração idênticos. Conferidos22manifestos de linhagem, inclusive lote Selic inicial.
- Incremental real5HTTP:SUCESSO,0inseridas/alteradas e geração preservada. Reconciliação adicional apenas planejada para não repetir downloads sem necessidade.
- Publicação1935084d-f303-4161-a7b7-986ebdc398e0 SUCESSO:core 22/gold 22 PRONTA. Verificador Decimal independente conferiu351linhas gold (248mensais,21anuais,82IPCA12m); seis anos IPCA completos,2026incompleto.
- HTTP local comparou todas 4323 observações e351agregados comSQL, paginação/ETag/limite/probes; banco inalterado e servidor próprio encerrado. Scripts reutilizáveis: validar_gold_historica.py e verificar_api_local.py.
- Backup pré46020bytes e pós129087bytes; catálogos legíveis. Restore integral/replay não ensaiados nesta etapa.
- Aviso heurístico de frescor IPCA mantido e documentado: referência01/10/2026, comparação45dias; sem homologação de calendário, não interpretar como falha real de disponibilidade.
- Produção sem mudança de lógica/esquema; Ruff/mypy passaram. Nenhuma nova execução da suíte automatizada foi necessária para uma carga operacional; última evidência permanece276testes/96,59% da entrega API.

Relatórios locais ignorados pelo Git: historico_bcb_20261118_175456.json, incremental_real_20261118.json, validacao_historico_m1.json, validacao_gold_historica.json e sondagem_api_bcb.json. Guia versionável: docs/historico-real-m1.md. M1 funcional real demonstrado, sem declarar todos os critérios globais concluídos.
