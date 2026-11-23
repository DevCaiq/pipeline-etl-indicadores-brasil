# Histórico real BCB e validação ponta a ponta — 18/11/2026

A carga do recorte 2020-01-01 a 2026-11-18 foi executada nas APIs oficiais BCB e confirmada no PostgreSQL local. Os valores retornados pela fonte foram preservados no bronze e validados antes da promoção. Esta entrega não altera a lógica de produção nem o esquema 0006; acrescenta evidências operacionais e verificadores manuais reutilizáveis.

## Dados carregados

| Série | Observações públicas desde 2020 | Apoio técnico 2019 | Última referência recebida |
|---|---:|---:|---|
| 432 — Meta Selic | 2514 | 0 | 18/11/2026 |
| 1 — Dólar venda | 1727 | 0 | 18/11/2026 |
| 433 — IPCA | 82 | 11 | 01/10/2026 |
| Total | 4323 | 11 | — |

O core contém 4334 fatos. Os onze meses de fevereiro–dezembro de 2019 entram no IPCA12m de 2020; a API não os expõe como observações públicas. IPCA até outubro é o recorte efetivamente devolvido pela fonte nesta consulta; não preencher novembro/dezembro ou assumir publicações ainda não confirmadas.

Foram 21 janelas de carga confirmadas, com 22 respostas HTTP 200: o primeiro manifesto IPCA contém também a janela de apoio2019. Os registros contabilizam 22 consultas iniciais, todas na primeira tentativa, respeitando o espaçamento do cliente. Corpos somam 165594 bytes, preservados com metadados e SHA-256. Houve zero registros em quarentena nesta etapa.

Execuções principais:

| Série | Execução da carga histórica |
|---|---|
| Selic | e53ef4cc-9dd1-42ed-a641-9c56089c94b1 |
| IPCA | d3347c1a-130c-4d11-85a1-03cf8340feef |
| Dólar | 9aca0bf9-de8b-45f4-983e-85ce9c3e38ae |

Relatório da CLI: dados/descoberta/historico_bcb_20261118_175456.json. Dados operacionais, logs, bronze e backups continuam fora do Git; amostras oficiais dos testes não foram substituídas.

## Idempotência, incremental e linhagem

Os 21 manifestos confirmados foram reaplicados sem rede. Cada tentativa terminou SUCESSO com zero inserções/alterações. Comparação antes/depois verificou exatamente valores, lote de origem, instantes, checkpoints e geração. Auditoria, preparação e lotes operacionais adicionais são esperados; não equivalem a duplicação dos fatos.

O incremental real foi executado depois do histórico: cinco novas consultas HTTP, todas na primeira tentativa. Selic/dólar consultaram 19/10/2026 a 18/11/2026; IPCA consultou desde 01/10/2024, em três janelas anuais. Resultado SUCESSO, zero inseridas/alteradas, fatos e geração preservados. Uma reconciliação completa adicional foi apenas planejada, evitando repetir os mesmos downloads recém-executados.

Os três checkpoints cobrem consultas confirmadas até 18/11/2026. A última observação é 18/11 para séries diárias e 01/10 para IPCA; cobertura consultada é distinta da última referência publicada. Os 22 manifestos de origem dos fatos atuais, incluindo o pequeno lote Selic anterior, tiveram identidade e checksum novamente conferidos; não há fatos com instante de origem desconhecido.

Evidência: dados/descoberta/validacao_historico_m1.json e incremental_real_20261118.json. Nenhuma falha foi ocultada e nenhum checkpoint saltou janela não confirmada.

## Gold e cálculos independentes

Após carga/incremental, a publicação 1935084d-f303-4161-a7b7-986ebdc398e0 terminou SUCESSO. Estado final core 22/gold 22, PRONTA, referência 18/11/2026.

| Visão | Linhas verificadas |
|---|---:|
| mart.mv_serie_mensal | 248 |
| mart.mv_serie_anual | 21 |
| mart.mv_ipca_12m | 82 |
| Total | 351 |

