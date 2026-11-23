# Conferência das fontes e referências históricas — 23/11/2026

Atualização posterior de 23/11/2026: a pendência de datas do dólar foi resolvida no recorte carregado: 1.728/1.728 datas na API oficial PTAX e 68 ausências classificadas pelos calendários ANBIMA. Ver [conferência do dólar](conferencia-dolar-2026-11-23.md). A confirmação dos termos específicos aplicáveis ao IPCA continua aberta; [solicitação preparada, não enviada](solicitacao-termos-ipca.md). O conteúdo anterior abaixo preserva o estado histórico.

## Resultado

A pendência de conferência das **referências mensais do IPCA no recorte do projeto**
foi resolvida: 93 esperadas e 93 carregadas, sem referência ausente ou inesperada.
São 82 referências públicas desde 2020 e 11 de apoio (fevereiro–dezembro/2019).
A conferência não equivale a validar os valores de cada mês ou todos os calendários
diários. Não altera a política de cobertura da API.

| Tema | Resultado desta etapa |
|---|---|
| IPCA SGS433 | Referências de fevereiro/2019 a outubro/2026 conferidas com calendário oficial |
| Selic SGS432 | 2.519 datas civis de 01/01/2020 a 23/11/2026; nenhuma data ausente dentro desse intervalo |
| Dólar SGS1 | 1.728 observações de 02/01/2020 a 19/11/2026; 68 dias de semana sem observação ainda exigem calendário específico |
| Termos BCB | Autorização geral de reprodução atribuída confirmada em extração indexada; HTML direto ainda não contém o texto integral |
| Produtor IBGE | Plano de Dados Abertos 2024–2025 obtido e arquivado; não identifica licença nominal da série SGS433 |
| Aceite integral | Continua condicionado aos termos específicos aplicáveis e ao calendário de cotações do dólar |

## Referências do IPCA: prova e recorte

