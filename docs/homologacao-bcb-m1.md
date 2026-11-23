# Homologação complementar BCB M1 — 19/11/2026

Atualização posterior de 23/11/2026: a pendência de datas do dólar foi resolvida no recorte carregado: 1.728/1.728 datas na API oficial PTAX e 68 ausências classificadas pelos calendários ANBIMA. Ver [conferência do dólar](conferencia-dolar-2026-11-23.md). A confirmação dos termos específicos aplicáveis ao IPCA continua aberta; [solicitação preparada, não enviada](solicitacao-termos-ipca.md). O conteúdo anterior abaixo preserva o estado histórico.

Atualização 23/11/2026: as referências históricas mensais do IPCA foram confrontadas com nova resposta oficial e com o banco: 93/93 no recorte, sem faltas. A licença específica e o calendário do dólar permanecem pendentes. Ver [nova conferência](conferencia-fontes-2026-11-23.md). O registro abaixo é histórico.

## Resultado e alcance

Esta consulta manual complementa as evidências do M1, sem alterar amostras oficiais, bronze operacional, fatos, banco, configuração ou implementação. Foram consultadas fontes oficiais de modo moderado, sem provocar quotas ou consultas acima dos limites anunciados. Não certifica completude histórica nem encerra a pendência de licença específica da série 433.

Os corpos HTTP foram gravados antes de qualquer interpretação em `dados/descoberta/bcb_homologacao_m1_20261119T040431Z/`, pasta operacional ignorada pelo Git. `metadados.json` contém URL original com parâmetros, URL final, instante UTC por resposta, status, cabeçalhos, nome, tamanho e SHA-256. As interpretações abaixo ocorreram somente depois dessa persistência. A primeira tentativa sem acesso de rede permitido falhou antes de receber respostas; não foi considerada homologação HTTP.

| Consulta | HTTP | Bytes | SHA-256 |
|---|---:|---:|---|
| Dólar SGS 1 sem observações | 404 | 112 | `9b8e7cafb477591fa3e61ef473e61968278235bfe9978b3aeaa5c0eb3e42419a` |
| Página dos termos BCB | 200 | 2871 | `e64d3a8ecfc66b359e640b507d59ff35fe4ac1be596e969812068cc0aa3fb1d4` |
| Página SGS 433 | 200 | 187124 | `00cb1b43d7f868be2aee5101ee0b9246bbce8d4e2aa5a9c2b4bcdc419c51509a` |
| Busca CKAN por 433 | 200 | 8514 | `d6c01644f4d0888d90b73bd2e23a10e4af4c7594ed534848573d368985b416c1` |
| Catálogo dólar SGS 1 | 200 | 36375 | `3910e9202676de25845361ca3b9e9c424358283f5c757847f3bebbb25b883f79` |
| Página IPCA IBGE | 403 | 5950 | `e959558901798ae0315f97e88f2a175a8a11350e12a691b314895c18e937d50f` |

## Ausência de observações não significa lista vazia

