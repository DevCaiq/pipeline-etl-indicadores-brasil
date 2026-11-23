# Revisão para o primeiro envio ao GitHub

Data: 23/11/2026. Destino indicado pelo responsável:
`https://github.com/DevCaiq/pipeline-etl-indicadores-brasil.git`.

## Escopo

Revisão local de código, estrutura, seleção Git, empacotamento, credenciais,
documentação e verificações automatizadas. Não houve commit, push, alteração de
configurações remotas ou criação de recursos na nuvem nesta etapa.

A consulta `git ls-remote` ao endereço indicado terminou com sucesso sem retornar
referências. Isso é compatível com um repositório vazio. O conector GitHub pediu
autenticação repetidamente; não foi possível conferir pela API a visibilidade,
proteções de branch ou opções de segurança da conta. Nenhuma destas configurações
é presumida como habilitada.

## Correções realizadas

- Reforço do `.gitignore` e `.dockerignore` para chaves privadas, certificados,
  dumps, diretórios de credenciais e ferramentas locais.
- `.gitattributes` para finais de linha compatíveis com scripts Linux.
- Licença MIT do código em `LICENSE`, separada das condições dos dados oficiais
  em [licença dos dados](licenca-dados.md). Texto jurídico padrão preservado.
- [Política de segurança](../SECURITY.md) com limites da operação local, orientação
  de relato privado e restrição de `/metrics` na futura hospedagem.
- README com início rápido para uma clonagem nova, geração exclusiva de senhas,
  banco de testes separado e sequência GitHub/CI → página → hospedagem.
- Script de reprodução sem caminhos pessoais fixos; executáveis pelo PATH,
  diretório do projeto dinâmico, interpretador por sistema e revisão Alembic
  obtida do grafo de migrações, sem fixar a antiga `0006`.
- Validação de credencial PUBLICADOR antes de conectar ao banco de testes;
  configuração incompleta retorna mensagem controlada.
- Distribuição fonte com lista explícita de diretórios/arquivos. A inspeção inicial
  encontrou cópias antigas de exemplos em `.cache` no sdist, sem segredo real;
  elas foram excluídas da seleção de empacotamento.

## Verificações

| Verificação | Resultado |
|---|---|
| Suíte completa inicial, PostgreSQL exclusivo | 588 testes, 95,80% de cobertura |
| Regressões dos ajustes de preparação | Três falhas reproduzidas antes da correção; três testes aprovados depois |
| Cópia limpa com credenciais e PostgreSQL próprios | 591 testes aprovados, migração `0010`, sete rotas HTTP 200 |
| Ruff e formatação após ajustes | Aprovados; 207 arquivos examinados pelo formatador |
| mypy | Aprovado, 56 módulos da aplicação |
| Bandit em `src` | Zero achados, zero erros, 6.847 linhas examinadas |
| pip-audit do ambiente principal | Nenhuma vulnerabilidade conhecida; pacote próprio editável não consultado como pacote publicado |
| Build e inspeção | Wheel e sdist construídos; sem arquivos operacionais, licença incluída e módulos de orquestração preservados |
| Lock | `uv lock --check` aprovado; nenhuma alteração de dependências |
| Seleção Git | Sem coincidências com credenciais locais ou padrões de token/chave na auditoria; arquivos privados ignorados |
| Histórico local | Zero commits antes desta entrega; nenhum histórico anterior para examinar |
| CI remoto | Não executado; depende do primeiro envio |

As amostras oficiais não foram alteradas e os testes automatizados não consultam
APIs externas. Sondagem do Git remoto e auditoria de vulnerabilidades usam rede
separadamente da suíte de testes.

Evidências privadas: `.cache/bandit_pre_github.json`,
`.cache/reproducao_m1_20261123_074220/testes.log` e
`dados/descoberta/reproducao_m1_20261123_074220.json`. A cópia limpa foi capturada
antes dos últimos ajustes documentais e da criação preventiva do diretório de
relatório em clone novo; esses ajustes finais não alteram o comportamento da API.
Containers da reprodução foram encerrados; volumes isolados foram preservados,
sem parar serviços ou remover volumes operacionais.

O Bandit restrito inicialmente ficou preso no cache da ferramenta fora do workspace;
a execução com acesso correto ao cache terminou com o resultado registrado acima.
Os processos restritos iniciados para a auditoria foram encerrados.

## Seleção dos arquivos

A auditoria considera `git ls-files --cached --others --exclude-standard`, que
inclui os arquivos ainda não rastreados candidatos ao primeiro commit. Ela procura
arquivos operacionais, formatos de chave/dump, padrões de token e coincidências
com credenciais locais, sem imprimir valores privados. O inventário privado com
SHA-256 e resultados fica em `.cache/auditoria_selecao_github.json`.

As verificações não substituem a inspeção do que for efetivamente adicionado ao
índice no primeiro commit. Não usar `git add -f` para incluir dados ou `.env`.
O histórico ainda não contém commits para auditar; esta revisão não certifica
histórico que venha a ser importado ou alterações posteriores.

## Limites para publicar os fontes e para hospedar

**Resultado: fontes aptos ao primeiro envio**, no escopo e com as verificações acima.
Não foi identificado bloqueio de segurança nos arquivos selecionados. Isso não
garante ausência de vulnerabilidades nem aprova exposição direta dos serviços.

O Compose atual publica serviços em `127.0.0.1`. A futura exposição pública precisa
de HTTPS, proxy e regras de rede. Em particular, `/metrics` consulta o banco e está
fora do limitador de `/api/`: restringir a rota a Prometheus/rede administrativa.
Banco, Redis, Prefect, MinIO, Grafana e Prometheus não devem ser expostos diretamente.

No GitHub, depois do primeiro envio, acompanhar o workflow de qualidade. Execução
local não prova aprovação de CI Linux. Conferir disponibilidade de Dependabot,
secret scanning e proteção de push para a conta/repositório, e habilitar quando
aplicáveis. Não foi alegado que essas opções já estejam ativas.

Compartilhar só pequenas amostras oficiais com metadados de origem. Dados
operacionais, backups, segredos e relatórios locais ficam fora do repositório.
Condições de dados e a [decisão do protótipo](decisao-aceite-local-m1-m2.md)
permanecem documentadas, sem licença nominal inventada ou contato aos órgãos.
