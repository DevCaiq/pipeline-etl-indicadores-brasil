# Ensaio de desempenho M1

Autorização: próxima etapa do plano principal, seção 13, protocolo já definido. Sem mudança de produto/esquema/dependências; servidor próprio loopback, encerrado ao final. Não executar ETL durante o ensaio, não alterar rate limit/configuração do servidor do usuário.

- [x] Registrar CPU/RAM Windows, recursos Docker, versões, dataset, pool e workers.
- [x] Verificador manual reutilizável: aquecimento 30s e medição 60s, 10 clientes, limite 100, workload misto documentado; medir p50/p95/p99, vazão e erros incluindo transporte/429/5xx. Elevar só o limite do processo próprio para 100000/min, registrar; sem Redis/304 e sem prometer SLA.
- [x] Comparar keyset e OFFSET no começo/meio/fim Selic, mesmas linhas, 10 repetições EXPLAIN ANALYZE BUFFERS; guardar planos originais em dados/descoberta. Sem índices/tuning prematuros ou dados artificiais no core oficial.
- [x] Verificar base inteira antes/depois e encerrar próprio servidor; documentar resultados reais, limites e protocolo reprodutível.
- [x] Executar verificações apropriadas dos scripts e revisão final; atualizar plano e próximo passo.

Decisão: ensaio M1 somente leitura (HTTP e SQL), a duração ETL recente já foi registrada no ensaio de replay, mas não constitui benchmark padronizado. O protocolo atual não exige recarregar dados nem validar a meta com cache (M2). Página final e gold podem conter menos de 100 itens no dataset real; registrar, sem fabricar volume. Concorrência fechada: cada cliente aguarda a resposta antes de enviar a próxima, sem taxa de chegada fixa.

## Evidências finais

Hardware registrado: i5-3470 4/4, Windows 33754714112 bytes de RAM; Docker4CPUs/16471625728 bytes, sem cota adicional no container. Credenciais não coletadas. Primeiro preparo falhou ao ler alembic_version com processamento; corrigido para view sanitizada, sem alterar permissões.

Ensaio real em desempenho_20261119_020401.json: aquecer30s, medir60s, concorrência10, limite100. 6061HTTP200 em60,0518s, 100,9295req/s, p95 149,0157ms, p99 210,1083ms; zero429/5xx/transporte/validação. Quatro cenários e sessãoSQLsomenteleitura. Treze tabelas/MVs preservadas porSHA256 e versão0006 pela view; próprio servidor encerrado nofinally. SQL60planos: keyset/OFFSET linhas idênticas, medianas ms início0,063/0,061, meio0,062/0,3455, fim0,038/0,676. Sem índice/tuning extra.

Seis testes de métricas passaram, Ruff/formatação aprovados. Sem mudança de produto, sem nova execução ampla desnecessária: última suíte completa permanece309/96,63% da etapa anterior. Revisão independente sem importantes; menores documentados (métrica aquecimento sem drenagem, pool do motorSQL e abortar JSON200 malformado). Não usar esses pontos para superestimar a medição principal, que inclui drenagem e não teve erros. Logs estruturados da aplicação ativos, access_log Uvicorn desativado.

Guias: docs/desempenho/protocolo-m1.md e 2026-11-18-m1-local.md. Próximo passo: orquestração/agendamento local. Sem SLA de hospedagem, cacheM2, escala sintética ou M1 global concluído.
