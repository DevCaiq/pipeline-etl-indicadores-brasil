# API de consulta BCB — M1

A API FastAPI consulta core/gold com o papel api_leitura. Todas as rotas são GET; nenhuma dispara coleta, carga ou publicação. A entrega é local, em 127.0.0.1, com esquema 0006. O recorte de 2020 a 18/11/2026 foi carregado: 4.323 observações públicas nas três séries, além de 11 registros técnicos de apoio IPCA. Calendário, recuperação e demais critérios globais ainda têm pendências; veja [validação com dados reais](historico-real-m1.md).

## Iniciar no Windows

Na raiz D:/pipeline-etl, com Docker Desktop aberto:

```powershell
uv sync --frozen
docker compose --env-file .env.banco up -d --wait banco
docker compose --env-file .env.banco run --build --rm migracoes
uv run --frozen python scripts/preparar_api.py
uv run --frozen pipeline-etl servir
```

A documentação interativa fica em http://127.0.0.1:8000/docs e o contrato em /openapi.json. Health e ready ficam na raiz. Ctrl+C encerra o servidor e o ciclo de vida libera o pool. Porta alternativa: servir --porta 8123.

scripts/preparar_api.py já foi executado nesta entrega. Ele cria .env.api exclusivamente, usando a senha de api_leitura em .env.banco e gerando SEGREDO_CURSOR aleatório. Não imprime os segredos e não sobrescreve arquivo existente. Ambos os arquivos ficam fora do Git e da imagem Docker. Não copiar .env.api para README, logs ou exemplos públicos.

Para outro arquivo, usar servir --configuracao-api CAMINHO. Variáveis de ambiente prevalecem sobre o arquivo. A API exige segredo de cursor com pelo menos 32 bytes; sem isso, o servidor não inicia. URL_BANCO_API pode faltar para diagnosticar o processo: /health funciona e /ready informa 503. Iniciar a API não inicia Docker nem executa migrações automaticamente.

## Rotas

| GET | Conteúdo |
|---|---|
| /health | Processo vivo, sem consulta ao banco |
| /ready | Banco acessível e revisão/visões compatíveis; não exige fatos ou gold publicada |
| /api/v1/series | Catálogo das três séries e cobertura disponível no core |
| /api/v1/series/{codigo} | Unidade, periodicidade, cobertura e regra da série |
| /api/v1/series/{codigo}/observacoes | Observações core por data crescente |
| /api/v1/series/{codigo}/agregados | Gold mensal/anual; granularidade=mes ou ano |
| /api/v1/indicadores/ipca-12m | Gold de composição de 12 meses e incompletude |
| /api/v1/pipeline/execucoes | Histórico sanitizado, fonte/situação, mais recente primeiro |
| /api/v1/pipeline/frescor | Última consulta registrada, referência, publicação, cobertura e heurísticas |

As rotas de dados estão em /api/v1; probes na raiz. IBGE, /metrics e rotas de escrita não são registradas nesta etapa. OpenAPI contém schemas tipados e exemplos de sucesso, vazio e erro; os exemplos foram validados contra os modelos de resposta.

## Filtros e representação

Observações, agregados e IPCA 12m aceitam de/ate inclusivos, limite e cursor. Datas devem usar exatamente YYYY-MM-DD; timestamps e segundos Unix não são convertidos implicitamente. O recorte público começa em 2020-01-01; datas futuras, início após fim ou mais de 3660 dias inclusivos retornam 422. Sem filtros, usa 2020-01-01 até hoje em America/Sao_Paulo.

limite padrão 100, mínimo 1, máximo 1000. O catálogo pequeno é completo, sem paginação. Execuções aceitam fonte=bcb e situacao entre EM_EXECUCAO, SUCESSO, PARCIAL, FALHA e IGNORADA. Filtros desconhecidos nas listas filtradas são rejeitados.

Decimais são strings com seis casas, ROUND_HALF_EVEN, arredondados somente na resposta. Datas são ISO; timestamps operacionais usam UTC com Z. Série inexistente retorna 404; série existente sem dados retorna 200 com lista vazia e cobertura. Dados técnicos IPCA de 2019 não são expostos como observações públicas, mas podem participar do cálculo12m da gold.

Exemplo de consulta:

```text
GET /api/v1/series/432/observacoes?de=2020-01-02&ate=2020-01-06&limite=2
```

A resposta tem data, pagina e meta. pagina.proximo_cursor deve ser reutilizado como valor opaco, mantendo os filtros e o limite. meta.de/ate mostram as datas resolvidas: ao navegar perto da mudança de dia, preservá-las explicitamente evita mudar o filtro implícito de hoje.

meta.versao_dados identifica a geração da camada. versao_core, versao_gold e data_publicacao permitem distinguir fatos novos de gold anterior. desatualizado refere-se ao sincronismo/atualidade da publicação gold; não substitui o indicador de idade da observação no endpoint de frescor.

Cobertura core conta observações públicas e datas de referência. Cobertura gold conta períodos publicados; unidade_contagem=periodos esclarece o significado do campo observacoes nessa cobertura. Enquanto gold está pendente, a cobertura informada é da gold antiga, sem misturá-la com a cobertura nova do core.

