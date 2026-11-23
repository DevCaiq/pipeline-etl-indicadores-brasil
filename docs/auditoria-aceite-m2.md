# Auditoria final de aceite local M1/M2 — 23/11/2026

Decisão posterior do responsável em 23/11/2026: seguir sem solicitação de autorização individual para o protótipo local. A espera por resposta deixa de bloquear o aceite local; atribuição e limitações dos termos permanecem. [Decisão de escopo](decisao-aceite-local-m1-m2.md). A minuta não foi enviada e o conteúdo anterior abaixo é histórico.

Atualização posterior de 23/11/2026: a pendência de datas do dólar foi resolvida no recorte carregado: 1.728/1.728 datas na API oficial PTAX e 68 ausências classificadas pelos calendários ANBIMA. Ver [conferência do dólar](conferencia-dolar-2026-11-23.md). A confirmação dos termos específicos aplicáveis ao IPCA continua aberta; [solicitação preparada, não enviada](solicitacao-termos-ipca.md). O conteúdo anterior abaixo preserva o estado histórico.

A auditoria foi reconciliada com a suíte agregada e execuções reais. A entrega
técnica M2 local foi verificada; o aceite integral ainda carrega ressalvas de
homologação das fontes M1. CI remoto e M3 foram adiados por decisão do responsável.
[Relatório consolidado](aceite-tecnico-m2.md).

| Critério | Estado e evidência |
|---|---|
| Base técnica M1 preservada | Suíte BCB, papéis reais, indicadores, cursores, replay e falha de refresh continuam aprovados. Runbook consolidado |
| Setup reproduzível e banco | Reprodução limpa já arquivada; migrações do zero e downgrade/upgrade testados em etl_testes; imagem/API reais verificadas |
| Três séries e histórico 2020+/apoio de 2019 | Dados técnicos coletados e apoio separado; licença SGS433 e completude oficial histórica permanecem sem homologação integral |
| Bronze, integridade, contratos e idempotência | Amostras oficiais/mocks offline, checksum e imutabilidade; replay de 79 cargas BCB e 27.855 fatos IBGE sem alterar metadados |
| IBGE, base territorial e cobertura | Cinco anos de estimativas, lacunas2022/2023 e marcadores preservados; associação atual na coleta, sem afirmar malha histórica |
| Gold/API por domínio | Gerações independentes; nenhuma soma incompleta é publicada como total completo; rotas e paginação testadas |
| Redis/ETag/stampede/gerações | Testes automatizados e Redis real isolado confirmaram acerto, reinício, fallback e HTTP 200. Métricas em /metrics e Grafana |
| S3/MinIO | Contrato comum, replay real, permissões, colisões, checksum e persistência já conferidos |
| Prefect | Seis deployments locais, limite global1, descarte conservador e tarefas Windows retomadas |
| Observabilidade | Três dashboards (5/9/8 gráficos), oito regras, contagens/frescor/cobertura/HTTP/retries/cache; métricas comparadas ao SQL |
| Alerta local | API indisponível provocado e resolvido em 19/11, evidência preservada; promtool check/test aprovados |
| Benchmark | Um milhão sintético; p95sem cache158,75 ms e com cache 126,87 ms medidos em 19/11, com escopo e limites documentados |
| Restore e demo | Snapshot arquivado recomposto em outro dia com referência durável; comparação integral/cursor e nova publicação no clone;125,359 s em 23/11 |
| Cobertura |588 testes, 95,80% global e 15 módulos críticos>=95%; gates locais aprovados, incluindo contratos/carga/API IBGE |
| Checks/build/segurança | Ruff/formato, mypy 56 módulos, wheel e imagem; Bandit zero achados/erros; pip-audit sem vulnerabilidades conhecidas em 23/11 |
| CI no GitHub | Workflow preparado com gates, mas não executado remotamente; adiamento explícito, sem alegar aprovação externa |
| Licenças/completude de fonte | Ressalva permanece; termos gerais não viraram licença nominal, calendários não conferidos não foram inventados |

## Revisões e regressões

Dois achados operacionais foram reproduzidos e corrigidos: descoberta IBGE confirmada
ocultada por falha posterior e timestamp inválido interrompendo o exporter.
A demonstração entre datas revelou dependência de relógio nas materializadas BCB;
a0010 passou a usar referência persistida, com atualização transacional no publicador.
A revisão apontou risco de recomposição com core pendente: proteção por trava e
recusa desse estado foram testadas. A revisão final de métricas de cache não
encontrou defeitos concretos; callback defeituoso não altera a resposta da consulta.

Os críticos IBGE inicialmente estavam abaixo de 95%. Casos relevantes de rejeição,
rollback e paginação foram acrescentados e os gates passaram na suíte final.
Os percentuais globais não foram usados como substitutos desses gates individuais.

Bandit antes travava ao escrever o cache do stevedore fora do workspace. O diagnóstico
com faulthandler apontou NamedTemporaryFile; LOCALAPPDATA foi redirecionado apenas no
subprocesso para .cache. Cinco ocorrências foram revisadas individualmente e receberam
supressões específicas justificadas: asserts redundantes de tipo/contrato, jitter de
TTL sem uso criptográfico e identificadores SQL de mapas fechados. Nenhuma regra
foi desabilitada globalmente. A análise final produziu zero achados e erros.

## Limite do aceite integral

[Homologação BCB](homologacao-bcb-m1.md) e
[complemento de fontes](complemento-fontes-aceite-m2.md) registram produtor,
atribuição, respostas oficiais arquivadas e falhas de acesso aos documentos.
Não há evidência suficiente para afirmar licença nominal SGS433 nem ausência de
lacunas segundo todos os calendários históricos diários. Manter cobertura.completa
como desconhecida e CALENDARIO_NAO_HOMOLOGADO quando aplicável. Não aplicar licença
de outro dataset ao IPCA nem confundir MIT do código com licença dos dados.

Os testes e a operação local foram concluídos; as ressalvas documentais não foram
silenciosamente dispensadas. Por isso o primeiro item do DoD M2 permanece qualificado
pela homologação M1, sem impedir a descrição factual da entrega técnica verificada.
Nenhum contato humano, repositório, recurso externo ou publicação foi realizado.


## Complemento da homologação histórica

Em23/11/2026, o novo calendário oficial foi confrontado com as datas do core por
consulta somente leitura. IPCA:93 esperadas/93 carregadas,82 públicas e11apoio de 2019,
zero faltantes e zero inesperadas no recorte fevereiro/2019–outubro/2026. Isso
resolve a conferência de referências mensais,sem validar numericamente todos os
valores ou estender a conclusão ao dólar. Evidência e fontes na
[conferência documental](conferencia-fontes-2026-11-23.md). A ressalva de licença
individual e calendário de cotações do dólar permanece,sem dispensa implícita.

## Encerramento da conferência histórica do dólar — 23/11/2026

1.728 datas oficiais PTAX coincidem com o banco; nenhuma divergência. As 68 ausências
em dias de semana foram classificadas, sem preencher dados. [Relatório](conferencia-dolar-2026-11-23.md).
A ressalva documental específica do IPCA permanece como único bloqueio de fonte
identificado para o aceite local integral. CI remoto e M3 permanecem adiados.
