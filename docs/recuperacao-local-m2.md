# Backup e restauração local M2

## Evidência de 19/11/2026

Ensaio executado com banco local BCB e IBGE, sem consumir APIs externas.
Backup novo: `backups/m2_20261119_162132_7013d2.dump`.
SHA-256: `e52fd3225e91d782313aa3433283b9baa28749f51f221cb9c315895af1f674f0`.
Destino exclusivo: `etl_ensaio_m2_20261119_162132_7013d2`.
Relatório privado: `dados/descoberta/restauracao_m2_20261119_162132_7013d2.json`.

A restauração com `pg_restore --exit-on-error --single-transaction` levou
30,453 segundos. O ensaio completo começou às 16:21:32 UTC e terminou às 16:22:15 UTC.
Esse tempo é uma medição nesta máquina e neste conjunto, sem garantia de RTO.

Conferências aprovadas:

- Igualdade de contagens e SHA-256 dos registros completos de 24 tabelas/MVs,
  incluindo auditoria, linhagem e instantes; 4.335 fatos BCB e 27.855 fatos IBGE.
- Catálogo: colunas com tipos SQL completos (incluindo tamanho de `varchar`), restrições, índices, donos, permissões de banco/colunas,
  esquemas, views, materializadas, funções, gatilhos e posições de sequências.
- 25 consultas da API comparadas entre origem e restauração com papel
  `api_leitura`, cache desligado e o mesmo segredo temporário de assinatura.
- Cursores gerados na origem aceitos na cópia; duas segundas páginas coincidiram,
  preservando filtros. O valor opaco do próximo cursor é normalizado porque
  o instante da assinatura pode mudar; dados, metadados e paginação permanecem
  na comparação. Não se alega igualdade byte a byte de tokens gerados em instantes distintos.
  O ensaio exige ao menos uma segunda página e registra seu hash no relatório.
- Origem e cópia novamente retratadas após as consultas, sem alterações.

As rotas cobrem probes, catálogo/observações BCB, regiões, UFs, municípios,
população municipal e agregações Brasil/região/UF nos cinco anos disponíveis.
Marcadores ausentes e totais incompletos permanecem preservados.

## Repetir com segurança

Pré-requisitos: Docker com serviço `banco` saudável, ambiente Python sincronizado,
`.env.banco` privado com credenciais locais e IBGE já carregado na origem.

```powershell
uv run --frozen python scripts/ensaiar_restauracao_m2.py
```

O script cria backup exclusivo e um banco novo de nome aleatório; recusa bancos
fora do padrão `etl_ensaio_m2_DATA_HORA_SUFIXO` e não reutiliza destino existente.
Não executa DROP, TRUNCATE nem restauração em `etl` ou `etl_testes`.
Backup, banco e relatório ficam preservados para inspeção, inclusive em falhas.
Repetições criam novas cópias; não agendar esse ensaio como rotina de backup.

Executar fora do horário das cargas. Mudança na origem durante o ensaio faz a
comparação final falhar; não interpretar essa falha como autorização para alterar
a origem ou forçar versões. O relatório só indica sucesso com todas as conferências.
Consultar o log local para diagnosticar falhas; não copiar credenciais para relatórios.

O primeiro ensaio revelou perda dos filtros na montagem da segunda página pelo
verificador. Corrigido com teste de regressão; o ensaio completo foi repetido em
novo destino e aprovado. Não houve alteração na API de produção para essa correção.

## Limites

Este é um teste de restauração em outro banco do mesmo cluster e equipamento.
Papéis globais, credenciais e bootstrap são pré-requisitos existentes; `pg_dump`
de um banco não demonstra recuperação desses recursos. Não comprova perda do
volume/cluster, desastre em outro computador nem backup externo.

O dump contém o banco; os objetos bronze permanecem no filesystem local e não
são transportados por `pg_dump`. Replay imutável IBGE tem evidência própria em
[execução M2](execucao-local-m2.md). A restauração deste ensaio não baixa fontes,
não republica gold nem refaz auditoria: recupera os valores persistidos do backup.

M3 e disponibilização no GitHub continuam adiados.


## Complemento — restauração entre datas diferentes

A demonstração de 23/11/2026 restaurou snapshot BCB com referência anterior e
conferiu integralmente dados, catálogo, permissões e API no esquema0010.
Relatório `dados/descoberta/restauracao_m2_20261123_062513_6014e5.json`.
A causa observada na revisão antiga era `CURRENT_TIMESTAMP` nas materializadas:
pg_restore faz REFRESH e alterava data_referencia ao reconstruir em outro dia.
A 0010 usa a referência persistida de publicação; a migração requer core/gold
consistentes e trava BCB livre. Nenhum snapshot antigo foi declarado idêntico
ignorando metadados. A publicação posterior é operação separada e pode avançar
referência dentro da transação. Backups antigos continuam exigindo procedimento
compatível com sua revisão, não se presume correção retroativa de sua definição SQL.
