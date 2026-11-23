# Complemento de fontes para o aceite M2

Atualização posterior de 23/11/2026: a pendência de datas do dólar foi resolvida no recorte carregado: 1.728/1.728 datas na API oficial PTAX e 68 ausências classificadas pelos calendários ANBIMA. Ver [conferência do dólar](conferencia-dolar-2026-11-23.md). A confirmação dos termos específicos aplicáveis ao IPCA continua aberta; [solicitação preparada, não enviada](solicitacao-termos-ipca.md). O conteúdo anterior abaixo preserva o estado histórico.

Atualização 23/11/2026: as referências históricas mensais do IPCA foram confrontadas com nova resposta oficial e com o banco: 93/93 no recorte, sem faltas. A licença específica e o calendário do dólar permanecem pendentes. Ver [nova conferência](conferencia-fontes-2026-11-23.md). O registro abaixo é histórico.

Consulta documental em 19/11/2026, com pesquisa web atual e abertura dos endereços oficiais abaixo. Nenhum fato BCB/IBGE foi coletado ou alterado; não foram modificadas amostras, calendários, código ou critérios do plano. Este complemento não registra uma licença específica que não foi encontrada.

## Permissão de reprodução e SGS 433

A [Política de Privacidade e Termos de Uso do BCB](https://www.bcb.gov.br/acessoinformacao/politicaprivacidade), seção Reprodução do Conteúdo, autoriza a reprodução de conteúdo do site e dos serviços digitais mediante preservação da integridade e indicação da fonte. A pesquisa web retornou o texto da cláusula e a indicação de atualização em 24/02/2022. A abertura direta nesta verificação entregou apenas o aviso de dependência de JavaScript; não equivale a uma nova cópia integral dos termos arquivada pelo projeto.

**Conclusão operacional:** o termo geral fornece fundamento documental para reprodução atribuída do conteúdo distribuído pelos serviços digitais BCB. Uma licença nominal individual por série não é a única forma possível de registrar uma permissão. Contudo, a aplicação desse termo à cadeia de direitos do IPCA produzido pelo IBGE é uma interpretação de escopo, não um esclarecimento individual do produtor. Não transformar essa inferência em “SGS 433 licenciada ODbL”, “CC BY” ou “domínio público”.

A [página oficial de metadados SGS 433](https://www3.bcb.gov.br/sgspub/consultarmetadados/consultarMetadadosSeries.do?method=consultarMetadadosSeriesInternet&hdOidSerieSelecionada=433) abriu o contêiner da série; seus dois iframes retornaram HTTP 500. A identificação do IPCA e do produtor IBGE já arquivada em [homologação BCB M1](homologacao-bcb-m1.md) permanece a evidência técnica do projeto. A busca atual em catálogos oficiais encontrou séries derivadas do IPCA com ODbL, sem localizar ficha individual 433 que permita transferir essa licença.

Os [termos gerais do Portal IBGE](https://www.ibge.gov.br/acesso-informacao/acoes-e-programas/politica-de-privacidade.html), indexados como versão de 11/03/2024, concentram-se nos serviços e dados pessoais; não foi identificada neles uma licença nominal para os indicadores agregados consumidos. A abertura direta retornou HTTP 403. A [licença da Agência de Notícias IBGE](https://agenciadenoticias.ibge.gov.br/agencia-sala-de-imprensa/2080-agencia-de-noticias/an-artigos-diversos/9277-licenca.html) permite reprodução atribuída do conteúdo da Agência, mas não deve ser estendida automaticamente à API SIDRA ou ao SGS.

Registro recomendado para operação local: “IPCA — variação mensal. Produtor: IBGE. Distribuição: Banco Central do Brasil, SGS, série 433. Reprodução com indicação da fonte e preservação das informações, conforme termos gerais BCB; licença nominal específica da série não identificada.” Guardar unidade, referência, data da coleta e identificação separada das transformações do projeto. MIT do código permanece separado dos dados.

Para encerrar o critério documental integral, obter uma versão integral verificável dos termos gerais aplicáveis e documentar expressamente seu alcance aos dados estatísticos de terceiros, ou obter manifestação oficial BCB/IBGE. Nenhum contato foi enviado. A pesquisa limitada não demonstra que uma licença específica inexista.

## Calendários e cobertura histórica

A [página oficial IPCA do IBGE](https://www.ibge.gov.br/estatisticas/economicas/precos-e-custos/9256-indice-nacional-de-precos-ao-consumidor-am-plo.html?=&t=series-historicas) aparece na pesquisa com calendário de coleta 2026 e referência a datas de divulgação/coleta 2012–2026. A abertura direta retornou HTTP 403. O [relatório metodológico oficial do SNIPC](https://biblioteca.ibge.gov.br/visualizacao/livros/liv101767.pdf) aparece indexado com referência ao calendário de divulgação anual, mas sua abertura também retornou HTTP 403. Não foi possível arquivar/conferir o documento histórico nesta verificação.

Encontrar esse calendário prova que há fonte documental candidata; não prova que cada referência mensal ou dia esperado esteja presente nos fatos do projeto. O calendário do IBGE informa coleta/divulgação do produtor e não assegura prazo de replicação no BCB. Também não é calendário das séries diárias SGS 1 e SGS 432. Esta pesquisa não confrontou os lotes históricos com um conjunto oficial de dias/referências esperados.

| Questão | Tratamento honesto no aceite local | Impedimento preservado |
|---|---|---|
| Frescor atual do IPCA | Usar calendário 2026 já conferido, dentro da vigência; fallback declarado fora dela | Não extrapolar regra de 2026 para todos os anos |
| Histórico desde 2020 e apoio IPCA 2019 | Manter evidências existentes de coleta, checksum e linhagem | Não afirmar completude mensal/diária sem confrontação por referência esperada |
| Dias sem observação | Preservar ausência, HTTP404 conhecido e políticas de validação; não criar zero ou interpolação | Ausência de fato não identifica sozinha feriado, indisponibilidade ou lacuna |
| IBGE população sem anos 2022/2023 no agregado usado | Expor anos realmente disponíveis e manter ausência explícita | Não inventar estimativa ou substituir silenciosamente por censo |
| Licença SGS 433 | Registrar termos gerais BCB, atribuição IBGE/BCB e limitação nominal | Não declarar homologação integral individual enquanto persistir a questão documental acima |

As lacunas de calendário são compatíveis com operação local que informa incerteza. Elas impedem afirmar sem ressalvas “histórico completo” ou encerrar por equivalência o critério literal de homologação integral. Preservar `cobertura.completa=null` e `CALENDARIO_NAO_HOMOLOGADO` até conferência efetiva. A exceção proposta para aceite local deve ser registrada como decisão de escopo; este documento não presume que o responsável já a aprovou.

## Resultado da verificação

O termo geral BCB é uma alternativa documental concreta à busca exclusiva por licença nominal 433, sob suas condições de reprodução. Nesta janela, permanecem sem comprovação integral o alcance individual para conteúdo de terceiro e a confrontação histórica por calendários oficiais. As falhas 403/500 e o shell JavaScript foram registradas como limitações de acesso, sem convertê-las em aprovação. [Auditoria de aceite](auditoria-aceite-m2.md) e [homologação M1](homologacao-bcb-m1.md) continuam válidas com essas ressalvas; nenhum checkbox foi alterado.
