# Fontes — descoberta inicial

Atualização posterior de 23/11/2026: a pendência de datas do dólar foi resolvida no recorte carregado: 1.728/1.728 datas na API oficial PTAX e 68 ausências classificadas pelos calendários ANBIMA. Ver [conferência do dólar](conferencia-dolar-2026-11-23.md). A confirmação dos termos específicos aplicáveis ao IPCA continua aberta; [solicitação preparada, não enviada](solicitacao-termos-ipca.md). O conteúdo anterior abaixo preserva o estado histórico.

Atualização 23/11/2026: as referências históricas mensais do IPCA foram confrontadas com nova resposta oficial e com o banco: 93/93 no recorte, sem faltas. A licença específica e o calendário do dólar permanecem pendentes. Ver [nova conferência](conferencia-fontes-2026-11-23.md). O registro abaixo é histórico.

Referência local da sessão: 17/11/2026. Coletas registradas em UTC nos metadados (18/11 UTC, ainda 17/11 em America/Sao_Paulo).

## BCB: consultas reais

| Série | Código | Janela | HTTP | Registros | SHA-256 |
|---|---|---|---|---|---|
| Meta Selic | 432 | 02/01/2020 a 06/01/2020 | 200 | 5 | 3f8a8a942d1ec01000faadd251aacde0badedd0b8c0eb8a29601b1365eecd639 |
| IPCA mensal | 433 | 01/01/2020 a 01/03/2020 | 200 | 3 | bccb755efe8fc808df5e0b02409a9b7fe4a29afa9b25234dc3ba6f81f3df0570 |
| Dólar venda | 1 | 02/01/2020 a 06/01/2020 | 200 | 3 | df05f9558fb93676c21044c15e4359a1ec804303fbcd6a0c1f00f08b99798d45 |

Origem: Banco Central do Brasil/SGS; produtor IPCA: IBGE. Dados públicos agregados, sem dados pessoais nas amostras. Corpos originais salvos antes do parse; cópias versionáveis em [amostras](../testes/amostras/bcb/), acompanhadas de metadados com origem, URL, parâmetros, instante UTC e SHA-256. Dados operacionais em dados/descoberta ficam fora do Git.

Verificado: lista não vazia, chaves exatamente data/valor, datas DD/MM/AAAA e Decimal finito. Amostras não substituem testes futuros de retry/falhas.

### Contrato observado

- data e valor são strings; separador decimal ponto nas amostras.
- Meta Selic 432: % a.a., diária; janela retornou cinco datas incluindo fim de semana. Não impor calendário de pregão a essa série.
- IPCA 433: percentual mensal; datas no primeiro dia do mês na amostra janeiro–março/2020.
- Dólar 1: BRL/USD; janela retornou três datas. Não preencher feriados/fins de semana.
- Parâmetros externos dataInicial/dataFinal/formato preservados; nomes próprios internos em português com snake_case.

### Referências e licença

- [Catálogo Meta Selic 432](https://dadosabertos.bcb.gov.br/dataset/432-taxa-de-juros---meta-selic-definida-pelo-copom): consultado oficialmente, unidade e licença ODbL identificadas.
- [Catálogo dólar 1](https://dadosabertos.bcb.gov.br/dataset/1-taxa-de-cambio---livre---dolar-americano-venda---diario): metodologia/unidade e ODbL identificadas na revisão.
- [SGS IPCA 433](https://www3.bcb.gov.br/sgspub/consultarvalores/consultarValoresSeries.do?method=consultarSeries&series=433): identificação/periodicidade confirmadas. Licença específica e página de catálogo ainda a localizar; não presumir por analogia.
- Catálogo diário informa filtro obrigatório/janela de até dez anos desde 26/03/2025. Lote anual e intervalo de 1s são limites conservadores do projeto, não quotas oficiais.
- Atribuir produtor, BCB/SGS, série, unidade, URL, coleta e transformação. Conferir termos ODbL antes de redistribuição ampliada. MIT do código não rege dados.

API CKAN adicional: package_show 432/1 retornou 403; busca 433 retornou HTTP 200 com zero resultados. Isso não indica ausência da série. O endpoint de catálogo presumido para 433 retornou 404; não o usar como fonte homologada.

## IBGE: metadados confirmados, valores pendentes

- [Metadados 6579](https://servicodados.ibge.gov.br/api/v3/agregados/6579/metadados) e [períodos](https://servicodados.ibge.gov.br/api/v3/agregados/6579/periodos) retornaram HTTP 200 na consulta direta.
- Confirmados: população residente estimada, variável 9324, unidade Pessoas, anual, nível N6 e nenhuma classificação.
- Recorte 2020+: 2020, 2021, 2024, 2025, 2026. Ausentes 2022/2023 nessa tabela; não completar com censo/interpolação.
- Corpos e hashes em dados/descoberta/ibge_metadados.body, ibge_periodos.body e respectivos .metadados.json.
- Ainda faltam Localidades, valores municipais, marcadores, cobertura e termos/licença; não iniciar conector apenas com metadados.

## Pendências da Fase 0

- [x] Três respostas reais BCB com origem, parâmetros e checksum.
- [x] Estrutura, datas e números verificados.
- [x] Metadados/períodos IBGE oficiais.
- [x] Calendário IPCA de 2026 conferido e arquivado; ver [evidências e limites](calendario-ipca.md).
- [x] Avaliação automática de frescor por calendário IPCA versionado, com vigência e fallback; ver docs/calendario-ipca.md.
- [ ] Demais anos/calendários e licença específica/catálogo da série 433.
- [ ] Comportamento de resposta vazia/limites documentados, sem chamadas agressivas.
- [x] Recorte BCB desde 2020 consultado até18/11/2026 e apoio IPCA fevereiro–dezembro/2019 carregados; ver docs/historico-real-m1.md. Calendário completo continua pendente.
- [ ] Localidades, valores, marcadores, cobertura e licença IBGE antes de M2.

Suíte automatizada futura usa amostras/mocks offline; sondagens externas ficam separadas.

## Sondagem com o cliente implementado — 18/11/2026

A CLI coletar bcb consultou somente a Meta Selic432 no período 02/01/2020–06/01/2020. HTTP200,186 bytes e cinco observações constatadas manualmente; checksum idêntico à amostra original. Corpo/metadados/manifesto preservados no bronze; relatório local em dados/descoberta/sondagem_coleta_bronze.json. Sem carga SQL ou homologação adicional de todas as regras de negócio. Ver docs/coleta-e-bronze.md.

## Carga histórica real — 18/11/2026

As três séries retornaram HTTP200 em22consultas anuais (incluindo apoio2019); incremental real consumiu mais5consultas. Foram preservadas 4.334 observações no core, sendo 4.323 públicas. Últimas referências: Selic/dólar18/11/2026 e IPCA01/10/2026. Contagens e verificações não equivalem à homologação do calendário. Evidências em [histórico real](historico-real-m1.md).

## Calendário IPCA — 18/11/2026

API oficial IBGE e fascículo de outubro arquivados com metadados e hashes. Outubro publicado em 12/11; novembro previsto para 11/12. Referência atual compatível com o calendário: aviso da heurística de 45 dias não prova atraso. Filtro efetivo por produto 9256 aplicado no cliente, porque a resposta incluiu outros produtos. Ver [calendário IPCA](calendario-ipca.md); HTML retornou 403 e não foi declarado homologado.
