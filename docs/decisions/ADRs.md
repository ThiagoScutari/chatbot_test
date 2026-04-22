# ADRs — Camisart AI

## ADR-001: Claude Haiku como LLM Router da Fase 2

**Data:** 2026-04-22
**Status:** Aceito
**Decidido por:** Thiago Scutari

### Contexto
A Fase 2 requer um classificador de intenções para mensagens que o FAQEngine
(regex) não resolve. Três opções foram avaliadas.

### Opções consideradas

| Opção | Custo/mês (100 fallbacks/dia) | Qualidade PT-BR | Infra adicional |
|-------|-------------------------------|-----------------|-----------------|
| **Claude Haiku 4.5** | ~R$ 15 | Excelente (nativo) | Nenhuma |
| GPT-4o-mini | ~R$ 11 | Boa | Nenhuma |
| Rasa NLU (self-hosted) | R$ 0 | Requer dados de treino | 2GB RAM VPS |

### Decisão
**Claude Haiku 4.5** pela combinação de qualidade nativa em português,
custo marginal baixo (fallbacks são minoria das mensagens) e zero infra adicional.
Rasa NLU exige dados de treino que só existirão após meses em produção.

### Consequências
- `ANTHROPIC_API_KEY` necessária em produção
- Bot funciona sem a chave (degradação graciosa para Camada 1 apenas)
- Reavaliar para Rasa NLU quando houver 3+ meses de logs reais