Foi preservada uma nova resposta da [API oficial do calendário IBGE](https://servicodados.ibge.gov.br/api/v3/calendario/?produto=9256)
antes de interpretar o JSON. O parâmetro produto não filtrou efetivamente o corpo:
a seleção foi feita localmente por `produto_id=9256`. Paginação 1/1, sem próxima
página; 2450 itens no corpo e 96 referências IPCA em 2019–2026, com 12 meses por ano.
Os campos finais de referência usam zero para ausência de intervalo; foram usados
ano/mês iniciais, sem fabricar datas finais.

Datas de divulgação foram comparadas como datas, sem inventar fuso para horários
não qualificados pela fonte. Foram selecionadas as referências já divulgadas até
23/11/2026 e a partir de fevereiro/2019. Janeiro/2019 está fora do apoio necessário;
novembro e dezembro/2026 ainda eram futuros no calendário consultado.

| Ano | Referências carregadas no recorte |
|---|---:|
|2019|11 de apoio|
|2020|12|
|2021|12|
|2022|12|
|2023|12|
|2024|12|
|2025|12|
|2026|10(janeiro–outubro)|

O corpo antigo, arquivado em 18/11, continha o mesmo histórico útil, mas antes só 2026
havia sido conferido. Sua integridade também foi revalidada e ele foi preservado.
O novo relatório guarda o ID oficial e a divulgação de cada uma das93 referências,
além das listas vazias de faltas e referências inesperadas.

A consulta SQL usou `api_leitura`, em transação `REPEATABLE READ READ ONLY`, sem
alterar fatos, checkpoints, bronze ou materializadas. Completude de referências nesse
recorte não garante prazo de replicação do BCB nem precisão histórica dos valores.
O calendário de divulgação do produtor não é calendário de mercado das séries diárias.

## Termos de uso e atribuição

Os [termos gerais BCB](https://www.bcb.gov.br/acessoinformacao/politicaprivacidade)
preveem reprodução do conteúdo do site e dos serviços digitais com integridade
e crédito à origem. Essa cláusula foi conferida na extração indexada da página.
O GET original foi arquivado, mas continuou entregando apenas o contêiner JavaScript.
O excerto curto guardado é identificado como extração indexada; seu hash não foi
apresentado como hash de uma cópia integral dos termos.

O [PDA IBGE 2024–2025](https://www.ibge.gov.br/np_download/novoportal/documentos_institucionais/Plano_de_Dados_Abertos_IBGE_2024_2025.pdf)
foi obtido em PDF. Ele descreve os canais de disseminação e utiliza o IPCA como
exemplo; o anexo inclui a tabela 7060 de IPCA e a 6579 de população estimada. Trata-se
de contexto institucional de dados abertos, não de licença individual SGS433.
Sua vigência2024–2025 também não foi reinterpretada como novo termo de 2026.

O [Decreto 8.777/2016, art.4º](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2016/decreto/d8777.htm)
fornece contexto para reutilização de dados federais e distingue direitos de terceiros.
Não foi usado para inventar ODbL/CC BY, domínio público ou titularidade patrimonial
para o IPCA. A abertura direta dessa página teve timeout; a consulta textual oficial
foi feita pela ferramenta de pesquisa, com esse limite explicitado.

Registro de atribuição para a série: **IPCA, variação mensal. Produtor: IBGE.
Distribuição: Banco Central do Brasil, SGS433.** Acrescentar URL/parâmetros,
referência, instante UTC e checksum da coleta. Médias, agregações e composições do
projeto são transformações próprias, com código separado das condições dos dados.
A licença MIT do código não atribui uma licença aos dados oficiais.

Não foi encontrada licença nominal individual nem manifestação oficial que resolva
expressamente toda a cadeia de direitos da série433. Não foram enviados e-mails,
protocolos ou solicitações aos órgãos. A permissão geral está documentada; o item
de homologação específica continua aberto em vez de ser dispensado implicitamente.

## Séries diárias: limite da conferência

Na Selic, comparou-se o conjunto real de datas com todos os dias civis entre mínimo
e máximo:2519/2519. É continuidade descritiva desse intervalo, não prova de política
de publicação. Não se aplicou calendário de pregão à meta Selic, que tem observações
em fins de semana.

No dólar, 1728 observações foram comparadas com 1796 dias de semana no intervalo
carregado. Os68 dias restantes são candidatos a feriados ou outras ausências, ainda
não classificados nesta conferência. Não são automaticamente68 erros de carga.
A lista completa está no relatório. Última referência19/11 não implica falta em
20/11 ou na manhã de 23/11 sem verificar feriado e horário de divulgação.

A [Resolução 2932/2002](https://normativos.bcb.gov.br/Lists/Normativos/Attachments/46961/Res_2932_v4_L.pdf)
e a [Resolução CMN 4.880/2020](https://www.bcb.gov.br/estabilidadefinanceira/exibenormativo?numero=4880&tipo=RESOLU%C3%87%C3%83O+CMN)
são referências oficiais para a próxima conferência, considerando datas de vigência.
Dias de atendimento bancário, liquidação e divulgação de cotação não são presumidos
intercambiáveis. Feriados estaduais/municipais e mudanças legais precisam do
tratamento apropriado à série. Não se preencheu ausência com zero ou interpolação.

## Arquivo das evidências e reprodução

Pasta privada `dados/descoberta/fontes_aceite_20261123_064251/`, ignorada pelo Git:

- `metadados.json`: URLs, parâmetros, UTC, status, tamanho e SHA-256 dos corpos obtidos;
  também registra timeout/403/502, sem convertê-los em evidência de sucesso.
- `calendario_atual.json`: HTTP 200,3.309.287 bytes,
  SHA-256`8e565dba3241ca02a514fca5840e75f09cd5c75f2c70ea52b5128d66357047f9`.
- `pda_ibge_2024_2025.pdf`: HTTP 200,982.498 bytes,
  SHA-256`9c56d0c952a326d9489e2e829fa12795570ae8fb65d34633268f03b22b599e02`.
- `extracao_termos_bcb.json`/`condicao_reproducao_bcb.txt`: tipo de evidência distinto
  dos originais HTTP, com hash do excerto e limite do acesso integral.
- `conferencia_referencias.json`: verificação inicial usando o snapshot18/11.
- `conferencia_referencias_atual.json`: conferência atual com as 93 referências,
  seus IDs/datas e os diagnósticos das duas séries diárias.

Para repetir: verificar o SHA do corpo contra os metadados, conferir paginação,
filtrar 9256 e a faixa de anos, recusar referência duplicada, conferir12 meses por ano,
selecionar meses já divulgados no corte e comparar datas do primeiro dia do mês
com `core.fato_serie` para 433. A consulta deve permanecer somente leitura.
Não atualizar apenas a data de um snapshot para prolongar sua vigência.
Os scripts usados nesta investigação ficam no cache operacional local; o relatório
registra os parâmetros e as fontes para reprodução independente.

Nenhum código da aplicação, migração, amostra oficial ou configuração foi alterado.
A nova consulta de calendário não renovou o recurso de frescor empacotado na API.
GitHub, M3 e a marcação global de aceite permanecem adiados.