Gold ainda não publicada retorna 200 vazio com GOLD_NAO_PUBLICADA. Gold anterior já existente pode ser servida com desatualizado=true. PRONTA significa sincronismo com os fatos disponíveis, não cobertura histórica completa. completo diário continua NULL por falta de calendário homologado; IPCA incompleto mantém valorNULL e motivo.

## Paginação, consistência e concorrência

Não há OFFSET: as listas buscam limite + 1 e usam a última chave como fronteira. Observações/agregados usam data/período; execuções usam iniciado_em e execucao_id em ordem decrescente. O primeiro cursor de histórico congela um teto de iniciado_em. Status das execuções existentes podem mudar entre páginas; não se promete snapshot permanente do histórico.

Cursores têm formato versionado, rota/série, resumo dos filtros, geração e chaves, assinados com HMAC-SHA256. Tamanho máximo 2048 caracteres, tipos e assinatura são validados antes da consulta das linhas. Não há criptografia: Base64 não fornece confidencialidade. Expiram após 24 h; alteração da geração retorna 409 CURSOR_EXPIRADO. Outra rota/série/filtro, adulteração ou formato inválido retornam 422. Rotacionar SEGREDO_CURSOR invalida os cursores anteriores.

Geração e linhas são lidas sob a mesma transação READ ONLY REPEATABLE READ. Nas rotas gold, uma trava compartilhada de sessão é adquirida antes de abrir o snapshot, coordenando com a trava exclusiva da carga/publicação. Isso impede misturar geração antiga com um heap materializado atualizado. A liberação é explícita ao fim da leitura; falha invalida a conexão antes de devolvê-la ao pool. A distinção entre travas de sessão e transação segue o [contrato PostgreSQL 16](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS).

