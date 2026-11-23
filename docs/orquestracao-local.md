# Orquestração BCB na máquina local

Atualização M2: três agendas IBGE acrescentadas ao mesmo pool. Ver
[agendamento IBGE](orquestracao-ibge-local.md). A retomada foi atualizada para
descartar agendas antigas no próprio fluxo, antes do ETL, preservando processos
que já iniciaram.

## Estado verificado em 19/11/2026

Prefect 3.9.3 instalado em ambiente isolado, servidor em http://127.0.0.1:4200 e worker de processos com concorrência global de um no pool pipeline-etl-local. As duas tarefas do usuário PipelineETL-Prefect-servidor e PipelineETL-Prefect-worker foram registradas no Agendador do Windows, iniciadas e verificadas Running. Não foi criada conta Prefect Cloud nem serviço externo.

| Deployment local | Agenda America/Sao_Paulo | Ação |
|---|---|---|
| pipeline-bcb-local/bcb-incremental | Diariamente às 20h | Coletar/validar/carregar as três séries e publicar gold |
| pipeline-bcb-local/bcb-reconciliacao | Primeiro domingo do mês às 21h | Reconciliar desde 2020 e publicar |
| pipeline-bcb-local/bcb-publicacao | Diariamente às 22h | Recuperar publicação sem consultar BCB |

A reconciliação usa cron 0 21 1-7 * 0 com day_or=false: dia do mês e domingo precisam coincidir. As outras agendas são 0 20 * * * e 0 22 * * *. O worker e cada deployment têm limite de um; o pool também mantém concurrency_limit=1, inclusive se outro worker for iniciado por engano.

## Pré-requisitos de operação

A máquina deve estar ligada, a sessão do usuário iniciada, Docker Desktop/PostgreSQL ativos e as tarefas Prefect em execução. As tarefas usam logon interativo do usuário atual, sem senha armazenada no Agendador e sem elevação. Isso não é um serviço que funciona antes do logon; não executa com computador desligado. Não foi simulado reinício completo do Windows, mas as tarefas registradas foram iniciadas pelo Agendador e executaram a retomada real.

Servidor aguarda a porta do PostgreSQL por até cinco minutos; worker aguarda a saúde do servidor por até cinco minutos. Após falha, o Agendador tenta reiniciar a tarefa até três vezes, com intervalo de um minuto. Se Docker não estiver ativo nesse período, abrir Docker Desktop e iniciar manualmente as tarefas. Não pressupor que o Docker Desktop inicia sozinho no logon.

## Separação dos ambientes e credenciais

- Aplicação/API continuam em .venv e uv.lock da raiz. A lógica de negócio não importa Prefect.
- SDK Prefect e suas dependências estão em orquestracao/.venv e orquestracao/uv.lock, com projeto próprio. A separação preservou as dependências já verificadas da API.
- Banco prefect_etl e papel orquestracao_etl são exclusivos do orquestrador, no mesmo PostgreSQL local. Foi confirmado que esse papel não tem CONNECT no banco etl. O ETL usa processamento/publicador, não o papel Prefect.
- .env.orquestracao armazena a URL secreta do banco do servidor. Gerenciador valida banco, papel, driver e endereço esperados antes de iniciar o servidor. Credenciais não aparecem nos argumentos das tarefas. Worker e deployments usam API local, sem receber a URL do banco Prefect do arquivo.
- PREFECT_HOME e perfis ficam em .cache/prefect. Telemetria do servidor desativada; API e painel em loopback. Arquivos .env, venvs, logs e dados operacionais permanecem ignorados pelo Git.

O bootstrap grava e sincroniza a credencial antes de criar papel/banco. Nova tentativa reutiliza a credencial e completa somente etapas faltantes, verifica proprietário e autentica o papel existente; nunca gira senha automaticamente. Se uma configuração estiver inválida, interromper e investigar em vez de apagar banco/volume.

## Executar e acompanhar

Abrir o painel http://127.0.0.1:4200 para ver deployments, próximas agendas e execuções. Abrir Docker Desktop primeiro, se estiver desligado.

```powershell
Start-ScheduledTask -TaskName PipelineETL-Prefect-servidor
Start-ScheduledTask -TaskName PipelineETL-Prefect-worker
Get-ScheduledTask -TaskName PipelineETL-Prefect-*
```

