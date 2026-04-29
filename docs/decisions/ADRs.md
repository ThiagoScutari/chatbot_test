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

---

## ADR-003: Substituição de RAG (pgvector) por Contexto Longo

**Data:** 2026-04-24
**Status:** Aceito
**Contexto:** Sprint 08 mostrou RAG com 0.0% accuracy. Catálogo tem ~38 chunks (~6.000 tokens).

### Problema com RAG para catálogos pequenos
- Chunking fragmenta o contexto — LLM vê pedaços, não o todo
- Threshold de similaridade difícil de calibrar para domínio específico
- Pipeline complexo (embedding → pgvector → chunks → geração) sem ganho real
- Custo adicional: OpenAI API para embeddings

### Decisão
Substituir pgvector + embeddings por injeção direta do catálogo completo
no contexto do LLM quando a pergunta for técnica e as Camadas 1 e 2
não resolverem com alta confiança.

### Quando reverter para RAG
Quando o catálogo crescer além de ~200 produtos (>50.000 tokens) e o
custo de contexto por query se tornar inviável. O ADR-002 permanece
válido para essa escala futura.

### Referência
Artigo: "RAG Está Morto?" — AkitaOnRails.com (2026-04-06)

---

## ADR-002 — LLM-first Pipeline (não regex-first)

**Data:** 2026-04-29
**Status:** Aceito
**Contexto:** Sprint 11 (Flowtest) revelou que o pipeline regex-first
não sustenta conversa multi-turn natural. Taxa de fallback de 37.4%,
captura de dados incorreta, e incapacidade de extrair informações de
linguagem livre.

**Decisão:** Claude Haiku como motor principal de processamento. Toda
mensagem é processada pelo LLM com system prompt contendo catálogo,
FAQ, knowledge base e regras do funil. O regex (FAQEngine) é mantido
apenas como fallback offline.

**Trade-offs:**
- (+) Conversa natural, extração de dados de linguagem livre
- (+) Sem manutenção de regex para cada nova pergunta
- (+) Adaptação automática a sotaques e abreviações
- (-) Custo por mensagem (~$0.005 vs $0 no regex)
- (-) Latência por mensagem (~1-2s vs 0ms no regex)
- (-) Dependência de API externa (mitigado pelo fallback)

**Consequências:**
- LLMRouter (Camada 2) e ContextEngine (Camada 3) são deprecados
- FAQEngine (Camada 1) mantido apenas como fallback offline
- System prompt é a nova "base de conhecimento" — mantido em markdown
- Guardrails em código Python validam respostas pós-LLM

**Rejeitar:** Voltar para regex-first ou adicionar mais regexes.
