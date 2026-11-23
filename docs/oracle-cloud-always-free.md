# Oracle Cloud Always Free: criação do servidor

Consulta das fontes oficiais em **23/11/2026**. Este é um roteiro para o responsável
executar no console; nenhuma conta ou infraestrutura foi criada. A hospedagem do
projeto ainda não foi testada. Valores e elegibilidade devem ser reconferidos na conta.

## Configuração proposta para este projeto

Uma VM Linux ARM para PostgreSQL, API, processamento e orquestração. Proposta inicial:

| Campo | Seleção |
|---|---|
| Nome | `servidor-pipeline-etl` |
| Imagem | Ubuntu Server 24.04 LTS ARM64, imagem oficial elegível |
| Shape | `VM.Standard.A1.Flex` |
| Recursos | 2 OCPUs e 12 GB RAM, se dentro da franquia exibida na conta |
| Disco de inicialização | 50 GB, configuração elegível gratuita |
| Região | Região principal da conta, a *home region* |
| Acesso inicial | SSH por chave, restrito ao seu IP |

A documentação consultada informa 1.500 OCPU-horas e 9.000 GB-horas mensais para A1,
equivalentes a 2 OCPUs/12 GB em conta Always Free, e 200 GB combinados de volumes de
inicialização e blocos. A franquia é compartilhada com outros recursos da conta.
Não seguir automaticamente tutoriais antigos de 4 OCPUs/24 GB.
[Franquias oficiais](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Esta é uma estimativa de adequação ao nosso projeto, não um benchmark. Uma VM de
1 GB seria bastante restrita para toda a composição M2. Limites de containers,
retenção de métricas/logs e concorrência precisarão de dimensionamento real.

## 1. Criar a conta

1. Acesse [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) e inicie o cadastro.
2. Use dados reais e conclua a verificação. A Oracle solicita cartão elegível para
   identificação; pode haver uma reserva temporária, distinta de cobrança definitiva.
3. Escolha a região principal considerando proximidade e disponibilidade. Os recursos
   gratuitos de computação deste roteiro devem ficar nessa região.
4. Ative autenticação multifator e guarde os meios de recuperação.
5. Para a prioridade de não contratar consumo pago, mantenha a conta gratuita;
   não faça upgrade para Pay As You Go durante este roteiro.

O teste com créditos tem prazo e não equivale ao Always Free. Selecionar algo
coberto apenas pelos créditos não o torna gratuito depois do teste.
[Cadastro, cartão e fim do teste](https://www.oracle.com/cloud/free/faq/).

## 2. Conferir limites antes de criar recursos

No console, procure **Limits, Quotas and Usage** e confira região, limites A1 e
volumes já existentes. Crie um compartimento `pipeline-etl` para organizar os recursos.

Em **Billing & Cost Management**, acompanhe custo real e previsão. Se disponível,
configure orçamento pequeno e avisos por e-mail, por exemplo equivalente a US$ 1.
Isso é apenas aviso: orçamento **não interrompe cobrança** e não substitui a
seleção de recursos elegíveis. [Funcionamento dos orçamentos](https://docs.oracle.com/en/solutions/oci-best-practices/track-and-manage-usage-and-cost1.html).

Se o console mostrar consumo faturável, licença adicional ou elegibilidade duvidosa,
não conclua a criação. Confira a franquia aplicada e o resumo de cada componente;
um valor de tabela sem desconto também precisa ser esclarecido antes de confirmar.

## 3. Criar a rede

Em **Networking → Virtual Cloud Networks**, crie uma VCN para o compartimento:

1. Nome `rede-pipeline-etl`, faixa privada sugerida `10.20.0.0/16`.
2. Sub-rede pública `subrede-pipeline-etl`, por exemplo `10.20.1.0/24`.
3. Internet Gateway e rota `0.0.0.0/0` para esse gateway.
4. Regra de entrada TCP 22 com origem **seu IPv4 público/32**.
5. Saída que permita DNS, atualizações e HTTPS para as fontes BCB/IBGE.

Revise regras criadas pelo assistente: substitua SSH aberto a toda a internet por
seu IP. Se seu provedor mudar esse IP, atualize a regra. O assistente pode propor
outros gateways; não crie NAT Gateway ou Load Balancer para este roteiro.

Inicialmente, não abra API, PostgreSQL, Redis, Grafana, Prometheus, Prefect ou MinIO
à internet. O acesso administrativo será por túnel SSH. [Rede e primeira instância](https://docs.oracle.com/en-us/iaas/Content/Compute/tutorials/first-linux-instance/overview.htm).

## 4. Criar a VM

Em **Compute → Instances → Create instance**:

1. Selecione o compartimento, o nome e a região acima.
2. Escolha a imagem oficial Ubuntu ARM64 e o shape A1 indicado.
3. Ajuste CPU e memória dentro da franquia restante.
4. Selecione a VCN/sub-rede pública e atribua IP público para acesso SSH.
5. Gere um par de chaves SSH ou forneça sua chave pública. Salve a chave privada
   fora do repositório e mantenha cópia segura; ela não deve ser compartilhada.
6. Configure o disco em 50 GB, com desempenho elegível à gratuidade. Não selecione
   imagem de Marketplace paga nem desempenho adicional sem conferir o preço.
7. Revise o resumo: CPU, RAM, disco, região, imagem e eventuais serviços extras.
8. Crie a instância e aguarde o estado **Running**. Anote IP e OCID em registro privado.

Os nomes dos menus podem mudar. Se ocorrer falta de capacidade, tente outro domínio
de disponibilidade elegível da mesma região, se houver, ou aguarde. Não troque por
um shape pago para contornar a indisponibilidade. [Criação de instância](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/launchinginstance.htm).

## 5. Entrar pelo Windows e verificar o servidor

No PowerShell, substitua o caminho e `IP_PUBLICO` pelos dados reais:

```powershell
ssh -i "C:\caminho\chave-pipeline.key" ubuntu@IP_PUBLICO
```

Confira a identidade do servidor antes de aceitar sua chave de host. Para imagens
Ubuntu o usuário é `ubuntu`; imagens Oracle Linux usam `opc`.
[Acesso SSH oficial](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/connect-to-linux-instance.htm).

Dentro da VM, os comandos abaixo verificam arquitetura e recursos e instalam
atualizações. São instruções para execução futura, não verificações já realizadas:

```bash
uname -m
free -h
df -h /
sudo apt update
sudo apt upgrade -y
```

No A1, espere `aarch64`. Se uma atualização solicitar reinício, reinicie e teste
novamente o SSH. Não desative o firewall do sistema para resolver conectividade;
confira separadamente as regras OCI e as regras do Linux, preservando o acesso SSH.

## 6. O que falta para hospedar a pipeline nessa VM

O servidor criado não significa que a pipeline esteja implantada. A migração terá
uma verificação própria:

1. Instalar Docker Engine e o plugin Compose para Ubuntu ARM64; Docker Desktop
   não é necessário no servidor.
2. Conferir suporte `linux/arm64` nos manifests das imagens fixadas por digest e
   nas dependências. Fazer build e smoke tests reais; não copiar `.venv` do Windows.
3. Transferir código de forma controlada e preparar credenciais novas na VM,
   separadas das locais. Manter banco, cache e painéis em rede privada/loopback.
4. Restaurar backup e transferir bronze com verificação de integridade. Não manter
   a única cópia dentro da mesma VM ou no mesmo disco.
5. Adaptar servidor/worker Prefect para serviços Linux com reinício automático.
   O Agendador do Windows atual não opera na VM. Impedir duas agendas concorrentes
   durante a mudança: somente um ambiente deve ficar responsável pela coleta.
6. Configurar retenção de logs/métricas e medir RAM, disco e duração dos processos.
7. Verificar ETL, API, reinício, restauração e replay antes de anunciar a hospedagem.
8. Para acesso público posterior, configurar HTTPS, proxy e limites; abrir somente
   as portas públicas necessárias. Não publicar consoles administrativos.

## 7. Ociosidade: o que é possível fazer

**Não existe garantia de manter a VM gratuita sem recuperação por ociosidade.**
A Oracle pode recuperar instâncias cujo uso em sete dias satisfaça simultaneamente:

- CPU no percentil 95 abaixo de 20%;
- rede abaixo de 20%;
- memória abaixo de 20%, este último critério somente para A1.

Isso não significa que sete dias sem login sejam o único critério. SSH, ping,
reinício ou uma coleta diária curta não garantem permanência.
[Política de ociosidade](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

Para operar de modo sustentável:

1. Execute o trabalho real do projeto: agendas necessárias, API e observabilidade.
   Não aumente consultas aos órgãos ou execute reconciliações redundantes só para
   consumir recursos. Uso legítimo pode continuar abaixo dos limiares.
2. Habilite e confira o plugin **Compute Instance Monitoring** do Oracle Cloud Agent.
   Acompanhe CPU, rede e RAM no console; instalar o agente não impede recuperação.
   [Habilitar monitoramento](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/enablingmonitoring.htm).
3. Dimensione a VM para o trabalho medido. Não reserve RAM ou mantenha CPU ocupada
   artificialmente para alterar métricas.
4. Acompanhe avisos da Oracle e use sua conta regularmente. A FAQ também trata
   abandono da conta após 30 dias ou mais de inatividade, condição distinta da VM.
   [Regras da conta](https://www.oracle.com/cloud/free/faq/).
5. Mantenha backup externo recente e um procedimento reproduzível para recriação.
   Confira quotas/custos de qualquer armazenamento ou backup adicional antes de usá-lo.

Não recomendamos scripts de carga artificial ou tráfego falso. A documentação
consultada também não fornece garantia de isenção por ociosidade após upgrade pago;
essa mudança não é parte deste roteiro de orçamento zero.

**Decisão prática:** Always Free é uma opção para nosso portfólio se aceitarmos
possível interrupção e disponibilidade limitada de capacidade. Se a exigência for
disponibilidade contínua garantida, a gratuidade não oferece essa garantia.

## Critério de conclusão deste roteiro

Servidor elegível criado, SSH verificado, acesso restrito, métricas visíveis e
franquias/custos revisados no console. A implantação M3 só será declarada após seus
testes próprios. Nenhuma destas verificações na nuvem foi executada nesta entrega.
