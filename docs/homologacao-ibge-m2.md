# Homologação IBGE — M2 local

Consulta oficial em 19/11/2026 UTC. Respostas preservadas antes do parse em `dados/descoberta/ibge_m2_20261119T040231Z/`, cada corpo acompanhado de URL, parâmetros, instante UTC, HTTP, cabeçalhos, tamanho e SHA-256. Diretório operacional fora do Git. Amostras oficiais pequenas e metadados completos em `testes/amostras/ibge/`. Não houve alteração de fixtures anteriores, banco, Docker ou credenciais.

## Contratos confirmados

[Localidades v1](https://servicodados.ibge.gov.br/api/v1/localidades/municipios): `/regioes`, `/estados` e `/municipios` retornaram HTTP 200, respectivamente 5, 27 e 5.571 objetos. IDs são números no JSON; normalizar código municipal como string de sete dígitos. Nomes externos preservados. Regiões: `id,nome,sigla`; estados: `id,sigla,nome,regiao`. Municípios: `id,nome,microrregiao,regiao-imediata`.

UF/região municipal podem ser obtidas por `regiao-imediata.regiao-intermediaria.UF.regiao`. A cadeia antiga `microrregiao.mesorregiao.UF` coincide onde disponível, mas `microrregiao` é `null` para Boa Esperança do Norte, 5101837. A nova cadeia estava completa nos 5.571 municípios; validar ambas quando presentes, aceitar uma cadeia válida e bloquear ausência/conflito de UF/região. Nenhuma inferência por nome é necessária. Snapshot atual não comprova hierarquia histórica: os totais históricos devem identificar a base territorial atual usada na associação.

[Metadados 6579](https://servicodados.ibge.gov.br/api/v3/agregados/6579/metadados): população residente estimada; pesquisa Estimativas de População; variável 9324; unidade `Pessoas`; frequência `anual`; classificações vazias; níveis administrativos N1/N2/N6/N3. Não é percentual. [Períodos](https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos): `id` string, `literals` lista e `modificacao` DD/MM/AAAA. Último ano observado 2026; descobrir em execução, sem fixá-lo. Disponíveis desde 2020: 2020, 2021, 2024, 2025, 2026. Ausentes 2022/2023 nesta tabela. `modificacao` não deve ser tratada automaticamente como data original de publicação.

Consulta nacional validada HTTP 200:

```text
https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos/2020|2021|2024|2025|2026/variaveis/9324?localidades=N6%5Ball%5D
```

Amostra restrita também validada com `localidades=N6%5B3550308%2C5300108%2C1504752%5D`; marcador real com `N6%5B5101837%5D`. Cliente deve codificar query params. Implementação pode consultar um ano por lote conforme plano; sintaxe por UF e limites oficiais não foram homologados. Não confundir tamanho desta resposta bem-sucedida com quota oficial.

Envelope observado: lista com objeto `id` string `9324`, `variavel`, `unidade`, `resultados`; cada resultado tem `classificacoes` e `series`; cada série tem `localidade: {id,nivel:{id,nome},nome}` e `serie:{ano:valor_string}`. Nível retornado `N6`. Valores inteiros positivos em strings. Nome de localidade pode diferir conforme consulta (`São Paulo (SP)` versus outro formato); associação e deduplicação usam código, nunca nome.

## Cobertura e marcadores

Conjunto de códigos N6 retornados coincide exatamente com snapshot Localidades: 5.571 únicos, zero extras, zero ausentes e zero duplicados. A resposta inclui códigos atuais também em anos anteriores. Cobertura de códigos não significa cobertura numérica completa.

| Ano | Códigos recebidos | Valores numéricos | Marcadores | Soma apenas numérica |
|---|---:|---:|---|---:|
| 2020 | 5571 | 5570 | `...`: 1 | 211755692 |
| 2021 | 5571 | 5570 | `...`: 1 | 213317639 |
| 2024 | 5571 | 5570 | `...`: 1 | 212583750 |
| 2025 | 5571 | 5571 | nenhum | 213421037 |
| 2026 | 5571 | 5571 | nenhum | 214211951 |

Todos os três `...` são Boa Esperança do Norte, 5101837/MT. A mesma série tem 5.877 em 2025 e 5.983 em 2026. Preservar marcador original, valor nulo e motivo de indisponibilidade; nunca imputar zero. [Convenções oficiais IBGE](https://ftp.ibge.gov.br/Estoque/Pesquisa_de_Estoques_%5Bsemestral%5D/2024_2_semestre/PB_2_semestre2024.pdf) descrevem `...` como dado numérico não disponível. Este PDF é de outra pesquisa: comprova convenção institucional, não a causa específica desta ausência em 6579. Não inferir existência histórica ou territorial válida de município a partir do marcador.

Não foram observados `-`, `..`, `x`, `X` ou vazio em 6579. O mesmo PDF distingue zero, não aplicável e sigilo, mas não os homologa nesta tabela. Para M2, aceitar somente inteiros e `...` observado; marcador novo bloqueia lote para revisão. Não criar fixtures inventadas como se fossem oficiais.

Somas acima são verificações aritméticas, não totais oficiais homologados nem comparações com níveis N1/N3. Gold deve informar denominador 5.571 da base atual, valores disponíveis, ausentes e incompletude; não apresentar total parcial como completo em 2020/2021/2024. Exibir subtotal explícito é possível. MT/Centro-Oeste contêm a ausência nesses anos; demais associações foram validadas estruturalmente, sem validar mudanças históricas de limites.

## Licença, atribuição e limites da homologação

[PDA IBGE 2024–2025](https://www.ibge.gov.br/np_download/novoportal/documentos_institucionais/Plano_de_Dados_Abertos_IBGE_2024_2025.pdf?v=2) foi baixado oficialmente HTTP 200 e arquivado. Identifica SIDRA e APIs como canais institucionais de dados abertos, mas não foi identificada licença nominal específica para tabela 6579 ou Localidades. Não atribuir CC/ODbL ou termos da Agência de Notícias por analogia. [Dados Abertos do IBGE](https://www.ibge.gov.br/acesso-informacao/dados-abertos.html) contextualiza o PDA; [termos/privacidade](https://www.ibge.gov.br/acesso-informacao/acoes-e-programas/politica-de-privacidade.html) tratam também dados pessoais, sem comprovar licença nominal desses conjuntos.

Registrar atribuição: IBGE — Instituto Brasileiro de Geografia e Estatística; Localidades v1 / SIDRA tabela 6579, variável 9324; Pessoas/anual; parâmetros, URL, instante de coleta, checksum, base territorial e transformações. MIT do código não licencia esses dados. Licença específica e documentação direta de marcadores da tabela permanecem pendências explícitas antes de redistribuição ampliada/M3, adiado pelo usuário. Homologação técnica suficiente para iniciar conector local com política conservadora acima; não declarar homologação jurídica integral.

Páginas HTML de ajuda SIDRA, documentação Agregados/Localidades e tentativa de termos retornaram HTTP 403. PDFs oficiais e endpoints JSON funcionaram; erros foram anotados no diretório operacional. Zero tentativas agressivas ou acesso a APIs nos testes automatizados. HTTP com intervalo conservador de um segundo, sem afirmar quota oficial.

## Evidências e verificação

Releitura de todos os corpos bem-sucedidos confirmou SHA-256 registrado; fixtures são cópias byte a byte. Análise offline em `analise_cobertura.json`: interseção integral de códigos, unicidade, validação de UF/região em ambas as hierarquias disponíveis e contagem por ano. Consulta externa é sondagem separada da suíte automatizada. Extração parcial do PDF, quando presente, é artefato derivado e não substitui corpo original.

| Artefato operacional `.body` | Bytes | SHA-256 |
|---|---:|---|
| convencoes_oficiais | 443004 | b513c912c3449449d75c6a4815f25a64af1c999e2d2e8c6c1063adffa19619b0 |
| estados | 2446 | 7ca1368dea3af83cba1af84ae8a7e88f1173c97586831d086cc8b3c1ba9c6596 |
| metadados | 444 | 6172ae800a704ad21cfd4f8ae55c2864ef688d172aa305341e84b3964cf45962 |
| municipio_hierarquia_opcional | 268 | 602d721d7f2e46eb945f7ef0d09abec07033bbba830c56078ab884f5c7dc15cd |
| municipios | 2470036 | 86ecdccdf97d72e7e5e46f0854cfcea8bacc28154cc1bc4ed0e6110e3a6c9c02 |
| periodos | 1343 | a64fcf07c29f10eb88b3abe3ed4b67addf6900ad0525988b8f8b84fe4664c2e2 |
| plano_dados_abertos | 982498 | 9c56d0c952a326d9489e2e829fa12795570ae8fb65d34633268f03b22b599e02 |
| populacao_amostra | 704 | 022fa1b940440386ab42e969b84ab28b1eb12d9173e8f8ec581a93242e4cd1d1 |
| populacao_marcador | 314 | ffce7a735f16fef7401efbc463e5743cb40e76203442a501179ac12a35e04635 |
| populacao_todos | 1015292 | f89eaa0fcc11c7f5a15b7f4ee7bc2852736b26ded61648671b96afcd03644fbf |
| regioes | 194 | 7a92480f1e5948b60d184fd11672f6d4e0842c906213f1b57c75db1ed12eb45a |
