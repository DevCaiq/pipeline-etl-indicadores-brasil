# Orquestração BCB local

Autorização: usuário escolheu execução na máquina local; seguir seção9 do plano. Agendas America/Sao_Paulo: incremental20h, primeirodomingo21h, publicação22h. Sem IBGE e sem serviço externo.

- [x] Implementar coordenador CLI para três séries independentes + publicação, estado global SUCESSO/PARCIAL/FALHA, sem retryHTTP adicional, com testes offline.
- [x] Adaptador Prefect3.9.3 isolado em orquestracao/uv.lock e ambiente próprio: subprocesso da CLI existente, sem traduzir contratosSDK. Processo worker local e servidor loopback, banco/credenciais PostgreSQL exclusivos.
- [x] Registrar deployments/agendas, limitar worker1; conferir execução por deployment e reinício/catch-up sem reexecutar toda fila atrasada. Preparar inicialização Windows reversível e logs locais, sem senhas em argumentos/agendador.
- [x] Testar suíte, Prefectreal/API local, permissões e agendas; documentar limites e retomada. Não declarar execução com PC desligado, serviço Windows permanente ou IBGE.

Decisão: SDK Prefect em ambiente separado evita alterar dependências de FastAPI/Starlette já verificadas. Adaptador chama a CLI do ambiente principal, que chama os serviços existentes; lógica de negócio não importa Prefect. Sem retry de flow/task, sem carga histórica automática; publicação pode recuperar sem HTTP. Não criar conta cloud nem notificações externas.

## Evidências — concluídas em 19/11/2026

Prefect 3.9.3/106 pacotes em orquestracao/.venv com lock próprio; API/dependências raiz preservadas. Banco/papel isolados, URL secreta ignorada, CONNECT no etl negado ao papel Prefect. Servidor4200loopback+workerprocess1 e poolconcurrency1,3deploymentsagendasSPcorretas. TarefasWindowslogonInteractiveLimited registradas e Running, sem senha em argumentos. Não simulado rebootWindows; Start-ScheduledTaskreal validou inicialização e retomada.

Execução real inicial d4c0bc3f-5391-4d25-924f-6aca0f8d9fc6 Completed; duasretomadas Completed; final b0aad655-8430-4361-b4c6-f8344e5e4abf Completed/paiSQL34472392-02a5-4ecd-8804-72cee451248f SUCESSO. Selic2515(+1em19/11),dólar1727,IPCA93=4335fatos/4324públicas. Gold23/23PRONTA,351agregados; APIcompletaHTTPpreservoudados/auditoria. PublicaçãonoopJA_PUBLICADA reconhecida sem classificarqualquerIGNORADAcomosucesso.

Revisão identificou statusparcialperdido, IDdeerroperdido, bootstrapnãoretomável e auditoria interrompida. Corrigidos com testesvermelho/verde: progressoDTOouEXISTScargaconfirmada; IDs preservados; credencialfsyncantesDB/retomada; trava sessãofluxo inteiro, hostname/PIDeContextVarpaifilhos; recuperação sóprocessoausenteetravalivre, inclusofilhosdepaifinalizado. Consultanativaincertaretornaativo; aquisição/liberaçãoambíguainvalida conexão. Retomadapaginafilas200e cancelaapenasauto_scheduleddopropriopool. Não apaga bronze/fatos/checkpointsconfirmados.

Suítefinal332aprovados54,94s/cobertura95,39%; mypy44arquivos, Ruff/formatação e wheel aprovados. Testesoffline de status/ID/progresso, trava/PIDpai-filhos, falhadediscoantesDB, e filapaginadasemcancelarmanual. Primeiras rodadas identificaramtipagemSQLno teste e prefixo/api no mock; ambos corrigidos antes da suítefinal. Pip-auditambienteprefectsemvulnerabilidadesconhecidas. Revisãofinalestáticanãoidentificouimportantesremanescentes.

Limitesdoc: PC+sessaologada+Docker/processosativos, aguardo5min/3reinícios1min noAgendador, logssemretençãoautomática, semCloud/IBGE/notificações/reexecuçãodecadavencido. Catchupéincrementalatual; reconciliaçãoperdidaexigecomandomanualoupróximaagenda. Sempromessadeexactly-once/execuçãoPCdesligado; M1globalnãoencerrado. Guia docs/orquestracao-local.md.

Conferência final Windows: consulta de PID migrada de tasklist para OpenProcess/GetExitCodeProcess/CloseHandle, após Bandit sinalizar subprocessos. Sem supressões de segurança; última suíte 332/95,39% em54,94s e Banditzeroachados. mypy também aprovado --platform linux. Revisão estática da API nativa confirmou HANDLE/pointers/fechamento; PID DWORD pressupõe metadados gerados por os.getpid, observação menor para endurecimento futuro de dados de auditoria manualmente inválidos. Tarefas verificadas Running, Interactive e Limited. Nenhum importante remanescente.