Consulta única: [SGS 1 em 01/01/2023](https://api.bcb.gov.br/dados/serie/bcdata.sgs.1/dados?formato=json&dataInicial=01/01/2023&dataFinal=01/01/2023), domingo e primeiro dia do ano. Parâmetros: `formato=json`, `dataInicial=01/01/2023`, `dataFinal=01/01/2023`.

A fonte respondeu HTTP 404 com envelope de erro e detalhe `Value(s) not found`. O corpo original de 112 bytes foi preservado; não retornou HTTP 200, corpo vazio ou `[]`. Esta observação homologa somente esse caso real de ausência, sem generalizar todos os períodos/séries. Não se criou fixture fictícia de resposta vazia.

O cliente atual trata 404 como erro não transitório; portanto esta resposta não deve ser interpretada como lote bem-sucedido nem avançar checkpoint. A validação separada já possui proteção `RESPOSTA_VAZIA` para `[]`, coberta por teste simulado; esse contrato defensivo não prova que a fonte efetivamente retornará `[]`.

## Série 433: produtor, atribuição e termos

A [consulta oficial SGS 433](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=433) retornou HTTP 200 e identifica IPCA, variação percentual mensal e fonte IBGE. O BCB distribui a série; não deve receber atribuição exclusiva de produtor.

A [busca oficial CKAN](https://dadosabertos.bcb.gov.br/api/3/action/package_search?q=433) retornou um resultado, `ouvidorias-dos-bancos`, sem relação com IPCA. A licença desse resultado não se aplica à série 433. Não foi localizada nesta consulta uma ficha de dataset 433 com licença específica. Não atribuir ODbL por analogia com outras séries.

A [política oficial de privacidade e termos de uso BCB](https://www.bcb.gov.br/acessoinformacao/politicaprivacidade), em resultado indexado da pesquisa web desta sessão, informa na seção Reprodução do Conteúdo que a reprodução exige preservação da integridade e indicação da fonte. A consulta HTTP direta arquivada retornou apenas a estrutura de uma aplicação JavaScript, sem o texto da cláusula. Uma tentativa adicional de endpoint de conteúdo (`https://www.bcb.gov.br/api/servico/sitebcb/politicaprivacidade`) retornou HTTP 400 e foi arquivada como falha, sem ser tratada como documentação de API oficial.

Esses termos gerais encontrados são evidência útil para atribuição, mas não constituem licença específica 433 arquivada nem esclarecem de forma individual o conteúdo produzido por terceiro. A pendência permanece explícita: obter e arquivar os termos efetivamente aplicáveis ao IPCA do IBGE distribuído no SGS, ou esclarecimento oficial. Não houve envio de mensagem ou contato humano com BCB/IBGE.

Atribuição proposta, sem alegar licença não identificada: “IPCA — variação mensal. Produtor: IBGE. Distribuição: Banco Central do Brasil, SGS, série 433.” Manter referência/data, unidade e fonte; identificar transformações e agregações do projeto separadamente. MIT do código não licencia os dados.

## Limites de consulta e cobertura histórica

O [catálogo oficial do dólar SGS 1](https://dadosabertos.bcb.gov.br/dataset/1-taxa-de-cambio---livre---dolar-americano-venda---diario), arquivado nesta execução, informa obrigatoriedade de filtros e limite de dez anos para consultas por período, com erro fora dessa condição, na alteração anunciada para 26/03/2025. Não se fez uma consulta deliberadamente inválida para confirmar esse erro. Lotes anuais e intervalo conservador do projeto não são quotas oficiais.

A [página oficial IPCA](https://www.ibge.gov.br/estatisticas/economicas/precos-e-custos/9256-indice-nacional-de-precos-ao-consumidor-am-plo.html?=&t=series-historicas) aparece na pesquisa web com seção de datas de divulgação e início/fim da coleta de 2012 a 2026. O HTTP direto desta execução recebeu 403; não foram baixados nem homologados os calendários históricos a partir desse indício. O calendário 2026 já conferido possui evidência própria em [calendário IPCA](calendario-ipca.md).

Para afirmar completude histórica é necessário conferir referências mensais esperadas do IPCA, inclusive os onze meses técnicos de 2019, e calendários/regras oficiais aplicáveis às séries diárias em cada ano. Conferir somente início/fim e quantidade de fatos não demonstra ausência de lacunas. Feriados, dias sem observação, revisões e diferenças entre data da referência e divulgação precisam permanecer explícitos; não preencher datas por interpolação ou zero. A existência de calendário do produtor não estabelece prazo de replicação no BCB.

Até essa conferência, preservar `cobertura.completa=null` e o motivo `CALENDARIO_NAO_HOMOLOGADO`. A integridade dos lotes coletados, idempotência e igualdade core/gold/HTTP já demonstradas são propriedades distintas da completude oficial histórica.
