# Métricas persistidas da coleta M2

Os clientes síncronos BCB e IBGE contam cada tentativa imediatamente antes de iniciar a chamada HTTP. Uma falha de conexão ou timeout também conta como requisição; resposta confirmada não é requisito. A primeira chamada de cada consulta não é retentativa. Esperas adiadas e consultas recusadas antes de iniciar HTTP não incrementam os contadores.

`ClienteBCB.metricas_coleta` e `ClienteIBGE.metricas_coleta` devolvem cópias cumulativas com dois inteiros não negativos: `requisicoes` e `retentativas`. Cada coordenação captura os valores antes do trabalho e persiste somente a diferença na execução pai em `ops.execucao.parametros.metricas_coleta`:

```json
{"requisicoes": 12, "retentativas": 2}
```

A gravação ocorre ao sair da coordenação, inclusive em falha, sem reler bronze, guardar URLs ou incluir mensagens de exceção. Falha nessa gravação produz aviso sanitizado e preserva o resultado ou erro original do ETL. A instrumentação mantém os limites e políticas de retentativa existentes e a ordem de preservação do bronze antes do parse.

Execuções antigas e clientes sem instrumentação válida não recebem zero artificial. O exporter deve distinguir ausência de observação de uma execução instrumentada sem requisições, como publicação isolada IBGE. Os clientes pertencem à coordenação que os utiliza; compartilhar uma instância com trabalho concorrente externo à coordenação contaminaria o delta.

Os contadores ficam persistidos ao término, e não durante cada chamada. Encerramento abrupto do processo, interrupção antes do bloco final ou indisponibilidade do banco na gravação podem deixar o pai sem observação. Enquanto o pai está em andamento, a métrica pode estar ausente. Os totais são históricos dos pais instrumentados e não comprovam completude de todas as tentativas já realizadas. Persistir o agregado é telemetria complementar, sem garantia de entrega em falhas do banco ou do processo.

## Descoberta de períodos IBGE

Depois de validar a coleta de períodos e executar `descobrir_periodos`, o callback opcional `registrar_periodos` recebe a tupla de anos disponíveis. A coordenação grava no pai `parametros.anos_disponiveis` como lista de inteiros e `parametros.consulta_periodos_em` como instante ISO 8601 UTC. Isso ocorre antes da coleta de população e não exige outra leitura do bronze.

Esses anos representam disponibilidade na fonte, enquanto os anos do resumo representam a seleção para carga. Uma coleta posterior pode falhar mesmo com a consulta de períodos registrada. A revisão0009 preserva essa consulta confirmada independentemente da situação global posterior; falha da carga não apaga a evidência da descoberta.
