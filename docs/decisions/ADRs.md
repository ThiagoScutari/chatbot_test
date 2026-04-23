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

---

## ADR-002: pgvector como Vector Store da Fase 3

**Data:** 2026-04-23
**Status:** Aceito
**Decidido por:** Thiago Scutari

### Contexto
A Fase 3 requer vector store para busca semântica sobre o catálogo da Camisart
(Camada 3 — RAGEngine). Chunks da base de conhecimento são indexados em vetores
de embedding e consultados por similaridade cosine quando FAQ (Camada 1) e
LLMRouter (Camada 2) não resolvem a mensagem.

### Opções consideradas

| Opção | Infra adicional | Limite dimensões | Latência |
|-------|-----------------|------------------|----------|
| **pgvector** | Nenhuma (usa Postgres existente) | 2.000 (HNSW) | ~2ms |
| ChromaDB | Servidor Python separado | Sem limite | ~ms |
| Qdrant | Servidor Rust separado | Sem limite | <10ms |

### Decisão
**pgvector** — catálogo da Camisart tem ~50 chunks (bem abaixo do limite de
2.000 dimensões do índice HNSW). Zero infra adicional, mesmo banco já
provisionado, custo operacional zero. Migrar para Qdrant se catálogo crescer
além de 5.000 chunks.

### Embedding model
**text-embedding-3-small** (OpenAI) — 1536 dimensões, US$ 0,02 por 1M tokens.
Custo de indexação inicial do catálogo: < R$ 0,01.

### Consequências
- `OPENAI_API_KEY` necessária em produção para gerar embeddings
- Bot funciona sem a chave (degradação graciosa — apenas Camadas 1 e 2)
- Extensão `vector` deve estar habilitada no PostgreSQL
- Reavaliar migração para Qdrant quando catálogo passar de 5.000 chunks
