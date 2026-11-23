# Validação BCB, quarentena e auditoria

A etapa verifica o bronze imutável e registra qualidade no PostgreSQL. SUCESSO significa aprovação do contrato nesta etapa; não significa carga econômica, calendário homologado ou API disponível. Não há escrita em core.fato_serie nem avanço de watermark.

## Executar localmente

Inicie o banco e aplique as migrações conforme [guia PostgreSQL](banco-de-dados.md). No diretório do projeto:

```powershell
uv run --frozen pipeline-etl validar bcb --manifesto dados/bronze/bcb/432/2026-11-18/f68045ff-e6c2-4622-9678-c98dc1df4287/manifest.json --credenciais-locais .env.banco
uv run --frozen pipeline-etl coletar bcb --serie 432 --inicio 2020-01-02 --fim 2020-01-06 --validar --credenciais-locais .env.banco
```

O primeiro comando usa arquivos existentes, sem HTTP. O segundo consulta o BCB, salva bronze e valida. Sem --validar, coletar mantém somente a coleta bruta, sem exigir banco. O acesso ao arquivo local de credenciais é explícito: somente a senha do papel processamento é usada, na porta local 55432. Como alternativa, configure URL_BANCO_PROCESSAMENTO; não combine as duas origens. Nunca forneça a senha na linha de comando.

A saída JSON apresenta execução, situação, contagens e avisos. Retorno 0 indica SUCESSO; retorno 1 indica qualidade parcial/falha ou falha técnica; retorno 2 indica configuração inválida. PARCIAL exige tratamento e não é promovido.

## Contrato e contagens

- Envelope JSON deve ser lista não vazia, com exatamente data e valor em cada objeto. Chaves duplicadas, números JSON não finitos, alteração de esquema e duplicatas conflitantes bloqueiam a execução.
- Datas usam DD/MM/AAAA, existem no calendário, não são futuras e pertencem à janela. IPCA é normalizado ao primeiro dia do mês e novamente conferido contra a janela.
- Valores devem ser texto decimal finito compatível com NUMERIC(24,10); vírgula decimal é aceita. Dólar deve ser positivo; IPCA negativo é permitido. Conversão não usa ponto flutuante.
- Observações idênticas da mesma data são deduplicadas. Valores distintos na mesma data rejeitam todos os envolvidos e causam FALHA estrutural.
- O manifesto deve cobrir exatamente as janelas anuais, identificar série/execução corretas e referenciar arquivos dentro da raiz. SHA-256 e tamanho são conferidos antes do parse.
- Gzip/deflate são descompactados com limite de saída 10 MiB; conteúdo truncado, concatenado ou excessivo é rejeitado. Metadados/manifestos têm limite 1 MiB. Nenhum arquivo bronze é modificado.

As contagens conservam lidas = validas + rejeitadas + duplicadas + nao_processadas. Erros de envelope usam posição 0 e não inventam linhas rejeitadas; posições de registros começam em 1. Desvio de esquema deixa as demais linhas como não processadas.

Sem erro estrutural, cada artefato e a execução agregada usam: nenhuma rejeição SUCESSO; >0% até 5% PARCIAL; >5% FALHA. A execução calcula o percentual sobre todas as linhas do manifesto; uma janela pode ter FALHA por percentual e o agregado ser PARCIAL. Qualquer erro estrutural prevalece como FALHA global. Ambos bloqueiam promoção. Resposta vazia falha conservadoramente até homologar calendário.

Avisos de volumetria comparam a mesma série/janela com a última execução bem-sucedida: variação maior que 20% gera aviso. Frescor só é avaliado para janelas que terminam perto da data atual, com tolerância 4 dias para séries diárias e 45 dias para IPCA; não substitui calendário oficial. Histórico antigo não é comparado ao presente como se fosse carga recente.

## Auditoria e recuperação

A revisão0002 acrescenta ops.etapa, ops.artefato, ops.quarentena, contagens e versões em ops.execucao. A revisão0001 é preservada. Cada revalidação gera nova execução e novos registros SQL, mantendo a referência ao UUID do artefato e da coleta original. Na coleta com validação, o início SQL é confirmado antes do primeiro HTTP; falha de banco impede a consulta.

Etapas, artefatos, rejeições e conclusão da execução são persistidos na mesma transação. Falha técnica reverte esse conjunto e tenta finalizar a execução como FALHA em nova transação. Se o banco continuar indisponível, o início pode permanecer EM_EXECUCAO e requerer reconciliação operacional; não se anuncia SUCESSO. Reusar uma execução finalizada é recusado sem alterar seu histórico.

A quarentena guarda motivo específico e representação JSON escapada em registro_original.json_escapado. Isso preserva NUL e surrogates que o PostgreSQL não aceita diretamente em JSONB. Para recuperar o objeto em Python, use json.loads(registro_original["json_escapado"]). Os bytes exatos continuam no bronze, com checksum e referência de origem. Não publique rejeições ou credenciais pela futura API; api_leitura não recebe privilégios sobre essas tabelas.

## Evidências locais — 18/11/2026

Backup anterior à migração: backups/etl_20261118_012407.dump,12646bytes, catálogo pg_restore --list legível. O teste verifica o catálogo; restauração completa permanece uma entrega posterior.

Imagem Docker construída, revisão0002 aplicada no banco etl e alembic check sem operações pendentes. O bronze oficial da série432, período02/01/2020 a06/01/2020, foi validado sem nova chamada HTTP: execução bd242e58-9544-46ef-ae8c-37e690420628, cinco linhas válidas, zero rejeitadas/duplicadas/não processadas, SUCESSO. A carga em core permanece pendente.

Verificação final:167 testes passaram, cobertura global 94,95%, qualidade 99%, contrato 100%. Ruff, mypy, bandit, auditoria de dependências e construção do pacote passaram.

Próximo passo: transformação e carga idempotente no core, preparação transacional, locks e controle incremental. M 1 ainda está em construção.

Atualização posterior: a carga BCB idempotente foi concluída e verificada com cinco fatos oficiais; o resultado acima descreve o momento da entrega de validação. Ver [carga e recuperação](carga-bcb.md) para o estado atual e as pendências.

## Conferência do frescor IPCA — 18/11/2026

Outubro/2026 é compatível com o calendário IBGE consultado; novembro está previsto para 11/12. O aviso de 45 dias foi preservado como falso positivo da heurística nesta data. Não houve mudança da validação automática nem apagamento de auditoria. Ver [fontes e avaliação](calendario-ipca.md).

## Política de frescor compartilhada com a API

A qualidade usa agora o calendário IPCA versionado e vigente com um dia completo de tolerância; fallback explícito mantém 45 dias quando necessário. Novas execuções registram política/versão e avaliação por artefato em parametros.avaliacoes_frescor. Janelas precisam conter a referência esperada e terminar perto da data atual para emitir aviso. Auditoria antiga permanece inalterada; a situação da carga continua sendo determinada pelos contratos de qualidade, e frescor é aviso operacional. Ver [calendário e testes](calendario-ipca.md).
