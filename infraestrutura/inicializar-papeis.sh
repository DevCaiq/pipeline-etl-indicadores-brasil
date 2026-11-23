#!/usr/bin/env bash
# Executado pela imagem oficial somente na primeira inicialização do volume.
set -euo pipefail
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 \
  --set senha_migracoes="$SENHA_BANCO_MIGRACOES" \
  --set senha_processamento="$SENHA_BANCO_PROCESSAMENTO" \
  --set senha_api="$SENHA_BANCO_API" \
  --set senha_publicador="$SENHA_BANCO_PUBLICADOR" <<'SQL'
SELECT format('CREATE ROLE migracoes LOGIN PASSWORD %L', :'senha_migracoes') \gexec
SELECT format('CREATE ROLE processamento LOGIN PASSWORD %L', :'senha_processamento') \gexec
SELECT format('CREATE ROLE api_leitura LOGIN PASSWORD %L', :'senha_api') \gexec
SELECT format('CREATE ROLE publicador LOGIN PASSWORD %L', :'senha_publicador') \gexec
GRANT publicador TO migracoes;
ALTER DATABASE etl OWNER TO migracoes;
REVOKE ALL ON DATABASE etl FROM PUBLIC;
GRANT CONNECT ON DATABASE etl TO migracoes, processamento, api_leitura, publicador;
SQL
