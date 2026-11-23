# Armazenamento S3 e MinIO local — M2

## Estado validado em 19/11/2026

MinIO ativo em **http://127.0.0.1:9000**, bucket privado `bronze-etl`, prefixo
`bronze`, volume persistente `pipeline-etl_dados_objetos`. Console desabilitado,
porta publicada somente em loopback, processo `aplicativo` sem privilégios,
sondagem de saúde aprovada. Nenhuma conta ou recurso de nuvem criado.

O cliente da pipeline usa credenciais próprias, get/put apenas no prefixo,
listagem limitada e proibição explícita de excluir objetos ou versões.
As credenciais administrativas ficam separadas e servem ao provisionamento.
Ambas são geradas em `.env.armazenamento`, ignorado pelo Git.

## Preparar e retomar

Pré-requisitos: Docker ativo, ambiente principal sincronizado por `uv.lock` e
`.env.banco` já preparado nas etapas anteriores.

```powershell
uv run --frozen python scripts/preparar_armazenamento_local.py --iniciar --provisionar
```

O comando gera credenciais fortes quando o arquivo privado não existe,
constrói/inicia somente o serviço `objetos`, aguarda saúde HTTP e prepara bucket
versionado, política e usuário dedicado. A primeira compilação precisa de rede
para dependências oficiais e pode demorar; execuções seguintes reutilizam cache.
O arquivo existente é preservado, sem rotação silenciosa de credenciais.

Para repetir somente o provisionamento com o servidor ativo:

```powershell
uv run --frozen python scripts/preparar_armazenamento_local.py --provisionar
```

O bootstrap é restrito ao endpoint local na porta 9000. Recusa credenciais de
exemplo, identidade administrativa como identidade da pipeline, política própria
preexistente no bucket e permissões extras/grupos na conta dedicada. Essas
configurações são preservadas para revisão, sem remoção automática. Erros de
autenticação não são interpretados como bucket ou usuário inexistente.

O fluxo normal não usa política de bucket; a autorização autenticada fica na
política IAM dedicada. O versionamento é habilitado sem remover dados.
Não usar `--remove-orphans` para administrar esta composição parcial: outros
serviços do mesmo projeto, como API e monitoramento, continuam necessários.

## Uso pela pipeline

Disco continua como padrão. A coleta IBGE pode usar S3 explicitamente:

```powershell
uv run --frozen python scripts/executar_ibge_local.py --configuracao-s3 .env.armazenamento
```

Esse comando consulta IBGE oficial, grava bronze no S3 e carrega/publica usando
os papéis já existentes. Não foi usado para baixar novos dados nesta validação:
o ensaio consumiu o bronze já arquivado. O cliente é fechado inclusive em falhas;
credenciais AWS implícitas e retries automáticos não são usados. TLS continua
verificado em endpoints HTTPS; HTTP é permitido somente no ambiente local.

A integração operacional S3 desta etapa é do IBGE. O fluxo BCB M1 mantém seu
armazenamento em arquivos. O contrato genérico `ArmazenamentoObjetos` oferece
os mesmos descritores, bytes e verificações para disco e S3.

## Integridade e limite da imutabilidade

`S3Objetos.gravar_imutavel` usa `IfNoneMatch="*"`, checksum SHA-256 enviado ao
servidor e metadado SHA-256. Chave existente gera `ObjetoJaExiste`, inclusive
quando os bytes são iguais; nenhuma repetição reescreve silenciosamente.
Na leitura, tamanho e SHA-256 são comparados ao descritor original e o stream
é fechado. Chaves não canônicas são recusadas.

A imutabilidade é o contrato de escrita condicional do adaptador. Versionamento
preserva versões, e a conta da pipeline não pode excluir objetos/versões.
Não há retenção WORM/Object Lock: um cliente privilegiado ou um PUT direto que
ignore o adaptador pode criar outra versão. Por isso, usar o adaptador na
pipeline e manter as credenciais administrativas fora dela. Isso não equivale
a backup externo; o volume ainda fica na mesma máquina.

## Evidências do ensaio real

```powershell
uv run --frozen python scripts/verificar_s3_local.py
```

O verificador usa prefixo exclusivo, transfere o pacote da última carga IBGE
confirmada e restaura um backup M2 já validado em banco novo. O caminho e SHA-256
do backup são conferidos. `etl` recebe somente a consulta de metadados da carga;
nenhuma promoção é direcionada à origem. Cada repetição cria banco/prefixo novos
e conserva os destinos para inspeção; não executar como rotina agendada.

Resultado `dados/descoberta/objetos_s3_20261119_211019_50aeca.json`:

- Mesmos descritores/bytes em disco e S3, checksum incorreto detectado.
- Duas tentativas de sobrescrita recusadas; escrita concorrente teve um vencedor.
- Exclusão de objeto/versão, escrita fora do prefixo e leitura anônima recusadas.
- Dez manifestos e trinta objetos originais transferidos sem mudar bytes/hashes.
- Replay em `etl_ensaio_objetos_20261119_211019_50aeca`: arquivos e S3 confirmaram
  27.855 registros inalterados, zero inserções e zero alterações.
- Core/mart preservados, incluindo metadados e agregações; publicação subsequente
  `IGNORADA/JA_PUBLICADA`, core/gold 1. Auditoria do replay foi gravada só no clone.

Após reconstruir/reiniciar e reprovisionar o serviço, os 32 objetos do ensaio
(trinta originais e dois do contrato) continuaram presentes, com uma versão cada.
Bytes arquivados novamente comparados. Evidência:
`dados/descoberta/persistencia_s3_20261119.json`.

Suíte: **506 testes**, cobertura **94,44%**, Ruff e mypy aprovados em 55 módulos.
Log `.cache/verificacao_armazenamento_m2.log`. Testes automatizados continuam
sem APIs externas; o teste real do MinIO é um comando manual separado.
Wheel construído e conferido: inclui o módulo S3 e não inclui o arquivo de
credenciais. Dez sondagens finais da API/monitoramento retornaram 200.
Revisão independente encontrou duas lacunas no reprovisionamento; ambas foram
reproduzidas com testes e corrigidas antes da verificação final.

## Origem da imagem

As imagens oficiais das versões consultadas não estavam disponíveis. A imagem
local usa `go install` com tags fixas do código oficial, sem espelhos de terceiros:

- MinIO `RELEASE.2025-10-15T17-29-55Z`, módulo `9e49d5e7a648`.
- mc `RELEASE.2025-08-13T08-35-41Z`, módulo `7394ce0dd2a8`.
- Go 1.24.8 e base Python 3.12 fixados também por digest; `GOAMD64=v1` e CGO desabilitado.

Metadados Go ficam em `/usr/local/share/minio-compilacao.txt` e
`/usr/local/share/mc-compilacao.txt` na imagem. Hashes SHA-256 dos binários foram
registrados na evidência de persistência. Referências:
[release oficial do servidor](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)
e [releases oficiais do cliente](https://github.com/minio/mc/releases).
Consultar nesses repositórios também as licenças das dependências externas.

As [agendas IBGE](orquestracao-ibge-local.md) foram ativadas na etapa seguinte.
O verificador S3 seleciona o último pacote confirmado em arquivos para comparar
os dois adaptadores, mesmo quando cargas mais recentes já usam MinIO.
M3 e disponibilização no GitHub permanecem adiados. A instrumentação e a demonstração foram concluídas: ver [aceite técnico M2](aceite-tecnico-m2.md), com ressalvas de fonte explícitas.
