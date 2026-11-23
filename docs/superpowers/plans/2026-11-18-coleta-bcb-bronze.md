# Plano de execução — Cliente BCB e bronze

Objetivo: coletar respostas SGS com HTTP resiliente e preservar bytes, metadados e manifesto imutáveis no filesystem. Sem validar medidas nem carregar core nesta etapa.
Especificação: plano-pipeline-etl-api.md, seção 6 e Fase 3; AGENTS.md; autorização para próximo passo.
Arquitetura: ClienteBCB usa httpx/tenacity; ArmazenamentoBronze grava arquivos exclusivos/atômicos; coletar_serie divide anos e publica manifesto somente após os artefatos. CLI coletar bcb integra essas partes, independente de PostgreSQL.

## Restrições

Português-BR em código próprio. Até 5 tentativas, somente rede/timeout e HTTP429/500/502/503/504; jitter 1–30s; Retry-After segundos/data; orçamento180s para iniciar novas operações/esperas. Intervalo mínimo1s e lock por cliente. HTTPX impõe timeout por fase/inatividade, não cancelamento rígido global; verificar orçamento também entre blocos e ao concluir. Limite de corpo10MiB. Origem fixa e sem redirecionamento.

Preservar bytes de iter_raw, incluindo eventual codificação HTTP; descompressao_automatica=false e Content-Encoding registrado. Não presumir que corpo HTTP200 é JSON válido. Contratos, quarentena e registros SQL serão implementados na próxima etapa, com novas migrações; não marcar Fase3 inteira concluída.

## Tarefas

- [x] Testes de cliente: sucesso, falhas transitórias, não retry404, 5 tentativas, Retry-After segundos/data, adiamento, orçamento, rate limit, payload grande e redirects.
- [x] Implementar ClienteBCB com relógio/espera injetáveis para testes offline.
- [x] Testes bronze: bytes e hash, gzip original, publicação sem sobrescrita, falha e checksum corrompido.
- [x] Implementar escrita temporária + publicação exclusiva, metadados e leitura verificada.
- [x] Testar janelas anuais/ano bissexto, manifesto parcial e suporte IPCA2019; implementar fluxo.
- [x] Integrar CLI com testes de parsing/erro e execução offline com MockTransport.
- [x] Verificar suíte completa, cobertura, tipos, lint, auditoria e uma sondagem oficial pequena.
- [x] Atualizar README, fontes, instruções e CI conforme o escopo.

## Arquivos

src/pipeline_etl/processamento/{erros,tipos,coleta}.py; clientes/bcb.py; armazenamento/arquivos.py; comandos.py; testes/unidade/test_{cliente_bcb,bronze,coleta}.py; docs/coleta-e-bronze.md.

## Revisão focada

Falhas não repetíveis; JSON inválido salvo sem parse; tempo de Retry-After maior que orçamento; gzip mantido sem alteração; pasta fora da raiz; manifesto concluído não publicado com artefato ausente; execução interrompida não apresentada como carga econômica bem-sucedida.

## Evidências

TDD por componente: módulos ausentes inicialmente; depois testes HTTP/bronze/fluxo/CLI passaram. Regressão Retry-After extremo e cooldown entre séries reproduzida antes de corrigir. Revisão independente encontrou manifesto com referência/tamanho divergente; três testes falharam e passaram após conferir referência canônica e bytes reais. Leitura passou a rejeitar metadados inválidos com diagnóstico controlado.

Suíte completa100/100, cobertura global95,68%, configuração100%, clienteHTTP98%. Sondagem oficial única:432, cinco observações,186 bytes, hash3f8a8a942d1ec01000faadd251aacde0badedd0b8c0eb8a29601b1365eecd639. Nenhuma carga no core ou alteração de credenciais/migrações. CI existente incorpora os novos testes automaticamente; nenhuma execução remota foi feita.

Decisões: transporte bruto mantém bytes iter_raw; não validar JSON neste estágio; registro SQL junto à próxima fase; locks/rate limit por cliente, globais na orquestração futura. Orçamento verificado nos pontos de controle, sem alegar cancelamento síncrono rígido que HTTPX não fornece. Publicação por hard link exclusivo evita sobrescrita permitida por replace em POSIX.

Fechamento: wheel/sdist e imagem atualizados; smoke do wheel com MockTransport fora das fontes e ajuda na imagem real passaram. Documentos/links, Git ignore, Ruff, mypy e bandit verificados. Auditoria não apontou vulnerabilidades conhecidas.
