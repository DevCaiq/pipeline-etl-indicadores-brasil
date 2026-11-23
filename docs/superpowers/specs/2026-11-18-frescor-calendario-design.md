# Frescor IPCA por calendário

Objetivo autorizado: automatizar a conferência já homologada, evitando o falso positivo de outubro em 18/11/2026. API e auditoria usam uma função pura compartilhada. Sem HTTP no caminho de leitura/testes, sem migração, sem alterar bronze/auditoria antiga.

Abordagens: consultar IBGE por requisição cria dependência externa e viola leitura local; ampliar 45 dias apenas mascara o problema. Escolha técnica: snapshot derivado versionado no pacote, extraído dos doze registros oficiais arquivados do produto 9256, com URL, SHA-256 original, instante UTC e IDs de origem. Compatível com wheel e Docker, independente de dados/ operacional.

Decisões do implementador: validade de 30 dias corridos após a data de consulta em São Paulo (inclusive); não usar antes da consulta. Tolerância local de um dia corrido completo após a data de divulgação, sem assumir hora/fuso do campo externo e sem afirmar SLA BCB. Referência passa a ser exigida quando hoje > divulgação + 1 dia. Última referência esperada é a maior vencida; defasado indica referência anterior. Datas futuras ou IPCA fora do primeiro dia do mês são indeterminadas. Sem referência, estado indeterminado.

Ausência, corrupção, consulta futura, expiração, ausência de referência vencida ou falta de cobertura do calendário levam à heurística existente (45 dias IPCA, 4 demais), com motivo explícito. Snapshot exige ano completo, ordem mensal e de divulgações, produto 9256, versão e hash válidos. API conserva campos e acrescenta motivo, referência esperada, data limite e versão; calendario_homologado só é true quando a regra de frescor usa o snapshot, cobertura histórica continua não homologada. Avaliação em lote anual só compara frescor se a janela inclui a referência esperada; janela encerrada longe de hoje não é considerada coleta recente.

Auditoria registra a política e a versão nos detalhes de novas etapas, sem reescrever anteriores. Atualização do snapshot exige nova coleta oficial arquivada, validação e revisão; snapshot expirado degrada para heurística, sem renovação automática silenciosa. Sem automação agendada nesta entrega.
