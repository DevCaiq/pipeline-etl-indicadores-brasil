# Segurança

O código é publicado para estudo e portfólio. A operação validada até aqui é local.
Publicar os fontes não significa que os serviços estejam preparados para exposição
direta à internet.

## Informar uma vulnerabilidade

Não publique senhas, tokens, dados pessoais, dumps ou provas com segredos em issues.
Se o repositório disponibilizar a opção **Security → Report a vulnerability**, use
esse canal privado. Se ela não estiver habilitada, peça um canal privado ao
mantenedor sem descrever publicamente detalhes exploráveis ou incluir segredos.
Não há prazo de atendimento ou programa de recompensas estabelecido.

## Operação

- Gere credenciais por ambiente; os arquivos `.env*` operacionais não pertencem ao Git.
- Exemplos com `SUBSTITUIR` não são senhas de uso. As contas SQL têm papéis separados.
- Mantenha PostgreSQL, Redis, Prefect, MinIO e painéis administrativos privados.
- Restrinja `/metrics` ao monitoramento interno. A rota consulta o banco e não está sujeita ao limite de `/api/`; não a exponha diretamente ao público.
- Para implantação pública, configure HTTPS, proxy, limites e regras de rede antes da exposição.
- Se uma credencial for publicada, revogue-a e substitua-a; removê-la do arquivo não elimina cópias no histórico.
- Auditorias e scanners reduzem riscos conhecidos, sem garantir ausência de vulnerabilidades.

Consulte o [roteiro de hospedagem](docs/oracle-cloud-always-free.md) e a
[revisão para GitHub](docs/revisao-publicacao-github.md).
