# Ensaio local de recuperação M1 — 18/11/2026

## Resultado

Foram demonstrados dois caminhos em bancos novos, sem trocar URLs da aplicação: restauração do backup e reconstrução offline pelo bronze. A base etl permaneceu idêntica antes/depois. Todas as verificações ocorreram no PostgreSQL local existente; os papéis globais e senhas já estavam disponíveis nesse mesmo cluster.

| Caminho | Banco exclusivo | Resultado |
|---|---|---|
| Restauração | etl_ensaio_rest_20261119_005954_dc9089 | Todas as tabelas/MVs, catálogo e permissões comparados com a origem |
| Reconstrução | etl_ensaio_replay_20261119_005954_dc9089 | 49 promoções reaplicadas na ordem original; fatos, origem, cobertura e gold iguais |

Os nomes usam UTC de 19/11; o ensaio ocorreu na noite de 18/11 em America/Sao_Paulo. Os bancos foram preservados para inspeção. Nenhum banco/volume foi removido; não houve publicação externa nem chamada BCB.

## Restauração do backup

Arquivo usado: backups/etl_historico_validado_20261118_180556.dump, formato custom PostgreSQL. Executado pg_restore com --exit-on-error --single-transaction em banco novo criado a partir de template0, proprietário migracoes, CONNECT restrito aos papéis do projeto. O ensaio não usa --clean e recusa reutilizar destinos existentes.

Foram comparados checksums SHA-256 lógicos e contagens de todas as tabelas e três MVs, incluindo 4334 fatos e auditoria completa. O catálogo verificado inclui colunas, defaults, precisão/escala, restrições, índices, esquemas, definições de views/MVs/funções, proprietários e privilégios padrão/de relações, por coluna e do banco. As ACLs por coluna de ops.publicacao foram verificadas explicitamente. Revisão Alembic 0006 preservada.

Na primeira tentativa, a comparação textual estrita apontou diferenças: pg_restore reescreve o cast de arrays varchar→text, e as ACLs das MVs foram reordenadas. A investigação confirmou dados idênticos e permissões equivalentes. O verificador passou a ordenar as ACLs e uniformizar somente esse cast textual de literais, com testes que preservam valores divergentes. Não foram ignoradas tabelas nem desativadas comparações de esquema. Os dois bancos da tentativa inicial, com sufixo 20261119_005802_2cd71b, também permanecem locais; o replay dessa tentativa não chegou a ser executado.

Tempo medido de restore mais comparação: 1,375 s. Medição única local, com cluster e imagem já disponíveis, excluindo criação do banco, preparação e HTTP. Não é benchmark nem promessa de RTO.

## Reconstrução pelo bronze

O plano foi derivado apenas das promoções de carga_bcb com situação SUCESSO, ordenadas por confirmado_em/execucao_id. Foram preservadas as 49 entradas, inclusive cargas iguais reaplicadas; não se escolheu arbitrariamente o manifesto mais recente. Cada manifesto teve identidade, corpos e SHA-256 revalidados antes do ensaio e durante a carga.

No segundo banco, Alembic aplicou 0001–0006 como migracoes. O papel processamento reaplicou as cargas e publicador publicou as três MVs. Nenhum HTTP externo foi feito.

A comparação semântica confirmou exatamente:

- 4334 fatos: chave, valor Decimal, instante original da coleta e checksum do manifesto de origem;
- três checkpoints: fim consultado e última referência por série;
- catálogo de séries e esquema/permissões;
- geração core 22/gold 22, PRONTA e data de publicação;
- 248 agregados mensais, 21 anuais e 82 IPCA em 12 meses.

IDs de execução/lote e instantes de auditoria são novos no replay, conforme esperado; não foram apresentados como restauração da auditoria antiga. A origem e a linhagem lógica dos fatos, incluindo os cinco valores do primeiro lote Selic, coincidiram. O replay recria auditoria de validação/carga/publicação; consultas externas e execuções-pai históricas não são inventadas. Por isso ultima_consulta pode ficar ausente no endpoint de frescor do banco reconstruído: não houve nova coleta.

Tempo de migrações, 49 cargas, publicação e comparação: 13,203 s. Medição local única, sem compromisso de desempenho. A reconstrução isolada foi comparada; não houve troca automática da aplicação para esse destino.

## API sobre cada destino recuperado

scripts/verificar_api_local.py recebeu --banco-ensaio para direcionar simultaneamente o retrato SQL e o processo HTTP à mesma base. O acesso HTTP usou api_leitura; cada servidor próprio foi encerrado ao final.

