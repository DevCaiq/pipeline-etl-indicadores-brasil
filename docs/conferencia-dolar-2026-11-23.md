# Conferência do histórico do dólar — 23/11/2026

**Pendência de datas resolvida no intervalo de 02/01/2020 a 19/11/2026:**
1.728 datas carregadas e 1.728 datas distintas no serviço oficial PTAX, sem
observação omitida ou extra. Os 68 dias de semana sem observação correspondem
exatamente aos calendários anuais ANBIMA. Nenhum fato foi inserido, alterado ou preenchido.

## Método e limites

A [ficha oficial do dólar](https://dadosabertos.bcb.gov.br/pt_BR/dataset/dolar-americano-usd-todos-os-boletins-diarios)
identifica a metodologia PTAX de fechamento. Foram feitas sete consultas anuais
ao recurso `CotacaoDolarPeriodo` da [API oficial PTAX](https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/documentacao),
com início/fim explícitos, `$format=json` e `$top=10000`. Cada resposta ficou abaixo
do limite e sem próxima página; os corpos foram preservados antes do parse.

As datas do banco foram lidas em transação `REPEATABLE READ READ ONLY` usando
`api_leitura`. A comparação usou conjuntos de datas, sem conversão de fuso dos
horários não qualificados pela fonte. Esta etapa verifica referências, não igualdade
de todas as cotações históricas nem o prazo futuro de publicação do SGS.

A fonte PTAX retornou duas linhas em 23/04/2025, com os mesmos valores de compra
e venda e milissegundos distintos. A duplicação foi registrada; o corpo original
não foi modificado. São 1.729 linhas oficiais para 1.728 datas distintas.

A primeira sondagem com `$orderby` foi rejeitada HTTP 400; ela foi arquivada
separadamente e não entrou na evidência de sucesso. Uma sondagem seguinte foi
interrompida pela duplicata; a conferência final acima tratou a ocorrência explicitamente.

A [ANBIMA](https://www.anbima.com.br/feriados/) é a publicadora do calendário do setor,
não um órgão governamental nem a fonte dos valores. Seus calendários 2020–2026
foram arquivados e usados para nomear as ausências; a confirmação das datas
efetivas veio da API oficial PTAX. Não se presumiu que atendimento de agência,
liquidação, pregão e publicação de cotação tenham calendários intercambiáveis.

O limite de 19/11 é o máximo carregado no snapshot. O calendário de 2026 também
registra 20/11 como feriado; 21–22/11 foram fim de semana. A consulta ocorreu
antes da divulgação diária de 23/11, portanto esta manhã não foi classificada
como atraso. O intervalo integral auditado não é estendido automaticamente.

A conferência documental não modifica a política da API: `cobertura.completa=null`
e `CALENDARIO_NAO_HOMOLOGADO` continuam quando aplicáveis ao recurso consultado.
Não foi implementado calendário dinâmico nem homologação automática de períodos futuros.

## Contagens por ano

| Ano | Datas PTAX distintas / banco | Dias sem observação classificados |
|---|---:|---:|
| 2020 | 251 | 10 |
| 2021 | 251 | 10 |
| 2022 | 251 | 9 |
| 2023 | 249 | 11 |
| 2024 | 253 | 9 |
| 2025 | 252 | 9 |
| 2026 | 221 | 10 |

## Classificação individual

| Data sem observação | Motivo no calendário ANBIMA | Fonte anual |
|---|---|---|
| 2020-02-24 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-02-25 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-04-10 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-04-21 | Tiradentes | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-05-01 | Dia do Trabalho | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-06-11 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-09-07 | Independência do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-10-12 | Nossa Sr.a Aparecida - Padroeira do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-11-02 | Finados | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2020-12-25 | Natal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2020.asp) |
| 2021-01-01 | Confraternização Universal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-02-15 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-02-16 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-04-02 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-04-21 | Tiradentes | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-06-03 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-09-07 | Independência do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-10-12 | Nossa Sr.a Aparecida - Padroeira do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-11-02 | Finados | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2021-11-15 | Proclamação da República | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2021.asp) |
| 2022-02-28 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-03-01 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-04-15 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-04-21 | Tiradentes | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-06-16 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-09-07 | Independência do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-10-12 | Nossa Sr.a Aparecida - Padroeira do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-11-02 | Finados | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2022-11-15 | Proclamação da República | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2022.asp) |
| 2023-02-20 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-02-21 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-04-07 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-04-21 | Tiradentes | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-05-01 | Dia do Trabalho | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-06-08 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-09-07 | Independência do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-10-12 | Nossa Sr.a Aparecida - Padroeira do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-11-02 | Finados | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-11-15 | Proclamação da República | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2023-12-25 | Natal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2023.asp) |
| 2024-01-01 | Confraternização Universal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-02-12 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-02-13 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-03-29 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-05-01 | Dia do Trabalho | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-05-30 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-11-15 | Proclamação da República | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-11-20 | Dia Nacional de Zumbi e da Consciência Negra | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2024-12-25 | Natal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2024.asp) |
| 2025-01-01 | Confraternização Universal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-03-03 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-03-04 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-04-18 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-04-21 | Tiradentes | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-05-01 | Dia do Trabalho | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-06-19 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-11-20 | Dia Nacional de Zumbi e da Consciência Negra | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2025-12-25 | Natal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2025.asp) |
| 2026-01-01 | Confraternização Universal | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-02-16 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-02-17 | Carnaval | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-04-03 | Paixão de Cristo | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-04-21 | Tiradentes | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-05-01 | Dia do Trabalho | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-06-04 | Corpus Christi | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-09-07 | Independência do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-10-12 | Nossa Sr.a Aparecida - Padroeira do Brasil | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |
| 2026-11-02 | Finados | [Calendário](https://www.anbima.com.br/feriados/fer_nacionais/2026.asp) |

## Integridade e reprodução

Arquivo operacional privado, ignorado pelo Git: `dados/descoberta/ptax_aceite_20261123_071525/`.
`metadados.json` e `metadados_calendarios.json` guardam URL, parâmetros, instante UTC,
HTTP, tamanho e SHA-256. `conferencia.json` e `classificacao_feriados.json` contêm
os resultados, listas de divergências vazias e a ocorrência duplicada.

| Corpo arquivado | SHA-256 |
|---|---|
| `ptax_2020.json` | `95b38a7c07b68c655a775dda7d226a88b0b8436274b3a241fdc84af7d8201e5a` |
| `ptax_2021.json` | `c46c87f0cd1093b8d3836418ccedb0b740ad87851c534c6504c4f66f8f168dec` |
| `ptax_2022.json` | `ddab662fb19a7cc4591aeb14bbddc7d07ae2d8db39c9418314cdf8399c53409f` |
| `ptax_2023.json` | `305a48ed208644c3a4c7b6f33b4353134cc688d794bfd928d7ffb7cd94f84e41` |
| `ptax_2024.json` | `0daddd456644a8cbad549ee42c0fd384a39acd1909edf44c3755d8e1a8993dc9` |
| `ptax_2025.json` | `11917e20df4423744326ac38052e20196720d04622becc5d634ecd0618b5b8aa` |
| `ptax_2026.json` | `6e053b795f613b5dcfebba9941bf3fe6b80ea87475c84642250ffd4445daf5c1` |
| `calendario_anbima_2020.html` | `04ac0d791f93ad7200a70d1d0641eca9f0c527d7ffc4443a9d4f44ca5406c8e9` |
| `calendario_anbima_2021.html` | `9c6939c11063da3effa5ff56af51795cc1888c2dbad3f70dd885fde00e610d0e` |
| `calendario_anbima_2022.html` | `35f9de88643b45659ae4997e1ae14e304cf7e22f81a909fb572c50cf979eb719` |
| `calendario_anbima_2023.html` | `7228adc1cbc9475d2fd27379ca2418320d610fa5e8ed4f96127ce9a056166614` |
| `calendario_anbima_2024.html` | `463ad1566d981c1a50637dd78455d32cfb9e29dbf9d09d8be5de86c0cd906a37` |
| `calendario_anbima_2025.html` | `505d495ee7bc8b35ef85d5a0acef8f983caeafef7a05d54843e263d083f9b329` |
| `calendario_anbima_2026.html` | `698a5061d02b5c0a7550955946e589ed33bae5c6fa3d4cd74c7ae4264215575e` |

Para reproduzir: conferir hashes antes do parse, recusar truncamento/paginação,
selecionar as datas de fechamento, registrar duplicações, comparar os dois conjuntos
de datas e confrontar os dias de semana restantes com os calendários anuais.
Registrar o corte e consultar o banco somente em modo leitura. Sondagens reais
são manuais e separadas dos testes automatizados offline.

## Consequência para o aceite

Este resultado encerra a pendência histórica do dólar no recorte acima. As 93
referências IPCA e a continuidade civil Selic já documentadas permanecem válidas
nos respectivos snapshots. A confirmação específica dos termos aplicáveis ao IPCA
continua aberta; [minuta de consulta oficial](solicitacao-termos-ipca.md) pronta,
sem envio. Não foi declarado aceite integral M1/M2, publicação ou CI remoto.
