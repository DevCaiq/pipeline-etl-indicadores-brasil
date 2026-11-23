# Operação e recuperação local M1/M2

Executar no PowerShell em `D:\pipeline-etl`. Este runbook consolida os comandos
locais; não publica o projeto nem substitui a configuração de uma nova máquina.

## Retomada

1. Abrir Docker Desktop e aguardar o mecanismo Linux. Conferir `docker info`.
2. Conferir PostgreSQL e serviços pelo Docker Desktop ou Compose. Não apagar volumes.
3. Conferir API em http://127.0.0.1:8001/ready, MinIO em
   http://127.0.0.1:9000/minio/health/ready e Prefect em http://127.0.0.1:4200.
4. Iniciar servidor e worker existentes, nessa ordem, conforme
   [orquestração local](orquestracao-local.md). Não criar um segundo worker.

```powershell
Start-ScheduledTask -TaskName PipelineETL-Prefect-servidor
Start-ScheduledTask -TaskName PipelineETL-Prefect-worker
Get-ScheduledTask -TaskName PipelineETL-Prefect-*
```

O worker consolida agendas antigas e solicita atualização de retomada. Máquina,
sessão do usuário e Docker ativos são requisitos; não funciona com PC desligado.
Segredos permanecem nos arquivos privados `.env.*`, nunca em comandos públicos.

## Carga confirmada, publicação falhou

Conferir o pai e os filhos no Prefect/logs locais, gerações por domínio e motivo
sanitizado. Corrigir a causa e repetir somente a publicação:

```powershell
uv run --frozen python scripts/executar_pipeline_local.py --modo publicacao
uv run --frozen python scripts/executar_ibge_local.py --modo publicacao --configuracao-s3 .env.armazenamento
```

Não recarregar fatos confirmados nem alterar `versao_gold` manualmente. Refreshes,
referência de publicação e troca de geração são transacionais. Ensaio de falha
entre materializadas e recuperação: [recuperação M1](recuperacao-local-m1.md).

## Migração e referência durável

A revisão0010 preserva a data de referência arquivada das materializadas BCB.
O publicador avança essa referência antes dos refreshes na mesma transação.
Assim, uma restauração em outro dia recompõe o snapshot do backup, sem trocar
metadados nem apresentar novos dados sob uma geração antiga.

Antes de migração relevante, criar backup privado fora do volume do banco e
conferir a recuperação em destino isolado. Não aplicar migrações enquanto houver
carga/publicação ativa. A revisão0010 usa a mesma trava BCB e recusa core pendente;
nesse caso, recuperar a publicação e repetir a migração, sem forçar versões.
Downgrade não substitui restauração de backup e reintroduz a semântica anterior.
Não usar revisão antiga para afirmar que o problema entre datas está corrigido.

## Falha da coleta ou do armazenamento

Não avançar checkpoints nem fabricar valores. Bronze confirmado e manifestos
permanecem para diagnóstico/replay. No S3, conferir serviço e configuração privada;
erro do backend escolhido não autoriza fallback silencioso para arquivos.
[Armazenamento e limites](armazenamento-s3-local.md).

## Cache e monitoramento

Redis indisponível deve acionar fallback ao PostgreSQL. Conferir o estado do
circuito e métricas de erro; não reiniciar banco ou apagar dados para limpar cache.
Chaves incorporam domínio/geração; alteração de gold não reutiliza outra geração.

Grafana: http://127.0.0.1:3000; Prometheus: http://127.0.0.1:9090.
Frescor desconhecido é `-1`, não sucesso. Distinguir última consulta, ano disponível,
ano carregado e publicação. Cobertura incompleta não é total nacional completo.
[Políticas e métricas](monitoramento-completo-m2.md).

## Restore e demonstração

```powershell
uv run --frozen python scripts/ensaiar_restauracao_m2.py
uv run --frozen python scripts/demonstrar_m2_local.py
```

Executar fora das agendas e sem migrações simultâneas. Os comandos criam bancos
exclusivos e preservam origem, dumps e clones para inspeção, inclusive em falhas.
Demonstração restaura, confere snapshot e API, faz replay idempotente e republica
somente no clone. A nova publicação pode avançar data/flags temporais da gold;
seu conteúdo completo é novamente conferido contra a definição SQL e pela API.
O core da cópia e a origem permanecem inalterados.

Nunca usar `docker compose down -v` como recuperação. Backups e bronze no mesmo
computador não comprovam recuperação de desastre nem backup externo. Instalação
inicial/imagens e histórico prévio são pré-requisitos da demonstração de 15min.