Em ambos os bancos, foram comparadas as 4323 observações públicas e os 351 agregados entre SQL e HTTP, além de probes, catálogo, documentação, paginação, ETag 304, erros sanitizados e limite por IP sem confiar em X-Forwarded-For. Retratos antes/depois confirmaram que a API não alterou os dados, incluindo SHA-256 do conteúdo de execuções, lotes e preparação. O verificador HTTP recusa Python com -O/PYTHONOPTIMIZE para não executar com asserts desativados; um teste específico confirma essa proteção.

Relatório principal local: dados/descoberta/recuperacao_20261119_005954_dc9089.json, com hash do backup, plano de promoções, execuções do replay, tempos e checksums lógicos. Relatórios HTTP: sondagem_api_etl_ensaio_rest_20261119_005954_dc9089.json e sondagem_api_etl_ensaio_replay_20261119_005954_dc9089.json, na mesma pasta ignorada pelo Git.

## Repetir o ensaio

Com Docker/banco ativos, backup confiável, bronze e .env.banco locais disponíveis:

```powershell
uv run --frozen python scripts/ensaiar_recuperacao_local.py backups/etl_historico_validado_20261118_180556.dump
uv run --frozen python scripts/verificar_api_local.py --banco-ensaio NOME_RESTAURADO_RETORNADO
uv run --frozen python scripts/verificar_api_local.py --banco-ensaio NOME_REPLAY_RETORNADO
```

O primeiro comando cria dois novos bancos e conserva os destinos; não executar repetidamente sem necessidade. O backup precisa corresponder à base etl atual: comparação estrita recusa uma cópia antiga divergente. O replay compara também a data de publicação atual; ao repetir em outro dia, preparar um estado de referência coerente antes de avaliar a igualdade temporal. Não usar backups não confiáveis, pois restauração executa SQL do arquivo.

## Limites e próximos critérios

O ensaio não demonstra reconstrução de cluster/volume perdido, recuperação de papéis/senhas, desastre em outra máquina ou storage remoto. pg_dump de um banco não contém papéis globais. Guardar credenciais e bootstrap separadamente, com acesso restrito. Bronze e dump no mesmo equipamento não constituem backup externo.

Próximos critérios: calendário automático com vigência/fallback, licença 433, benchmark conforme protocolo, orquestração e demais pendências do plano. O calendário atual foi conferido separadamente em [calendário IPCA](calendario-ipca.md). Não declarar M1 global concluído nem metas RPO/RTO garantidas.

## Verificação final do projeto

### Complemento operacional em 19/11/2026

`scripts/ensaiar_falha_publicacao.py` criou um dump e um banco clone novo;
uma falha foi injetada no segundo refresh. O primeiro refresh foi revertido
na mesma transação, core e checkpoints permaneceram iguais, e a publicação
ficou `PENDENTE`. Após remover a falha, nova publicação chegou a `PRONTA`.
A origem foi conferida antes/depois e preservada. Relatório local:
`dados/descoberta/falha_refresh_20261119_040950.json`.

Para repetir, com Docker e credenciais locais disponíveis:

```powershell
uv run --frozen python scripts/ensaiar_falha_publicacao.py
```

O comando escreve somente em clone criado pelo próprio ensaio e conserva
backup/destino para inspeção. Em uma falha operacional real, conferir a execução
e a geração em `ops.publicacao`; corrigir a causa e repetir a publicação com
papel `publicador`. Não alterar `versao_gold` manualmente nem promover gold
parcial. Uma falha de refresh não exige recarregar fatos já confirmados.

Reprodução por fonte limpa, ambiente novo e credenciais próprias também passou:
`scripts/verificar_reproducao_m1.py`, relatório
`dados/descoberta/reproducao_m1_20261119_040532.json`. A reprodução incluiu
instalação frozen, migrações, seeds, 332 testes e sete sondagens HTTP.
Não equivale a CI remoto nem a backup fora da máquina.

Após os ajustes de revisão, as sondagens HTTP dos dois bancos foram repetidas e passaram. A comparação somente leitura final incluiu ACLs por coluna e banco, conferiu a semântica dos três bancos e o conteúdo original antes/depois de todas as sondagens. Suíte completa: 279 testes aprovados em 56,49 s, cobertura global 96,59%; Ruff/formatação e mypy (41 arquivos de produção) aprovados. A lógica e o esquema de produção não foram modificados nesta etapa.