As tarefas já foram registradas nesta máquina. Para parar o consumo e depois o servidor:

```powershell
Stop-ScheduledTask -TaskName PipelineETL-Prefect-worker
Stop-ScheduledTask -TaskName PipelineETL-Prefect-servidor
```

Isso não remove bancos, agendas ou dados. Parar durante uma carga pode interromper a execução; usar preferencialmente quando não houver flow Running/Pending. A retomada reconcilia auditoria de processos comprovadamente interrompidos, conforme seção seguinte.

Para execução manual do pipeline, sem iniciar outro worker:

```powershell
uv run --frozen python scripts/executar_pipeline_local.py --modo incremental
uv run --frozen python scripts/executar_pipeline_local.py --modo reconciliacao
uv run --frozen python scripts/executar_pipeline_local.py --modo publicacao
```

Para preparar uma nova máquina/cópia, depois do banco e credenciais de negócio:

```powershell
uv sync --frozen
uv sync --project orquestracao --frozen
uv run --frozen python scripts/preparar_orquestracao_local.py
uv run --project orquestracao --frozen python orquestracao/gerenciar.py servidor
```

Manter esse terminal ativo, registrar deployments em outro terminal e depois iniciar worker:

```powershell
uv run --project orquestracao --frozen python orquestracao/gerenciar.py registrar
uv run --project orquestracao --frozen python orquestracao/gerenciar.py worker
```

Não iniciar worker manual adicional enquanto a tarefa Windows estiver Running. Para reproduzir o logon automático, executar infraestrutura/registrar-orquestracao.ps1 no PowerShell do usuário; o script só substitui tarefa própria se ação e argumentos coincidirem. Não copia senhas para o Agendador. Tarefas referenciam D:\pipeline-etl: mover o projeto exige reinstalar ambientes/corrigir caminhos e registrar novamente.

## Fluxo, falhas e retomada

O adaptador orquestracao/fluxos.py chama scripts/executar_pipeline_local.py no Python do ambiente principal. O coordenador executar_pipeline reutiliza atualizar_serie e publicar_bcb. Séries são sequenciais e independentes: falha em uma não impede as demais. Não há retries do flow; os retries HTTP continuam exclusivamente no cliente BCB existente. O subprocesso tem limite de uma hora; timeout marca o flow como falha, sem novo ciclo HTTP automático.

SUCESSO exige três séries concluídas e publicação efetivada ou já vigente (IGNORADA/JA_PUBLICADA). PARCIAL reconhece séries/janelas confirmadas, inclusive consultando cargas persistidas se uma exceção perdeu o DTO. Sem progresso confirmado, FALHA. IGNORADA por lock/ausência de pré-requisito não vira sucesso. Publicação pendente deixa o resultado parcial quando houve progresso; o deployment das 22h pode recuperá-la sem rede externa.

Uma trava PostgreSQL de sessão protege o coordenador inteiro (2026111901), enquanto as travas originais continuam protegendo promoção/publicação. A conexão é invalidada se houver dúvida na aquisição/liberação. O pai pipeline_bcb guarda hostname/PID; ContextVar inclui pai_pipeline_id nas execuções-filhas. Falhas que fornecem execucao_id preservam esse vínculo no resumo. A API mantém o histórico sanitizado; o modo novo pipeline_bcb pode ter fonte=null na view atual, sem expor parâmetros privados nem exigir migração somente para esse rótulo.

No começo do worker, a retomada pagina as execuções Scheduled vencidas dos deployments próprios. Confirma uma solicitação incremental BCB atual e grava um marco UTC. Ao iniciar, agendas automáticas anteriores ao marco encerram como CanceladoNaRetomada antes do subprocesso ETL; não há cancelamentos remotos forçados. Execuções manuais são preservadas. A solicitação atual recebe chave de idempotência por minuto de inicialização. Não reiniciar repetidamente o worker para provocar novas coletas. Uma reconciliação mensal BCB perdida não é executada integralmente como catch-up: executar --modo reconciliacao manualmente quando necessário, ou aguardar a próxima agenda. IBGE possui prioridade própria para consolidar sua fila, conforme documentação M2.

