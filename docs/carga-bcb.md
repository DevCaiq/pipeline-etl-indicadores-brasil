# Transformação e carga BCB

A carga recebe um manifesto bronze existente, valida os bytes novamente e promove somente um conjunto integralmente aprovado. Não consulta o BCB. A transformação preserva Decimal, ordena as datas e não preenche lacunas, arredonda medidas ou cria cotações de feriados. As observações de apoio IPCA de 2019 permanecem identificáveis pela data; consultas públicas futuras deverão respeitar o recorte desde 2020.

## Usar no ambiente local

Com Docker Desktop aberto e PostgreSQL ativo:

```powershell
docker compose --env-file .env.banco up -d --wait banco
docker compose --env-file .env.banco run --build --rm migracoes
uv run --frozen pipeline-etl carregar bcb --manifesto dados/bronze/bcb/432/2026-11-18/f68045ff-e6c2-4622-9678-c98dc1df4287/manifest.json --credenciais-locais .env.banco
```

O arquivo .env.banco é lido somente por opção explícita, usando o papel processamento. Também é possível configurar URL_BANCO_PROCESSAMENTO, sem combinar as duas origens. O comando não usa privilégios administrativos. --ajuda e -h apresentam a ajuda.

A saída JSON inclui execucao_id, situacao, inseridas, alteradas, inalteradas, motivo e avisos. Código 0 representa SUCESSO; 1 representa falha ou tentativa adiada; 2 indica credenciais inválidas/ausentes. Cada tentativa gera histórico de validação e carga distinto; parametros.validacao_id relaciona as duas execuções. Os contadores de carga ficam no resumo/parâmetros; os contadores de qualidade pertencem à validação.

## Fluxo e idempotência

1. Conferir manifesto, identidade, checksums, janelas e contrato. PARCIAL ou FALHA impede toda promoção.
2. Persistir ops.preparacao_bcb em grupos de até 1.000 linhas. A preparação é durável, ligada à execução, e permite investigar falhas sem modificar o core.
3. Reservar uma conexão durante a transação de promoção e adquirir o advisory lock transacional BCB, chave 2026111801. Esperar no máximo 30 segundos pela aquisição; lock ocupado resulta em IGNORADA/LOCK_OCUPADO, sem escrita no core.
4. Comparar por chave natural (codigo_sgs, data). Inserir novos valores ou revisar valores diferentes. ON CONFLICT usa IS DISTINCT FROM: valor igual não altera lote_id, alterado_em ou origem_coletada_em.
5. Confirmar fatos, ops.lote, checkpoint, geração do domínio e execução na mesma transação. Alterações de negócio incrementam versao_core e deixam publicação PENDENTE; versao_gold permanece anterior. Nenhuma alteração de negócio implica nenhuma nova geração.

Mesmo com payload igual, novas tentativas acrescentam histórico operacional e preparação. Esse histórico é esperado; idempotência não significa ausência de auditoria. O instante de coleta mais recente confirmado também é consultado no histórico: uma coleta antiga divergente não pode revisar o fato, mesmo quando uma coleta recente igual preservou os metadados do fato. Origem desconhecida ou instante igual com valor divergente também bloqueia a revisão.

Observações que desaparecem da janela geram OBSERVACOES_AUSENTES_NA_JANELA. Nenhum fato é excluído automaticamente. Os consumidores atuais devem usar a situação operacional ao avaliar esse aviso; homologação de calendário/cobertura oficial continua pendente.

## Cobertura e checkpoint

ops.watermark_bcb separa fim_coberto de ultima_observacao. A cobertura é calculada pela união das janelas de lotes confirmados, sem saltar lacunas, começando em 01/01/2020 para séries diárias e 01/02/2019 para apoio IPCA. A última observação considera somente fatos até o fim dessa cobertura contígua. Janelas fora de ordem podem inserir fatos, mas não avançam o checkpoint além de um intervalo ainda não confirmado.

Uma amostra que começa em 02/01/2020 não cria checkpoint inicial, mesmo com observações válidas. Isso não determina se 01/01 era feriado: significa apenas que não existe evidência de uma consulta confirmada cobrindo esse dia. O checkpoint representa janelas consultadas e aprovadas, não comprovação de todas as datas esperadas no calendário oficial.

O comando automático de coleta incremental, seus recuos de 30 dias/24 meses e a reconciliação histórica serão a próxima entrega. A existência da tabela de checkpoint não significa que essa coleta já foi implementada.

## Falhas e recuperação

Falha durante a promoção reverte fatos, lote, checkpoint, geração e conclusão. O início auditado e a preparação previamente confirmada permanecem; a execução é marcada FALHA em outra transação. Se o banco continuar indisponível, essa marcação pode não ser persistida: conferir execuções EM_EXECUCAO após restabelecer o banco, sem presumir sucesso.

Após corrigir banco/lock/entrada, repetir carregar com o manifesto preservado cria nova tentativa. A preparação antiga não é promovida automaticamente. Bronze antigo divergente requer análise; não há opção de forçar substituição silenciosa. Replay para reconstrução isolada e restauração completa continuam pendentes.

O lock protege chamadas que usam esse contrato; não impede SQL administrativo que ignore o mecanismo. A publicação futura deverá usar a mesma chave e respeitar o estado PENDENTE. Não há mart publicado ou API nesta entrega.

## Migração e evidências — 18/11/2026

A revisão 0003 acrescenta ops.preparacao_bcb (índice por série/data), ops.watermark_bcb, ops.publicacao e core.fato_serie.origem_coletada_em. Revisões 0001 e 0002 foram preservadas. O papel processamento herda os privilégios operacionais; api_leitura não recebe acesso à preparação. Fatos legados podem ter origem nula: revisão divergente é bloqueada até reconciliação explícita.

Backup anterior à migração: backups/etl_antes_carga_20261118_052614.dump, 23.863 bytes, com catálogo pg_restore --list legível. Não foi ensaiada uma restauração completa. A imagem Docker foi construída e aplicada; alembic current retornou 0003 head e alembic check não encontrou diferenças.

O manifesto oficial da série 432, de 02/01/2020 a 06/01/2020, foi carregado duas vezes, sem HTTP:

| Tentativa | Execução | Inseridas | Alteradas | Inalteradas |
|---|---|---:|---:|---:|
| Primeira | 15741700-6345-43f0-a10c-f52eda78424a | 5 | 0 | 0 |
| Repetição | 0ad6b084-d25c-43e7-9e44-245e11d6f869 | 0 | 0 | 5 |

Consultas posteriores compararam exatamente valores, lote de origem e instantes: cinco fatos preservados, versao_core=1, versao_gold=0, PENDENTE e nenhum checkpoint criado para a janela inicial incompleta. Relatório operacional local em dados/descoberta/sondagem_carga_bcb.json, ignorado pelo Git.

184 testes passaram, incluindo migração/reversão em etl_testes, transações, permissões, revisões antigas e lacunas. Cobertura global 95,32%; carga 96%, transformação 100%, validador 99% e contrato 100%. Ruff, formatação, mypy, bandit, auditoria de dependências e build do pacote passaram. A revisão estática independente não apontou falhas importantes/críticas.

Atualização posterior: coleta incremental/reconciliação por CLI foram implementadas; as evidências acima descrevem a entrega da carga. Ver [guia incremental](incremental-bcb.md) para comandos, limites e estado atual.
