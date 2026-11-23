# Agendamento IBGE local — 19/11/2026

Atualização 23/11/2026: servidor e worker retomados, fluxos reais BCB/IBGE concluídos com sucesso. Ver [aceite técnico](aceite-tecnico-m2.md). As datas de próximas ocorrências da tabela abaixo são o registro histórico de19/11; consultar o painel Prefect para a agenda atual.

Três deployments IBGE registrados junto aos três BCB no Prefect local.
Servidor e worker existentes estão `Running` no Agendador do Windows.
Painel: http://127.0.0.1:4200. Nenhuma conta de nuvem ou segundo worker criado.

| Deployment | Agenda America/Sao_Paulo | Cron | Próxima ocorrência gerada |
|---|---|---|---|
| pipeline-ibge-local/ibge-localidades | Domingo, 18h | `0 18 * * 0` | 22/11/2026, 18h |
| pipeline-ibge-local/ibge-incremental | Dia 5, 20h | `0 20 5 * *` | 05/12/2026, 20h |
| pipeline-ibge-local/ibge-reconciliacao | Dia 1 de janeiro/abril/julho/outubro, 21h | `0 21 1 1,4,7,10 *` | 01/01/2027, 21h |

Cada deployment tem uma agenda ativa e limite um. O pool `pipeline-etl-local`
tem limite global um e o worker usa `--limit 1`. Horários coincidentes com BCB
entram na mesma fila; o cron define elegibilidade, não início garantido.
As próximas ocorrências foram lidas das rodadas automáticas geradas pelo servidor.
O aceite inclui disparo manual real pelo deployment; não se alega que essas
ocorrências futuras de calendário já aconteceram.

## Modos e armazenamento

- Incremental mensal descobre períodos homologados, busca anos ainda ausentes
  e revisa o último disponível. Na primeira carga, busca todos os disponíveis.
- Localidades semanal coleta o pacote completo, incluindo população dos anos
  disponíveis, para validar/promover o snapshot territorial junto dos fatos.
  Essa escolha preserva o contrato transacional atual e a cobertura populacional.
- Reconciliação trimestral revê todos os anos disponíveis desde 2020.
- Publicação permite recuperação manual sem consulta IBGE; não acrescenta agenda.

Deployments usam MinIO (`usar_s3=true`), configuração privada `.env.armazenamento`.
Parâmetros Prefect não contêm senhas. Pai SQL registra tipo/endpoint/bucket/prefixo
sem credenciais e cada manifesto confirmado. Filhos recebem `pai_pipeline_id`.
Arquivos permanecem opção da CLI; o verificador S3 escolhe o último pacote
confirmado em arquivos para conservar a comparação entre adapters.

```powershell
uv run --frozen python scripts/executar_ibge_local.py --modo incremental --configuracao-s3 .env.armazenamento
uv run --frozen python scripts/executar_ibge_local.py --modo publicacao --configuracao-s3 .env.armazenamento
```

O adaptador chama a CLI no ambiente principal. Prefect continua isolado em
`orquestracao/.venv`, sem dependência na aplicação. Não há retry de flow;
tentativas HTTP ficam exclusivamente no cliente IBGE. Subprocesso limitado a
uma hora. Código não zero torna o flow falho; publicação falha após carga
confirmada retorna `PARCIAL`, preservando dados já promovidos.

## Coordenação e retomada

Trava de sessão PostgreSQL `2026112002` protege toda rodada IBGE, inclusive manual.
É independente do coordenador BCB e da trava IBGE de promoção/publicação
`2026112001`. Recuperação de auditoria aberta exige trava adquirida, mesmo
hostname e PID comprovadamente ausente. Incerteza preserva o registro.
Bronze, fatos e checkpoints não são apagados.

No início do worker, o gerenciador pagina a fila vencida dos seis deployments
próprios. Solicita a rodada BCB atual e, havendo agendas IBGE automáticas vencidas,
uma rodada IBGE consolidada: reconciliação tem prioridade sobre localidades,
que tem prioridade sobre incremental. Manuais e outros projetos são preservados.
Chaves de idempotência reduzem duplicação na mesma inicialização/minuto.

Depois de confirmar as substitutas, grava atomicamente um marco UTC em
`.cache/prefect/retomada_projeto.json`. Não há cancelamento remoto com `force=True`:
o estado pode avançar enquanto a fila é consultada. O próprio fluxo verifica o
marco ao iniciar; se for agenda automática anterior, retorna
`CanceladoNaRetomada/CANCELLED` antes de criar subprocesso ou consultar fontes.
Rodada que já iniciou não é interrompida por esse mecanismo.

Agendas antigas podem continuar visíveis até o worker processar seu descarte;
filas grandes levam mais tempo para limpar. Não há garantia de exatamente uma
execução em todas as falhas de rede/máquina. Falha ao solicitar substituta
preserva o marco anterior e a fila para nova tentativa.

## Operação Windows

Máquina ligada, sessão aberta, Docker/PostgreSQL/MinIO e tarefas Prefect ativos.
MinIO indisponível causa falha, sem troca silenciosa para disco. Docker Desktop
não é iniciado por esses fluxos. A consolidação ocorre no início do worker;
suspensão sem reinício não executa essa retomada. Antes de reiniciá-lo após pausa
longa, verificar ausência de rodadas ativas no painel.

```powershell
Start-ScheduledTask -TaskName PipelineETL-Prefect-servidor
Start-ScheduledTask -TaskName PipelineETL-Prefect-worker
Get-ScheduledTask -TaskName PipelineETL-Prefect-*
```

Preparação do servidor/papel/tarefas e registro em outra cópia:
[operação BCB](orquestracao-local.md). Preparação do objeto:
[MinIO local](armazenamento-s3-local.md). O comando
`uv run --project orquestracao --frozen python orquestracao/gerenciar.py registrar`
registra os seis deployments após preparar os ambientes e iniciar o servidor.

## Evidências

- Incremental real: flow `eed7cd3f-6ca6-4110-85b9-35ba5725b292`, `COMPLETED`.
  Pai SQL `987d7237-f933-4c14-8001-accd6c5b10b2`, `SUCESSO`; seis manifestos S3,
  população 2026, 5.571 linhas lidas/válidas. Publicação `JA_PUBLICADA`,
  core/gold 1, `PRONTA`.
- Worker atualizado, publicação sem nova coleta:
  `e8584333-c628-40f1-a9a3-8e972be62fef`, `COMPLETED`.
- Simulação com SDK/servidor reais:
  `122eedf4-b3ac-4667-9ad3-5e59c5b40381`, `CanceladoNaRetomada/CANCELLED`,
  com subprocesso bloqueado no ensaio. Classificação antiga/manual/futura tem
  testes independentes, sem APIs externas.
- Relatórios privados em `dados/descoberta/`:
  `agendamento_ibge_20261119.json`, `auditoria_agendamento_ibge_20261119.json`,
  `publicacao_coordenada_ibge_20261119.json`, `descarte_agenda_ibge_20261119.json`.
- **523 testes, cobertura 94,32%**, Ruff e mypy aprovados.
  Log `.cache/verificacao_agendamento_ibge_final.log`.

Pendências M2: instrumentação complementar, demonstração final reproduzível e
reconciliação do checklist geral. M3/GitHub seguem adiados.
