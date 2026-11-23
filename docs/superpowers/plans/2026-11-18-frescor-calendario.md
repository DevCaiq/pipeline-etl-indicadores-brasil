# Implementação do frescor por calendário

Spec: docs/superpowers/specs/2026-11-18-frescor-calendario-design.md. Continuação autorizada do próximo passo acordado. Português-BR, sem alterações de schema/dependências nem API externa na suíte. Repositório sem commit-base: preservar workspace atual e dados; não criar worktree vazia.

- [x] Testes falhando de regra pura: calendário real, limites divulgação/tolerância/vigência, dados ausentes/inválidos, fallback e série diária.
- [x] Extrair snapshot oficial versionável; implementar carregamento estrito e avaliação pura em processamento/frescor.py.
- [x] Integrar API e auditoria com testes de contrato, janela e rastreabilidade; manter cobertura histórica desconhecida e auditoria antiga.
- [x] Verificar suíte completa, Ruff/mypy, wheel contendo snapshot, HTTP real local sem escrita e revisão independente.
- [x] Atualizar documentação com política, operação de atualização e limites.

## Evidências e decisões

Implementação executada na continuidade autorizada, preservando código/dados existentes. Recurso final src/pipeline_etl/calendarios/ipca_2026.json: a pasta dados/ inicialmente testada era excluída pelo Git/Hatch, detectado no teste real do wheel. Recurso movido para calendarios/ e wheel reconstruído/extraído; importação do próprio wheel confirmou CALENDARIO_IBGE para outubro em 18/11. Nenhuma dependência ou migração alterada.

Testes de regra observados falhar antes da implementação (módulo ausente), e regressão de auditoria observada falhar com aviso indevido. Depois da implementação passaram. Primeira suíte: 308 aprovados/1 falhou por mock já consumido no iter_raw; mock corrigido para ByteStream sem mudar código HTTP. Suíte final: 309 aprovados em 67,11 s, cobertura 96,63%. Ruff/formatação, mypy 42 arquivos e Bandit aprovados (Bandit precisou execução fora da restrição; tentativas anteriores sem conclusão foram interrompidas).

HTTP local completo: 4323 observações e 351 agregados conferidos; origem/auditoria preservadas e servidor próprio encerrado. IPCA defasado=false, CALENDARIO_IBGE, versão ibge-ipca-20261118-19f6021aa9b7, referência esperada 2026-10-01, limite 2026-11-13. Não houve recarga/revisão de fatos ou remoção de alertas anteriores. Revisão estática independente sem achados importantes; cobertura histórica permanece não homologada.

Próximas etapas: benchmark conforme protocolo e orquestração/agendamento. Renovação do snapshot segue operação manual documentada com nova consulta oficial, nunca mera troca da data de validade.