scripts/validar_gold_historica.py recalcula estatísticas a partir do core sem reutilizar as funções de cálculo da aplicação. Confere contagem, média por observação, mínimo, máximo e último; compara composição IPCA com Decimal em precisão 500, sem float. Cálculos anuais/12m são comparados sem arredondamento intermediário de apresentação; médias são conferidas também na precisão pública de seis casas.

Os seis anos IPCA de 2020 a 2025 têm 12 meses completos. O ano 2026 permanece incompleto e retorna NULL, conforme contrato. As 82 janelas de 12 meses são completas, incluindo janeiro de 2020 graças ao apoio de 2019. Não se converte Selic em rentabilidade nem se calcula média anual como média das médias mensais.

Relatório: dados/descoberta/validacao_gold_historica.json.

## API real

scripts/verificar_api_local.py iniciou um servidor próprio em porta livre de 127.0.0.1. Foram conferidas as consultas básicas, health/ready/docs/OpenAPI, ETag 304, paginação e limite por IP real, inclusive com X-Forwarded-For forjado. O servidor foi encerrado ao final.

A verificação percorreu todas as 4323 observações públicas via keyset, sem duplicações/omissões, e comparou valores/datas com o core. Também comparou as 351 linhas gold HTTP com a gold SQL, incluindo strings decimais de seis casas, unidades, incompletude e datas. O verificador independente acima confirmou separadamente os cálculos SQL.

Comparação do banco antes/depois preservou os 4334 fatos, seus metadados, lotes, preparações, auditoria, gerações e visões. API somente leitura não gerou ETL. Relatório atual: dados/descoberta/sondagem_api_bcb.json.

Para repetir as verificações, com banco e gold disponíveis:

```powershell
uv run --frozen python scripts/validar_gold_historica.py
uv run --frozen python scripts/verificar_api_local.py
```

Esses verificadores consultam apenas PostgreSQL/HTTP locais; não baixam novamente o BCB. Para usar a API no terminal:

```powershell
uv run --frozen pipeline-etl servir
```

Abrir http://127.0.0.1:8000/docs após iniciar. Uma instância já ativa consulta a nova geração sem reiniciar; cursores de geração anterior expiram conforme contrato.

## Backup e avisos

Backup anterior à carga: backups/etl_antes_historico_20261118_175426.dump, 46020 bytes. Backup após a validação: backups/etl_historico_validado_20261118_180556.dump, 129087 bytes. Ambos tiveram catálogo pg_restore --list legível. Isso não equivale a um ensaio de restauração completa ou reconstrução por replay isolado.

A qualidade registrou FRESCOR_POTENCIALMENTE_DEFASADO para o IPCA. A heurística compara 45 dias desde o início do mês de referência: 01/10 a 18/11 supera esse limiar, apesar de as consultas recentes terem retornado SUCESSO. O aviso aparece nas validações do histórico/reaplicação/incremental; não representa três falhas diferentes da fonte. O calendário oficial precisa ser homologado antes de interpretar isso como atraso real. O alerta foi preservado, sem ajustar o limiar só para obter uma situação verde.

## Estado e pendências

O percurso fonte→bronze→qualidade→core→gold→API foi demonstrado com dados reais e sem rejeições. Ruff e mypy passaram; a lógica de produção não mudou, portanto os 276 testes/cobertura 96,59% documentados na etapa da API permanecem a última execução automatizada, não uma suíte nova deste carregamento.

A carga do recorte foi concluída; completude de calendário ainda não foi homologada. Permanecem calendário IPCA/termos específicos, ensaio completo de restauração e replay isolado, benchmark conforme protocolo, CI remoto autorizado, orquestração, IBGE/cache/métricas e hospedagem. Não declarar M1 global encerrado ou SLA de desempenho com base nesta sondagem.

## Etapa posterior: recuperação e calendário

Após esta carga, o calendário de 2026 foi conferido manualmente e os ensaios completos de restauração/replay em bancos novos passaram, incluindo HTTP de todos os dados. Ver [calendário IPCA](calendario-ipca.md) e [recuperação local](recuperacao-local-m1.md). A suíte foi executada novamente nessa etapa posterior: 279 testes aprovados, cobertura global 96,59%. Os limites registrados acima descrevem o encerramento da carga; calendário automático, benchmark e demais critérios continuam pendentes.