A espera pela trava gold é limitada a 2 s; publicação ocupada pode resultar503 PUBLICACAO_OCUPADA, sem afetar /health ou declarar o banco permanentemente indisponível. Consultas têm timeout SQL de 5 s e espera por locks relacionais de 2 s. Não há transação mantida entre páginas. O desenho de isolamento usa os [mecanismos SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/core/connections.html#setting-transaction-isolation-levels-including-dbapi-autocommit).

## Cache, limites e erros

Dados públicos incluem ETag do JSON e Cache-Control: public, max-age=0, must-revalidate. If-None-Match correspondente retorna 304 depois de conferir o banco, a geração e a representação. Páginas que reemitem um próximo cursor podem ter ETag diferente por causa do instante de emissão do token. Operação, probes e erros usam no-store. Redis ainda não é utilizado.

O limite padrão é 100 requisições/minuto/endereço de conexão, em um processo. LIMITE_REQUISICOES_MINUTO permite ajuste local. Uvicorn é iniciado com proxy_headers=False: X-Forwarded-For não altera a identidade do cliente. /health e /ready não consomem o limite. Não é um limite global entre réplicas; uma publicação futura atrás de gateway precisará de configuração própria, sem confiar indiscriminadamente em headers enviados pelo cliente.

Todas as respostas têm X-Request-ID gerado pelo servidor. Erros usam envelope erro com codigo, mensagem, requisicao_id e detalhes. Não retornam stack trace, SQL, credenciais, parâmetros internos de execução ou registros de quarentena. Logs da aplicação incluem ID, rota-modelo, status e duração; o access log bruto do Uvicorn está desativado para não registrar queries/cursor por padrão. O tratamento usa os [handlers FastAPI documentados](https://fastapi.tiangolo.com/tutorial/handling-errors/).

| HTTP | Situação |
|---|---|
| 404 | Série/recurso inexistente |
| 405 | Método não registrado |
| 409 | Cursor expirado por tempo ou geração |
| 422 | Parâmetro, período ou cursor inválido |
| 429 | Limite local excedido, com Retry-After |
| 503 | Banco/schema indisponível ou espera por publicação excedida |
| 500 | Erro inesperado sanitizado |

## Permissões e operação

A revisão 0005 cria ops.v_publicacao_api, v_esquema_api, v_execucoes_api e v_frescor_api. Elas expõem somente campos selecionados; api_leitura não recebe acesso geral às tabelas ops. A revisão 0006 remove escrita herdada de processamento nessas visões, evitando inclusive alteração indireta de alembic_version. O processamento continua escrevendo somente em suas tabelas autorizadas.

O servidor usa a factory criar_aplicacao, e o [lifespan FastAPI](https://fastapi.tiangolo.com/advanced/events/) libera o pool ao encerrar. Não há conta externa ou publicação remota criada nesta entrega. Para encerrar uma instância iniciada no terminal, usar Ctrl+C.

Verificação manual repetível:

```powershell
uv run --frozen python scripts/verificar_api_local.py
```

Esse script inicia uma instância própria em porta livre de 127.0.0.1, verifica endpoints, paginação no recorte 02..06/01/2020, ETag, limite com headers forjados e preservação do banco; depois encerra somente o processo que criou. Não exige que o servidor padrão 8000 esteja ativo e não altera fatos, lotes ou estado de publicação. Logs ficam em .cache e o relatório em dados/descoberta/sondagem_api_bcb.json, ambos fora do Git.

## Evidências — 18/11/2026

- 276 testes passaram; cobertura global 96,59%. Cursor 97%, repositório 98%, aplicação 98%; filtros, modelos e limitador 100%. Os três módulos principais da API têm meta individual 95% no CI.
- Testes com api_leitura real, snapshots concorrentes, gold pendente, cursors inválidos/expirados, ETag 304, rate limit e schemas/exemplos OpenAPI válidos. A suíte não acessa APIs externas.
- Regressões reproduzidas antes das correções: confiança implícita em X-Forwarded-For; geração antiga com linhas de MV nova; cobertura gold confundida com core; escrita herdada em views; coerção de timestamps Unix em datas públicas.
- Backup pré 0005: backups/etl_antes_api_20261118_172409.dump, 42.602 bytes; pré 0006: backups/etl_antes_api_privilegios_20261118_173202.dump, 46.104 bytes. Ambos com catálogo legível; não equivalem a ensaio completo de restauração.
- Imagem construída; revisões aplicadas e alembic check sem diferenças. HTTP real em 12 rotas, paginação sem duplicatas, ETag 304 e bloqueio de spoofing no limite; cinco fatos, metadados, lotes, preparações, auditoria e gerações preservados. Servidor temporário encerrado.

Histórico real completo, calendário oficial homologado, replay isolado, desempenho medido, IBGE, Redis, métricas, agendamento e hospedagem ainda estão pendentes. Próxima validação do M1: carga histórica real e ensaio ponta a ponta, sem confundir implementação funcional com cobertura completa da fonte.

Atualização posterior: a API foi verificada com todas as 4.323 observações públicas e os 351 agregados reais; banco preservado em core22/gold22 PRONTA. O histórico acima descreve a entrega inicial da API; a carga real está documentada no guia de histórico.

## Recuperação e calendário — atualização de 18/11/2026

A API foi verificada também sobre os bancos isolados de restauração e replay: cada um retornou as 4323 observações públicas e 351 agregados esperados, sem alterar o banco. O script manual aceita --banco-ensaio com nome exclusivo retornado pelo ensaio; a configuração normal .env.api não foi modificada. Ver [recuperação local](recuperacao-local-m1.md).

O [calendário oficial IPCA de 2026](calendario-ipca.md) foi conferido manualmente: outubro é a referência esperada em 18/11. O endpoint de frescor ainda usa HEURISTICA_45_DIAS e pode retornar defasado=true nesse caso. Não foi introduzido um novo contrato silenciosamente. No replay não são inventadas consultas externas, então ultima_consulta pode ficar ausente. A avaliação automática por calendário e a cobertura histórica completa continuam pendentes.

## Frescor por calendário — implementação posterior de 18/11/2026

O IPCA usa agora o calendário oficial arquivado enquanto estiver vigente: CALENDARIO_IBGE, um dia completo de tolerância após divulgação e validade de 30 dias da consulta (inclusive). Em 18/11/2026, outubro retorna defasado=false. Sem calendário utilizável, a heurística de 45 dias permanece e motivo explica a degradação. Séries diárias continuam com quatro dias.

Campos aditivos: motivo, referencia_esperada, data_limite e versao_calendario. calendario_homologado=true significa calendário aplicado ao frescor atual, sem alterar cobertura histórica: cobertura.completa=null e motivo CALENDARIO_NAO_HOMOLOGADO permanecem. Ausência/referência inválida retorna defasado=null. A API não consulta IBGE para responder. Ver [política, vigência e atualização](calendario-ipca.md).

A sondagem local completa passou após a mudança, com todos os dados e auditoria preservados; esquema continua 0006. A implementação substitui a limitação heurística descrita nas atualizações históricas acima enquanto o snapshot estiver vigente.

## Desempenho medido — 18/11/2026

Ensaio local com 30s de aquecimento, 60s de medição e dez clientes: 6061 pedidos, p95 149,02 ms, aproximadamente 100,93 pedidos/s, zero 429/5xx/transporte/validação. Workload misto de páginas Selic início/meio/fim e gold mensal, limite cem itens, sem cache de aplicação e sem 304. SQL keyset/OFFSET e planos também medidos. Dados e auditoria preservados. Não representa todas as rotas, saturação, ETL concorrente ou SLA de hospedagem. Ver [protocolo, ambiente e resultados](desempenho/2026-11-18-m1-local.md).

## Orquestração local — 19/11/2026

Prefect executa coleta/carga/publicação fora da API, com papel e banco próprios para seus metadados. A API continua somente leitura. Após atualização real pela agenda/worker, foram conferidas 4324 observações públicas e 351 agregados; core total 4335, core 23/gold 23 PRONTA, esquema 0006. A observação adicional é Selic de 19/11. O pai pipeline_bcb é auditado privadamente, com vínculos dos filhos; fonte pode aparecer null para esse modo novo na view sanitizada atual. Nenhum parâmetro privado foi exposto. Ver [agendas e operação](orquestracao-local.md).
