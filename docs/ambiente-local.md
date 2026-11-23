# Ambiente local — preparação inicial

Referência da sessão: 17/11/2026. Este relatório distingue ferramentas instaladas da aplicação ainda não criada.

## Verificações concluídas

| Item | Evidência |
|---|---|
| Sistema | Windows 10 Pro 22H2, build 19045, x64 |
| Memória | 31,4 GiB reportados, máquina informada com 32 GB |
| Python | 3.12.3 |
| Git | 2.48.1.windows.1; repositório local iniciado, branch principal, sem remoto/commit |
| WSL | 2.7.13.0, kernel 6.18.33.2-2; padrão 2 |
| Docker Desktop | 4.99.0.245822, pacote oficial via winget, instalador com hash validado |
| Docker Engine | Cliente e servidor 29.9.3, contexto desktop-linux, servidor linux/amd64 |
| Docker Compose | v5.7.0, comando docker compose |
| Container | docker run --rm hello-world concluiu e exibiu Hello from Docker! |
| uv | 0.13.9, pacote oficial astral-sh.uv via winget |

Docker Desktop iniciou em segundo plano, sem reiniciar Windows. Antes da instalação não havia distribuição WSL de usuário; o Docker gerencia seu backend próprio. Não instalar Ubuntu apenas por presumir requisito do Docker. Não foram alteradas opções BIOS/UEFI.

Consultas CIM exibiram hypervisor presente e flags isoladas de virtualização/SLAT falsas. Esses campos não provaram ausência de suporte: o daemon Linux e hello-world funcionaram. Teste operacional prevalece neste diagnóstico.

## PATH e contexto de execução

O processo do assistente foi iniciado antes da instalação, por isso não herdou o novo PATH. O primeiro hello-world falhou ao localizar docker-credential-desktop. Repetir com a pasta oficial Docker/resources/bin no PATH somente do processo resolveu; o pull e o container concluíram. Nenhuma alteração adicional global de PATH foi feita pelo assistente além da instalação dos pacotes.

Abra um novo PowerShell para receber o PATH registrado pelos instaladores e execute:

    python --version
    git --version
    uv --version
    wsl --version
    docker version
    docker compose version
    docker run --rm hello-world

Se o novo terminal ainda não localizar Docker/uv, verificar a pasta instalada antes de modificar PATH manualmente. Não imprimir conteúdo de .env ou configuração de credenciais para diagnosticar.

## Sandbox e Git

CIM, WSL e rede tiveram acesso negado no sandbox; consultas e instalação precisaram do executor autorizado fora do sandbox. Após inicializar Git, o executor restrito passou a falhar ao criar processos; arquivos finais foram escritos pelo executor autorizado.

Inicialmente .git foi criado pelo usuário de sandbox e gerou aviso de ownership no usuário Windows. Atribuir owner diretamente foi negado. Após verificar ausência de referências/commits, remoto e índice, somente os metadados Git vazios criados nesta sessão foram recriados sob o usuário Windows; todos os arquivos do projeto foram preservados. git status funciona sem exceção de confiança nesse usuário; nenhuma configuração global ou identidade foi alterada. O executor restrito também voltou a iniciar normalmente após a correção. Branch principal, sem commit/push/remote.

## Próxima fase

Base Python criada e verificada: pyproject.toml/uv.lock, pacote pipeline_etl, configuração tipada, registros JSON e comando verificar-configuracao. Instalação com uv sync --frozen; ver README para comandos de testes e qualidade. Pacote wheel instalado em segundo ambiente e executado fora da árvore de fontes. PostgreSQL 16.16 e migração inicial agora executados via Compose em 18/11/2026; reinício/persistência, permissões e testes reais verificados. API e coleta ainda pendentes. Ver docs/banco-de-dados.md.

## Referências oficiais

- [Docker Windows](https://docs.docker.com/desktop/setup/install/windows-install/).
- [Docker WSL 2](https://docs.docker.com/desktop/features/wsl/).
- [Microsoft WSL](https://learn.microsoft.com/en-us/windows/wsl/install).

Requisitos e políticas de suporte são definidos pelos fornecedores; versões acima representam a instalação efetivamente verificada nesta máquina.
