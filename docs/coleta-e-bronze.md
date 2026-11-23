# Coleta BCB e camada bronze

Etapa verificada em 18/11/2026. Cliente HTTP síncrono, armazenamento filesystem imutável e comando de coleta por período. Código próprio em português-BR.

## Executar

Na raiz do projeto:

    uv sync --frozen
    uv run --frozen pipeline-etl coletar bcb --serie 432 --inicio 2020-01-02 --fim 2020-01-06

Para selecionar mais de uma série, repetir --serie. Sem esse argumento, usar SERIES_BCB da configuração (432,433,1 por padrão). CAMINHO_BRONZE controla a raiz; o padrão é dados/bronze, relativo ao diretório de execução.

    uv run --frozen pipeline-etl coletar bcb --serie 1 --serie 432 --inicio 2020-01-01 --fim 2020-12-31
    uv run --frozen pipeline-etl coletar bcb --ajuda

O período é obrigatório, começa em 2020-01-01 ou depois e termina até hoje no fuso America/Sao_Paulo. Janelas são inclusivas, por ano civil, sem repetir limites. A coleta histórica do IPCA que começa em 2020-01-01 inclui fevereiro–dezembro/2019 como apoio técnico: o manifesto diferencia inicio solicitado de inicio_coleta efetivo.

O modo disponível é carga-historica (padrão). Incremental com watermark, backfill de banco e replay econômico ainda não estão implementados. A execução atual é no host; o serviço Docker migracoes continua destinado ao Alembic, sem volume bronze de worker.

## Significado da saída

- JSON em stdout contém situação e lista de manifestos por série.
- Logs JSON em stderr incluem fonte, série, execução, tentativa e informações de falhas, sem corpo da resposta.
- Código 0: todas as séries solicitadas tiveram seus corpos e manifestos preservados.
- Código 1: alguma coleta ficou incompleta; verificar motivo/manifesto e eventual proxima_tentativa_em.
- Código 2: erro de argumentos/configuração/período.

COLETADA significa transporte e persistência concluídos, não contrato de dados aprovado. Resposta HTTP200 vazia, HTML ou JSON inválido também é evidência bronze; a validação/quarentena é uma etapa separada, disponível com --validar; ver [guia de qualidade](validacao-e-quarentena.md). Nenhuma observação é inserida em core e nenhum watermark é avançado. Esta etapa registra execução no manifesto/logs; controle SQL detalhado está disponível na validação opcional, sem marcar a Fase3 inteira como encerrada.

Séries independentes continuam após uma falha. Um Retry-After adiado continua bloqueando novas consultas ao BCB no mesmo cliente, inclusive para outra série; não há repetição automática de toda a coleta.

## Política HTTP

- Origem fixa api.bcb.gov.br; sem URL arbitrária nem seguimento de redirecionamentos.
- Até 5 tentativas para falha de rede/timeout/protocolo remoto e HTTP429/500/502/503/504. Outros status não são retentados.
- Backoff exponencial com jitter de 1 a 30s. Retry-After inteiro ou data HTTP determina espera mínima, inclusive quando maior que 30s.
- Espera que não cabe no orçamento gera adiamento; não reduzir o prazo do servidor. Esperas fora do calendário representável permanecem bloqueadas no cliente e recebem data máxima como indicação operacional, não agendamento automático.
- Intervalo mínimo de 1s entre inícios; lock por instância de cliente. Limites globais entre processos entram na orquestração futura.
- Conexão/pool até10s, leitura/escrita até30s, limitados pelo orçamento restante quando a tentativa começa.
- Orçamento180s verificado antes de iniciar operações, entre blocos e ao concluir. HTTPX mede timeout por fase/inatividade, não cancelamento rígido global: uma operação já bloqueada pode terminar depois do prazo; nesse caso a resposta é recusada e não aceita como artefato.
- Corpo limitado a10MiB antes da gravação. Leitura iter_raw mantém bytes codificados originais, sem descompressão. O cliente solicita identity; eventual Content-Encoding do servidor fica nos metadados.

Referências oficiais consultadas: [timeouts HTTPX](https://www.python-httpx.org/advanced/timeouts/), [streaming HTTPX](https://www.python-httpx.org/quickstart/#streaming-responses) e [Tenacity](https://tenacity.readthedocs.io/en/latest/).

## Layout e integridade

    dados/bronze/bcb/{codigo}/{data_utc_execucao}/{execucao_id}/
      {artefato_id}.body
      {artefato_id}.meta.json
      manifest.json

Corpo salvo antes de qualquer parse. Metadados incluem URL oficial, parâmetros, HTTP status, coleta UTC, tamanho, SHA-256, Content-Type/Encoding e descompressao_automatica=false. O arquivo .body não é necessariamente texto JSON: consultar codificacao_conteudo antes de interpretar.

Publicação: escrever arquivo temporário no mesmo diretório, flush/fsync, criar hard link exclusivo no destino e remover temporário. Diferente de replace, isso não sobrescreve arquivo existente. Windows NTFS e filesystem Linux com suporte a hard links foram considerados; storage sem esse recurso falha de forma explícita, sem fallback que substitua arquivos.

Manifesto é publicado por último, após conferir referências canônicas, presença, tamanho e SHA-256. Referência recebida deve corresponder integralmente aos metadados verificados. Leitura recusa caminhos fora da raiz e metadados incompatíveis. Checksums detectam divergência dos corpos; não são assinatura criptográfica de autoria dos metadados.

Falha de rede após algumas janelas gera manifesto INCOMPLETA com artefatos já concluídos. Falha de persistência impede manifesto COLETADA. Interrupção abrupta pode deixar corpo/metadados órfãos sem manifesto; esses diretórios não representam execução concluída. Não prometer transação conjunta com SQL ou durabilidade absoluta contra falha física do dispositivo.

Cada execução cria identificadores novos, mesmo com mesmo payload. Não há sobrescrita nem deduplicação destrutiva no bronze; idempotência de dados de negócio será garantida na carga futura.

## Leitura verificada

ArmazenamentoBronze.ler_corpo(caminho_metadados) devolve bytes somente após verificar referência, tamanho e checksum. Não acessa a rede e não interpreta medidas. Descompressão, contratos e reconstrução do core ficam para o próximo estágio.

## Evidências

- 100 testes passaram, incluindo PostgreSQL local; cobertura global95,68%, configuração100% e cliente HTTP98%.
- Casos offline: sucesso, 429/5xx/rede/timeout, cinco tentativas, Retry-After/data/inválido/extremo, cooldown entre séries, orçamento, gzip original, limite, redirects, janelas/apoio IPCA, disco indisponível, corrupção e referências falsas de manifesto.
- Sondagem oficial Meta Selic432, 02/01/2020–06/01/2020: HTTP200, cinco observações,186 bytes; SHA-256 3f8a8a942d1ec01000faadd251aacde0badedd0b8c0eb8a29601b1365eecd639.
- Execução local f68045ff-e6c2-4622-9678-c98dc1df4287; relatório em dados/descoberta/sondagem_coleta_bronze.json, ignorado pelo Git.
- Revisão independente apontou divergência entre referência publicada e verificada; três regressões falharam antes e passaram após correção.

Testes usam MockTransport e filesystem temporário; não consultam APIs externas. Sondagem real foi manual e separada da suíte. Documentação de licenças/calendários e demais pendências permanece em docs/fontes.md.

Build final verificado: wheel instalado fora das fontes executou coleta simulada e preservou bronze temporário; distribuição sem dados/segredos. Imagem não root reconstruída com novas dependências e ajuda da CLI de coleta executada sem novas consultas externas.
