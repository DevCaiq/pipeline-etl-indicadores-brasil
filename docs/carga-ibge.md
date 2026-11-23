# Carga e publicação IBGE local

`carregar_ibge(armazenamento, manifestos, motor)` recebe descritores `ObjetoBronze` de regiões, UFs, municípios, metadados, períodos e um ou mais anos de população. Cada coleta é revalidada por SHA-256, identidade e parâmetros antes do contrato. Somente anos disponíveis desde 2020 e cobertura municipal exata são aceitos. Nenhum acesso HTTP ocorre durante a carga.

A promoção utiliza uma única transação e advisory lock `2026112001`. A identidade territorial deriva do SHA-256 do JSON canônico das dimensões normalizadas; membros e origem do snapshot existente são preservados. Dimensões atuais usam comparação semântica; municípios ausentes ficam inativos. Uma redução territorial que deixe fatos extras em um ano do pacote é rejeitada para preservar os fatos e impedir um ano com snapshots misturados. Anos fora do pacote permanecem intactos.

Fatos iguais preservam lote, instante e origem. As execuções bem-sucedidas guardam evidências de recoleta por ano e por recurso territorial (`regioes`, `ufs`, `municipios`), com instante e SHA-256 normalizado para impedir revisões divergentes mais antigas mesmo depois de uma recoleta igual. Somente alterações semânticas de dimensões ou fatos avançam a geração `ibge`. Falhas bloqueiam o pacote e registram execução, etapa e quarentena com referências bronze; nenhuma observação é inventada.

`publicar_ibge(motor)` valida cobertura por membros e snapshot único por ano/indicador, atualiza `mart.mv_populacao_uf`, `mart.mv_populacao_regiao` e `mart.mv_populacao_brasil` na mesma transação e avança gold para core. Uma falha desfaz todos os refreshes. Ausência oficial `...` permanece NULL: subtotal disponível e total completo são campos distintos.

Verificação local autorizada, exclusivamente em `etl_testes`, sem API externa:

```powershell
.venv/Scripts/python.exe scripts/testar_banco.py --no-cov testes/integracao/test_carga_ibge.py -q
```

Os testes usam `httpx.MockTransport`, respostas oficiais arquivadas (município reembalado como lista e série recortada por ano) e variantes sintéticas explicitamente identificadas. Cobrem idempotência, marcador desconhecido, bronze antigo divergente, evidência após recoleta igual, snapshots, incompletude gold, rollback de refresh e papéis reais `processamento`/`publicador`.

Recência de regiões ou UFs não atualiza a proveniência dos municípios. Uma revisão divergente de qualquer recurso territorial precisa ser mais recente que a última evidência bem-sucedida desse mesmo recurso, inclusive quando a última recoleta era semanticamente igual. A regressão cobre municípios antigos misturados a regiões/UFs recentes e confirma preservação dos fatos, snapshot e geração.
