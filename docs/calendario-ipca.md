# Calendário do IPCA — conferência de 18/11/2026

Atualização 23/11/2026: as referências históricas mensais do IPCA foram confrontadas com nova resposta oficial e com o banco: 93/93 no recorte, sem faltas. A licença específica e o calendário do dólar permanecem pendentes. Ver [nova conferência](conferencia-fontes-2026-11-23.md). O registro abaixo é histórico.

## Conclusão desta consulta

A referência outubro/2026 recebida na série BCB/SGS 433 é compatível com o calendário oficial em 18/11/2026. A publicação de outubro ocorreu em 12/11/2026 às 09h, conforme a capa do [fascículo oficial IPCA/INPC](https://ftp.ibge.gov.br/Precos_Indices_de_Precos_ao_Consumidor/INPC/Fasciculo_Indicadores_IBGE/ipca-inpc_202610caderno.pdf). A [API oficial do calendário IBGE](https://servicodados.ibge.gov.br/api/v3/calendario/?produto=9256) informa novembro para 11/12/2026 e dezembro para 12/01/2027. Datas futuras são previsões sujeitas a revisão.

O produtor é o IBGE; o BCB distribui a série SGS 433. Calendário de divulgação do produtor não é SLA de replicação no BCB. Não confundir IPCA (produto 9256) com INPC (9258) ou IPCA-15 (9260), nem data da referência com dia de publicação.

| Referência de 2026 | Divulgação informada pelo calendário |
|---|---|
| Janeiro | 10/02/2026 |
| Fevereiro | 12/03/2026 |
| Março | 10/04/2026 |
| Abril | 12/05/2026 |
| Maio | 12/06/2026 |
| Junho | 10/07/2026 |
| Julho | 11/08/2026 |
| Agosto | 11/09/2026 |
| Setembro | 09/10/2026 |
| Outubro | 12/11/2026 |
| Novembro | 11/12/2026 — prevista |
| Dezembro | 12/01/2027 — prevista |

## Evidência e limites da coleta

Corpos originais em dados/descoberta/calendario_ipca_20261118/, fora do Git. metadados.json registra URL final, parâmetros, HTTP, instante UTC, tamanho e SHA-256. A consulta ocorreu em 19/11/2026 00:55 UTC, ainda 18/11 em America/Sao_Paulo.

- publicacao_outubro.pdf: HTTP 200, 419031 bytes, SHA-256 5e7ddcbe40720d2da93256c21b5e5c28abda2247e3de6a3627cff79e357d9a70.
- calendario.json: HTTP 200, 3308649 bytes, SHA-256 19f6021aa9b7fc2825c0ccef6efbf1667d20cb2ac20f213f2a8595f7d4b5c8a5.
- A página HTML do produto retornou HTTP 403; o corpo da falha foi preservado. Não foi considerada uma consulta HTML bem-sucedida.

A chamada com produto=9256 retornou 2449 itens de vários produtos, página 1/1, nextPage=0. O parâmetro não restringiu a resposta nesta sondagem: a seleção efetiva foi feita localmente por produto_id=9256 e ano_referencia_inicio=2026. Foram conferidos os doze meses sem duplicatas. avaliacao.json guarda os IDs oficiais selecionados e a avaliação derivada. Não construir um conector assumindo que o filtro enviado foi aplicado.

O campo data_divulgacao da API não explicita fuso e traz 12:00:00; nesta homologação foram usadas somente suas datas. O horário de publicação de outubro acima veio do PDF, que declara 09h. Não inferir conversão de fuso sem contrato oficial.

## Como interpretar o aviso atual

Na conferência manual anterior, a aplicação usava HEURISTICA_45_DIAS desde o primeiro dia do mês de referência: de 01/10 a 18/11 são 48 dias. Por isso a validação anterior registrou FRESCOR_POTENCIALMENTE_DEFASADO e a API podia informar defasado=true mesmo com outubro dentro do calendário esperado. Para esta data, o aviso é um falso positivo da heurística frente ao calendário consultado; não prova indisponibilidade do BCB.

O aviso e a auditoria foram preservados. A conferência manual preservou o limiar e a auditoria. A implementação posterior descrita abaixo passou a avaliar o frescor automaticamente; o registro anterior permanece como evidência da investigação. A cobertura pública continua declarada CALENDARIO_NAO_HOMOLOGADO porque não foi verificado o calendário completo de todas as séries/anos.

Vigência, versão, tolerância, fallback e testes foram implementados na etapa abaixo. Atualizações de previsões permanecem manuais e exigem nova evidência oficial. Licença específica do dataset 433 continua pendente; calendário verificado não resolve esse item.

## Avaliação automática implementada

processamento/frescor.py compartilha a política entre API e qualidade. Snapshot derivado em src/pipeline_etl/calendarios/ipca_2026.json contém apenas os doze registros oficiais do produto 9256, com IDs originais, datas, URL, SHA-256 do corpo oficial e instante UTC da consulta. Ele integra o wheel e a imagem por ser recurso do pacote; não depende da pasta operacional dados/. O SHA-256 identifica a origem arquivada, não é assinatura digital do snapshot derivado.

Decisões locais, não SLAs oficiais:

- Vigência inclusiva: 18/11/2026 até 18/12/2026, no calendário de America/Sao_Paulo. Política geral: data da consulta até consulta + 30 dias. Antes/depois desse intervalo, usar fallback.
- Divulgação avaliada por data, sem inferir fuso de 12:00:00 da API IBGE. Um dia corrido completo após a divulgação é tolerado para replicação no BCB. Referência passa a ser exigida quando hoje > divulgação + 1 dia.
- Novembro previsto para 11/12: em 11 e 12/12, outubro ainda atende; a partir de 13/12 exige-se novembro. Previsões podem mudar e precisam de revisão antes de renovar o snapshot.
- Atraso pelo calendário retorna CALENDARIO_IBGE e REFERENCIA_ATRASADA; referência adequada retorna REFERENCIA_EM_DIA. Ausência de referência ou data futura/IPCA fora do primeiro dia do mês retorna defasado=null com SEM_REFERENCIA/REFERENCIA_INVALIDA.
- Snapshot ausente, inválido, ainda não vigente, expirado, fora da cobertura ou sem referência vencida recorre à HEURISTICA_45_DIAS com motivo explícito. Séries diárias conservam HEURISTICA_4_DIAS. A ausência/corrupção do recurso não impede a API de iniciar.

/api/v1/pipeline/frescor conserva os campos existentes e acrescenta motivo, referencia_esperada, data_limite e versao_calendario. calendario_homologado=true indica uso efetivo do calendário para frescor; cobertura.completa continua null e cobertura.motivo continua CALENDARIO_NAO_HOMOLOGADO porque a cobertura histórica de todas as séries não foi certificada. data_limite corresponde à referência esperada retornada, não à próxima atualização do calendário. Em fallback/sem referência, dados do calendário aplicado ficam null.

Qualidade só avalia janelas encerradas perto da data atual. Com calendário, a janela precisa conter a referência esperada; uma consulta restrita a novembro antes de sua divulgação não é interpretada como falta de outubro. Novas validações guardam avaliacoes_frescor nos parâmetros privados de ops.execucao, com índice do artefato, política, motivo, referência/data limite e versão. O endpoint público de execuções continua sanitizado. Alertas e auditoria anteriores permanecem intocados.

## Atualizar o snapshot sem renovar previsão antiga

1. Consultar novamente a API oficial em operação manual separada, preservar bytes originais e registrar URL/parâmetros/HTTP/instante UTC/SHA-256 fora do Git. Verificar paginação; filtrar produto_id=9256 no cliente e conferir doze referências do ano.
2. Conferir alterações de previsões e o produtor correto. Gerar o recurso derivado com IDs e datas reais, consultado_em do novo HTTP e fonte_sha256 do novo corpo. versao usa ibge-ipca-AAAAMMDD-PREFIXO_SHA_12, onde a data é a consulta em São Paulo. Não alterar só a data de consulta para prolongar vigência sem nova resposta oficial.
3. Se precisar mudar o ano, atualizar recurso/caminho como mudança revisada. O carregador recusa quantidade, ordem mensal, IDs repetidos, datas anteriores ao término da referência, fuso ausente, versão e hash malformados. Dados oficiais brutos nunca são sobrescritos para satisfazer esses critérios.
4. Rodar testes offline, validar carregamento e empacotamento. Publicar uma nova versão do código só quando autorizado. Não há chamada IBGE em requisições da API ou jobs automáticos de renovação.

## Evidência da implementação

309 testes aprovados, cobertura global 96,63%; Ruff/formatação, mypy (42 arquivos) e Bandit aprovados. Wheel reconstruído e carregado em diretório separado: calendário incluído e política correta sem ler dados/ operacional. A primeira tentativa de build identificou a exclusão da pasta chamada dados/ pela regra do Git; o recurso passou à pasta calendarios/. Um mock HTTP de integração foi corrigido para entregar streaming de bytes, sem alterar o cliente.

Sondagem HTTP real local comparou todas as 4323 observações públicas e 351 agregados com SQL, preservou fatos/gerações/auditoria e encerrou o próprio servidor. O IPCA retornou defasado=false, CALENDARIO_IBGE, REFERENCIA_EM_DIA, referencia_esperada=2026-10-01, data_limite=2026-11-13 e versão ibge-ipca-20261118-19f6021aa9b7. Relatório operacional: dados/descoberta/sondagem_api_bcb.json. Testes específicos cobrem limites divulgação/tolerância/vigência, fallback, ausência/corrupção, referências inválidas, janela avaliada e persistência dos detalhes. Revisão independente não encontrou problemas importantes.