Antes do novo coordenador, auditoria aberta só é finalizada depois de adquirir a trava e confirmar a ausência do PID no mesmo hostname. Windows usa OpenProcess/GetExitCodeProcess com HANDLE tipado e CloseHandle em finally; nunca os.kill no Windows. Apenas consulta o processo, sem encerrá-lo. Falha/permissão/incerteza na consulta é tratada como presença/incerteza: preservar o registro. Processo ativo, hostname diferente, PID ausente/inválido e PID reutilizado exigem inspeção conservadora. Também são recuperados filhos abertos de pai já finalizado. Registros interrompidos recebem FALHA/PROCESSO_INTERROMPIDO_CONFIRMADO; fatos, bronze e checkpoints confirmados não são apagados. Isso não reconstrói contextos de auditoria antigos que não tinham vínculo/PID e não prova execução exatamente uma vez em todos os cenários de falha de máquina/rede.

A consolidação da fila ocorre no início do worker, não em cada desbloqueio da tela/retorno de suspensão. Não extrapolar esse ensaio para funcionamento sem sessão ou infraestrutura permanentemente disponível.

## Logs, evidências e verificações

Logs dos processos em .cache/servicos; logs das execuções ETL em .cache/execucoes. Não contêm configuração secreta deliberadamente impressa, mas continuam operacionais e privados. Não foi implementada limpeza automática: revisar/arquivar logs antigos periodicamente. Backup de etl não inclui o banco prefect_etl; preservar credenciais e copiar o banco Prefect separadamente se o histórico de orquestração precisar ser recuperado. Ausência desse histórico não apaga fatos/bronze do projeto.

Verificações reais:

- Flow d4c0bc3f-5391-4d25-924f-6aca0f8d9fc6: incremental por deployment, Completed, três séries e publicação SUCESSO.
- Inicialização pelo Agendador: retomadas 3b798a16-7084-4d5d-b081-7fde9343bc53 e a038a3fb-eab7-4d5f-b9f5-252b2b71abfb Completed.
- Validação final b0aad655-8430-4361-b4c6-f8344e5e4abf Completed; pai SQL 34472392-02a5-4ecd-8804-72cee451248f SUCESSO, com três atualizações, cinco coletas/cargas/validações e publicação JA_PUBLICADA auditadas sob pai_pipeline_id.
- Em 19/11/2026, Selic recebeu uma observação nova: core total 4335, públicas 4324, gold core 23/gold 23 PRONTA. Dólar segue referência 18/11 e IPCA outubro. Reaplicações da mesma janela não duplicaram fatos. API completa local novamente conferida contra SQL e sem escrita.
- Suíte final: 332 testes aprovados em 54,94s, cobertura global 95,39%; testes de status, erro técnico com ID, progresso persistido, perda de resposta da trava, dúvida de PID, exclusão de coordenadores, recuperação pai/filho, falha de disco antes do banco e fila paginada simulada. Suíte sem APIs externas.
- Ruff/formatação, Bandit e mypy (44 arquivos de produção, incluindo conferência de tipos para Linux) aprovados; wheel recompilado. A primeira análise Bandit motivou a substituição do comando tasklist pela consulta nativa Windows, sem supressão de alertas. Ambiente Prefect auditado com pip-audit: nenhuma vulnerabilidade conhecida encontrada na consulta. Isso não é garantia de ausência de falhas.

Relatórios locais: dados/descoberta/deployments_locais.json, execucao_prefect_final.json, retomadas_prefect.json, orquestracao_verificada.json e sondagem_api_bcb.json. Revisão independente identificou os ajustes de recuperação/auditoria descritos acima; corrigidos e verificados. Não publicar essas evidências operacionais sem revisão.

Referências de implementação: [Prefect 3.9.3 no PyPI](https://pypi.org/project/prefect/3.9.3/), [workers de processos](https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/workers.mdx) e [calendários/timezone](https://github.com/PrefectHQ/prefect/blob/main/docs/v3/concepts/schedules.mdx). Contratos conferidos também no SDK instalado e na API local.

## Pendências

Executar/revisar pendências de homologação (incluindo licença específica 433 e cobertura), consolidar o runbook e os critérios finais do M1. A agenda das 22h recupera publicação; não implementa uma nova varredura completa de qualidade independente da extração. Antes de M2, conferir recursos adicionais e atualizar o calendário IPCA com nova evidência oficial quando necessário. Não declarar M1 global encerrado apenas porque o agendamento está ativo.
