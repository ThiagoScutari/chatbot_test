# PRD — Sprint 07: RAG sobre Catálogo (Fase 3)
**Projeto:** Camisart AI  
**Branch:** `sprint/07-rag`  
**Status:** Aprovação Pendente  
**Origem:** Spec §9 Fase 3 + documentação `docs/camisart_knowledge_base_v2.md`  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S07-01 | `migrations/` | pgvector — extensão + tabela `knowledge_chunks` | 🔴 |
| S07-02 | `knowledge/` | `products.json` expandido + `camisart_knowledge_base.md` no app | 🔴 |
| S07-03 | `engines/` | `RAGEngine` — indexação e busca semântica | 🔴 |
| S07-04 | `scripts/` | `scripts/index_knowledge.py` — indexa docs no pgvector | 🔴 |
| S07-05 | `pipeline/` | Pipeline integra Camada 3 após LLMRouter | 🔴 |
| S07-06 | `api/` | `GET /admin/rag/status` — chunks indexados e estatísticas | 🟡 |
| S07-07 | `tests/` | Suite completa com mocks OpenAI — zero chamadas reais | 🔴 |
| S07-08 | `docs/` | ADR-002: pgvector como vector store da Fase 3 | 🟢 |

---

## Objetivo do Sprint

Implementar a **Camada 3** da arquitetura de 3 camadas. O `RAGEngine` indexa a base de conhecimento da Camisart em vetores semânticos e, quando a Camada 2 (LLMRouter) tem baixa confiança ou a mensagem é uma pergunta técnica complexa, o RAG recupera os chunks mais relevantes e o LLM gera uma resposta fundamentada no catálogo real — nunca inventada.

**Princípio fundamental:** o RAG não inventa. Toda resposta gerada pela Camada 3 é baseada exclusivamente em chunks da base de conhecimento validada. Se a informação não está no documento, o bot encaminha para o consultor.

```
Mensagem: "qual tecido é melhor para jaleco hospitalar?"
        │
        ▼
┌─────────────────┐
│  Camada 1: FAQ  │  regex → None (sem padrão específico)
└────────┬────────┘
         │ None
         ▼
┌─────────────────┐
│  Camada 2: LLM  │  classifica → confiança baixa (pergunta técnica)
└────────┬────────┘
         │ confidence < 0.60
         ▼
┌─────────────────┐
│  Camada 3: RAG  │  busca chunks sobre "jaleco + tecido + hospitalar"
│  (pgvector)     │  encontra: "Para uso hospitalar..."
└────────┬────────┘
         │ chunks relevantes
         ▼
   LLM gera resposta
   fundamentada no catálogo
   (sem alucinação)
```

---

## S07-01 — Migration: pgvector + tabela knowledge_chunks

### Dependência
```bash
pip install pgvector>=0.3
```
Adicionar ao `requirements.txt`.

### SQL

```python
# app/migrations/migrate_sprint_07.py

PGVECTOR_SQL = """
-- Habilitar extensão pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de chunks indexados
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source      TEXT NOT NULL,        -- nome do arquivo fonte
    chunk_id    TEXT NOT NULL,        -- id único dentro do fonte (ex: "produto_polo_1")
    content     TEXT NOT NULL,        -- texto do chunk
    embedding   vector(1536),         -- embedding text-embedding-3-small
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_knowledge_chunk UNIQUE (source, chunk_id)
);

-- Índice HNSW para busca aproximada eficiente
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
ON knowledge_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Índice por fonte para re-indexação parcial
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_source
ON knowledge_chunks(source);
"""
```

### Modelo SQLAlchemy

```python
# app/models/knowledge_chunk.py

import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from app.database import Base

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(256), nullable=False)
    chunk_id: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )
```

---

## S07-02 — Atualizar products.json e adicionar knowledge base ao app

### Estrutura do products.json expandido

Cada produto recebe o campo `rag_texto` — texto corrido otimizado para embedding que captura:
- Nome e categoria
- Características técnicas
- Para quem é indicado
- Casos de uso reais
- Diferenciais

```json
{
  "version": "2.0",
  "products": [
    {
      "id": "polo_piquet",
      "nome": "Camisa Polo",
      "categoria": "polo",
      "tecidos": ["piquet", "algodao", "pv", "poliester"],
      "mangas": ["curta", "longa"],
      "precos": {
        "varejo": 45.00,
        "atacado_12": 42.00,
        "observacao": "Sujeito a alteração — consultar para pedidos grandes"
      },
      "tamanhos": ["P", "M", "G", "GG"],
      "tamanhos_especiais": "G1, G2, G3 sob consulta",
      "personalizacoes": ["bordado", "serigrafia", "lisa", "colorida"],
      "pronta_entrega": true,
      "segmentos": [
        "corporativo", "saude", "educacao",
        "portaria", "jardinagem", "servicos_publicos"
      ],
      "casos_de_uso": [
        "Recepcionistas e equipe de atendimento ao cliente",
        "Profissionais de saúde em clínicas e consultórios",
        "Professores e coordenadores pedagógicos",
        "Porteiros e agentes de segurança patrimonial",
        "Equipes de campo e logística",
        "Jardineiros e trabalhadores de serviços gerais",
        "Funcionários de serviços públicos municipais e estaduais"
      ],
      "rag_texto": "Camisa polo da Camisart disponível em malha piquet, algodão, PV e poliéster, com manga curta ou manga longa. A malha piquet é a mais procurada para uniformes corporativos pelo visual elegante e durabilidade. Preço a partir de R$45 no varejo e R$42 em atacado para pedidos de 12 ou mais peças. Tamanhos P, M, G e GG, com tamanhos especiais G1, G2 e G3 sob consulta. Ideal para empresas, clínicas, escolas, porteiros e serviços públicos. A personalização mais comum é bordado do logotipo no peito esquerdo."
    },
    {
      "id": "camiseta_basica",
      "nome": "Camiseta Básica",
      "categoria": "camiseta",
      "tecidos": ["algodao", "poliester", "pv", "misto_algodao_poliester"],
      "mangas": ["curta", "longa", "regata"],
      "precos": {
        "a_partir_de": 29.00
      },
      "tamanhos": ["P", "M", "G", "GG"],
      "personalizacoes": ["bordado", "serigrafia", "sublimacao_pv", "sublimacao_poliester", "lisa", "colorida"],
      "pronta_entrega": true,
      "segmentos": [
        "esportes", "eventos", "igrejas", "escolas", "varejo"
      ],
      "rag_texto": "Camiseta básica da Camisart disponível em 100% algodão, 100% poliéster, PV (poliéster e viscose) e misto algodão/poliéster. Mangas curta, longa ou regata. O algodão é mais fresco e respirável, ideal para o calor de Belém. O poliéster e o PV aceitam sublimação total para estampas com foto e cores ilimitadas. Usada por times de futebol, igrejas, eventos, grupos e escolas. Pronta entrega em peças lisas e coloridas. A partir de R$29."
    },
    {
      "id": "jaleco",
      "nome": "Jaleco",
      "categoria": "jaleco",
      "modelos": ["tradicional", "premium"],
      "tecidos": {
        "tradicional": "gabardine",
        "premium": "gabardine superior"
      },
      "cortes": ["masculino", "feminino"],
      "precos": {
        "tradicional": 120.00,
        "premium": 145.00
      },
      "personalizacoes": ["bordado", "lisa"],
      "segmentos": ["saude", "educacao", "estetica"],
      "casos_de_uso": [
        "Dentistas e cirurgiões-dentistas",
        "Médicos, clínicos gerais e especialistas",
        "Oftalmologistas e dermatologistas",
        "Esteticistas e profissionais de beleza",
        "Nutricionistas e fisioterapeutas",
        "Enfermeiros e técnicos de enfermagem",
        "Professores e coordenadores",
        "Recepcionistas de clínicas e hospitais",
        "Laboratoristas"
      ],
      "rag_texto": "Jaleco da Camisart em dois modelos: tradicional em gabardine (R$120) e premium em gabardine superior com melhor toque e acabamento (R$145). Disponível em corte masculino e feminino com modelagens diferentes para melhor caimento. Muito usado por dentistas, médicos, oftalmologistas, esteticistas, professores e enfermeiros. A personalização mais comum é bordado com nome do profissional e logotipo da clínica. Para uso hospitalar com lavagens frequentes, consultar o especialista sobre o tecido mais adequado. A Camisart envia catálogo para o cliente escolher o modelo com mais detalhes de comprimento e bolsos."
    },
    {
      "id": "uniforme_industrial",
      "nome": "Uniforme Industrial",
      "categoria": "industrial",
      "tecidos": ["brim", "oxford_pesado"],
      "opcoes": ["com_fita_refletiva", "sem_fita_refletiva"],
      "precos": {"consultar": true},
      "personalizacoes": ["bordado", "serigrafia"],
      "segmentos": ["industria", "construcao_civil", "seguranca", "gas"],
      "rag_texto": "Uniforme industrial da Camisart em tecido brim ou oxford pesado, resistente a rasgos e uso intenso. Disponível com ou sem fitas refletivas para atender normas de segurança do trabalho. Muito procurado por empresas de construção civil, distribuidoras de gás, indústrias e segurança viária. Personalização com bordado ou serigrafia do logotipo e nome da empresa. Preço sob consulta conforme modelo e quantidade."
    },
    {
      "id": "uniforme_escolar",
      "nome": "Uniforme Escolar",
      "categoria": "escolar",
      "produtos_mais_usados": ["polo", "camiseta_basica", "jaleco"],
      "personalizacoes": ["bordado", "serigrafia"],
      "segmentos": ["escolas_particulares", "escolas_publicas"],
      "rag_texto": "Uniforme escolar da Camisart para escolas particulares e públicas. Os produtos mais usados são camisa polo manga curta para alunos e professores, camiseta básica algodão para educação física e jaleco para professores e laboratório. Personalização com bordado ou serigrafia do nome e logotipo da escola. Atenção: pedidos para início do ano letivo (janeiro e fevereiro) devem ser feitos com 30 dias de antecedência pela alta demanda."
    },
    {
      "id": "uniforme_domestico",
      "nome": "Uniforme Doméstico",
      "categoria": "domestico",
      "modelos": ["manga_curta", "sem_manga", "com_bolso", "sem_bolso"],
      "precos": {"unidade": 120.00},
      "personalizacoes": ["bordado", "lisa"],
      "segmentos": ["domestico"],
      "rag_texto": "Uniforme doméstico da Camisart para babás, diaristas, cuidadoras e empregadas domésticas. Disponível em modelos manga curta, sem manga, com bolso e sem bolso. Sem cor padrão definida, o cliente escolhe conforme preferência. Pode ter bordado com nome ou iniciais. Preço a partir de R$120 por unidade."
    },
    {
      "id": "boné_personalizado",
      "nome": "Boné Personalizado",
      "categoria": "acessorio",
      "modelos": ["aba_curva", "aba_reta"],
      "precos": {"a_partir_de": 35.00},
      "pedido_minimo": 12,
      "prazo_dias_uteis": 15,
      "personalizacoes": ["bordado"],
      "rag_texto": "Boné personalizado da Camisart com bordado do logotipo ou nome da empresa. Disponível em aba curva e aba reta. Pedido mínimo de 12 unidades. Preço a partir de R$35 por unidade. Prazo de 10 a 15 dias úteis após aprovação da arte. Ideal para complementar pedidos de uniforme, eventos corporativos e times esportivos."
    }
  ],
  "servicos": [
    {
      "id": "bordado",
      "nome": "Bordado",
      "pedido_minimo": 1,
      "preco_programacao": {"min": 60.00, "max": 80.00},
      "preco_por_peca_7_9cm": 4.50,
      "prazo_dias_uteis": 7,
      "formatos_aceitos": ["AI", "CDR", "PDF_vetorial", "PNG_300dpi"],
      "rag_texto": "Bordado da Camisart sem pedido mínimo — borda a partir de 1 peça. Valor de programação (digitalização da arte) de R$60 a R$80, cobrado uma única vez. Bordado de 7 a 9cm custa R$4,50 por bordado por peça. A posição mais comum é o lado esquerdo do peito. Prazo de 5 a 7 dias úteis após aprovação. Formatos aceitos: AI, CDR, PDF vetorial ou PNG em 300 DPI. Quando o cliente não tem arte, a Camisart tem designer próprio para ajudar."
    },
    {
      "id": "serigrafia",
      "nome": "Serigrafia",
      "pedido_minimo": 20,
      "preco": "consultar",
      "prazo": "consultar",
      "rag_texto": "Serigrafia da Camisart a partir de 20 peças. Ideal para estampas grandes e pedidos maiores. Valores e prazo dependem do número de cores, tamanho da estampa e quantidade — consultar com o especialista. Para pedidos menores que 20 peças, o bordado é mais indicado."
    },
    {
      "id": "sublimacao",
      "nome": "Sublimação",
      "tecidos_compativeis": ["poliester", "pv"],
      "preco": "consultar",
      "rag_texto": "Sublimação da Camisart integra a tinta ao tecido, permitindo estampas com fotos, gradientes e cores ilimitadas que não descascam. Funciona apenas em tecidos de poliéster ou PV. Não funciona em algodão. Ideal para uniformes esportivos, camisetas comemorativas e estampas all-over. Valores e prazo sob consulta com o especialista."
    }
  ]
}
```

### Copiar knowledge base para app/knowledge/

```bash
cp docs/camisart_knowledge_base_v2.md app/knowledge/camisart_knowledge_base.md
```

Atualizar `app/config.py`:
```python
KNOWLEDGE_BASE_PATH: Path = Path("app/knowledge/camisart_knowledge_base.md")
OPENAI_API_KEY: str = ""  # para embeddings text-embedding-3-small
```

---

## S07-03 — RAGEngine

### Interface

```python
# app/engines/rag_engine.py

class RAGResult(BaseModel):
    chunks: list[str]          # conteúdo dos chunks recuperados
    sources: list[str]         # ids das fontes
    query: str                 # query original
    top_k: int                 # número de chunks recuperados

class RAGEngine:
    """
    Busca semântica sobre a base de conhecimento da Camisart.

    Uso:
        engine = RAGEngine(db, openai_client)
        result = await engine.query("qual tecido para jaleco hospitalar?", top_k=3)
        # result.chunks = ["Para uso hospitalar com lavagens frequentes...", ...]
    """

    def __init__(
        self,
        db_session_factory,
        openai_client,
        config: dict | None = None,
    ) -> None:
        ...

    async def query(
        self,
        text: str,
        top_k: int = 3,
        threshold: float = 0.70,
    ) -> RAGResult:
        """
        Busca os chunks mais relevantes para o texto dado.
        Retorna apenas chunks com similaridade >= threshold.
        """
        ...

    async def index_document(
        self,
        source: str,
        chunks: list[dict],  # [{"chunk_id": str, "content": str, "metadata": dict}]
    ) -> int:
        """Indexa chunks de um documento. Retorna número de chunks inseridos."""
        ...
```

### Estratégia de chunking para a knowledge base

A base de conhecimento é dividida em chunks por seção — cada produto e cada tipo de personalização vira um chunk independente, mais os guias técnicos como chunks menores.

```python
# app/engines/rag_engine.py — chunker

def chunk_knowledge_base(markdown_text: str) -> list[dict]:
    """
    Divide a knowledge base em chunks semânticos.
    Cada seção de nível ## vira um chunk.
    Seções longas são subdivididas por parágrafo.
    """
    MAX_CHUNK_CHARS = 800  # ~200 tokens — adequado para text-embedding-3-small

    chunks = []
    current_section = ""
    current_title = ""
    chunk_counter = 0

    for line in markdown_text.split("\n"):
        if line.startswith("## "):
            # Nova seção — salva a anterior
            if current_section.strip():
                chunks.extend(
                    _split_section(current_title, current_section, chunk_counter, MAX_CHUNK_CHARS)
                )
            current_title = line.replace("## ", "").strip()
            current_section = ""
            chunk_counter += 1
        else:
            current_section += line + "\n"

    # Última seção
    if current_section.strip():
        chunks.extend(
            _split_section(current_title, current_section, chunk_counter, MAX_CHUNK_CHARS)
        )

    return chunks
```

### Busca por similaridade cosine

```python
# app/engines/rag_engine.py — query

async def query(self, text: str, top_k: int = 3, threshold: float = 0.70) -> RAGResult:
    # 1. Gerar embedding da query
    embedding = await self._embed(text)

    # 2. Busca por similaridade no pgvector
    from sqlalchemy import text as sql_text
    with self._db_session_factory() as db:
        results = db.execute(sql_text("""
            SELECT content, source, chunk_id,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM knowledge_chunks
            WHERE 1 - (embedding <=> :embedding::vector) >= :threshold
            ORDER BY similarity DESC
            LIMIT :top_k
        """), {
            "embedding": str(embedding),
            "threshold": threshold,
            "top_k": top_k,
        }).fetchall()

    return RAGResult(
        chunks=[r.content for r in results],
        sources=[r.chunk_id for r in results],
        query=text,
        top_k=len(results),
    )
```

---

## S07-04 — Script de indexação

```python
# scripts/index_knowledge.py
"""
Indexa a base de conhecimento da Camisart no pgvector.

Uso:
    python scripts/index_knowledge.py              # indexa tudo
    python scripts/index_knowledge.py --clear      # limpa e re-indexa
    python scripts/index_knowledge.py --status     # mostra chunks indexados

Quando re-indexar:
    - Após atualizar camisart_knowledge_base.md
    - Após atualizar products.json
    - Após adicionar novos produtos ao catálogo
"""
```

O script lê `app/knowledge/camisart_knowledge_base.md` e `app/knowledge/products.json`, divide em chunks, gera embeddings via OpenAI `text-embedding-3-small` e insere em `knowledge_chunks`.

**Custo de indexação:** ~50 chunks × 200 tokens = 10.000 tokens = **$0.0002** (menos de 1 centavo).

---

## S07-05 — Integrar RAGEngine no Pipeline

O RAGEngine entra quando a Camada 2 tem confiança baixa **E** a mensagem parece uma pergunta técnica ou de produto.

```python
# app/pipeline/message_pipeline.py

# Depois da Camada 2 com confiança baixa:
if (self._rag_engine
        and classification.confidence < thresholds["medium"]
        and _is_product_question(inbound.content)):

    rag_result = await self._rag_engine.query(inbound.content, top_k=3)

    if rag_result.chunks:
        # Gerar resposta com contexto do RAG
        response_text = await self._generate_rag_response(
            question=inbound.content,
            chunks=rag_result.chunks,
            session=session,
        )
        result = HandleResult(
            response=FAQResponse(type="text", body=response_text),
            next_state=session.current_state,
            matched_intent_id="rag_response",
        )
    else:
        # RAG não encontrou nada relevante → encaminha para humano
        result = _fallback_to_human(session)
```

### Prompt para geração com contexto RAG

```python
RAG_GENERATION_PROMPT = """Você é o assistente da Camisart Belém, uma loja de uniformes.
Responda a pergunta do cliente usando APENAS as informações abaixo.
Se a informação não estiver no contexto, diga que um consultor pode ajudar melhor.

Contexto da Camisart:
{chunks}

Pergunta do cliente: {question}

Responda de forma direta, amigável e em português. Máximo 3 parágrafos curtos."""
```

### Gatilho para perguntas técnicas

```python
def _is_product_question(text: str) -> bool:
    """Heurística: mensagem parece ser pergunta técnica sobre produto."""
    keywords = [
        "tecido", "material", "composição", "gramatura",
        "aguenta", "resiste", "lavar", "lavagem",
        "diferença", "melhor para", "indicado para",
        "serve para", "funciona para", "qual", "como é",
        "sublimação", "bordado", "serigrafia",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)
```

---

## S07-06 — Endpoint admin RAG status

```python
@router.get("/rag/status", dependencies=[Depends(verify_admin_token)])
async def rag_status(request: Request) -> StandardResponse:
    """Retorna estatísticas do RAG: chunks indexados, fontes, última indexação."""
```

---

## S07-07 — Testes (zero chamadas reais à OpenAI)

**Regra absoluta:** nenhum teste chama a API OpenAI de verdade.

```python
# tests/test_rag_engine.py

# Mock de embedding — retorna vetor fixo de 1536 dimensões
@pytest.fixture
def mock_openai_client():
    import numpy as np
    client = MagicMock()
    client.embeddings.create = AsyncMock(return_value=MagicMock(
        data=[MagicMock(embedding=np.random.rand(1536).tolist())]
    ))
    return client

# Testes a cobrir:
# 1. chunk_knowledge_base() divide corretamente por seção ##
# 2. RAGEngine.index_document() insere chunks no banco
# 3. RAGEngine.query() retorna chunks relevantes (com embedding mockado)
# 4. RAGEngine.query() retorna lista vazia quando threshold não atingido
# 5. Pipeline chama RAG quando LLM tem confiança baixa E é pergunta de produto
# 6. Pipeline NÃO chama RAG quando FAQ resolve (Camada 1)
# 7. Pipeline NÃO chama RAG quando LLM tem alta confiança (Camada 2)
# 8. _is_product_question() retorna True para perguntas técnicas
# 9. _is_product_question() retorna False para saudações
# 10. Resposta RAG não alucia — usa apenas conteúdo dos chunks mockados
# 11. Sem chunks relevantes → encaminha para humano
# 12. RAGEngine não importado em adapters (teste AST)
```

---

## S07-08 — ADR-002: pgvector como vector store

Criar em `docs/decisions/ADRs.md`:

```markdown
## ADR-002: pgvector como Vector Store da Fase 3

**Data:** 2026-04-23
**Status:** Aceito

### Contexto
A Fase 3 requer vector store para busca semântica sobre o catálogo.

### Opções consideradas

| Opção | Infra adicional | Limite dimensões | Latência |
|-------|----------------|-----------------|----------|
| **pgvector** | Nenhuma (usa Postgres existente) | 2.000 (HNSW) | ~2ms |
| ChromaDB | Servidor Python separado | Sem limite | ~ms |
| Qdrant | Servidor Rust separado | Sem limite | <10ms |

### Decisão
**pgvector** — catálogo da Camisart tem ~50 chunks (bem abaixo do limite).
Zero infra adicional, mesmo banco já provisionado, custo zero.
Migrar para Qdrant se catálogo crescer além de 5.000 chunks.

### Embedding model
**text-embedding-3-small** (OpenAI) — 1536 dimensões, $0.02/1M tokens.
Custo de indexação inicial: < R$ 0,01.
```

---

## Variáveis de Ambiente

Acrescentar ao `.env.example`:

```env
# RAG — Fase 3
OPENAI_API_KEY=           # para embeddings text-embedding-3-small
KNOWLEDGE_BASE_PATH=app/knowledge/camisart_knowledge_base.md
```

---

## Ordem de Execução

```
S07-08 → S07-01 → S07-02 → S07-03 → S07-04 → S07-07 → S07-05 → S07-06
```

ADR primeiro — decisão documentada.  
Migration antes do model — tabela precisa existir.  
Products.json e knowledge base antes do engine — dados antes do código.  
RAGEngine antes do script — indexação usa o engine.  
Testes acompanham cada item.  
Pipeline integra no final — quando tudo está validado.  
Admin endpoint fecha o sprint.

---

## Commits Atômicos Esperados

```
docs(adr): ADR-002 pgvector como vector store Fase 3 [S07-08]
feat(migrations): pgvector + tabela knowledge_chunks + índice HNSW [S07-01]
feat(knowledge): products.json v2 expandido + camisart_knowledge_base.md [S07-02]
feat(engine): RAGEngine busca semântica com pgvector [S07-03]
feat(scripts): index_knowledge.py indexa catálogo no pgvector [S07-04]
test(rag): suite completa com mocks OpenAI — zero chamadas reais [S07-07]
feat(pipeline): integra RAGEngine como Camada 3 [S07-05]
feat(api): GET /admin/rag/status estatísticas de indexação [S07-06]
```

---

## Critérios de Aceite

- [ ] Extensão pgvector habilitada no banco
- [ ] Tabela `knowledge_chunks` criada com índice HNSW
- [ ] `index_knowledge.py` indexa todos os chunks sem erro
- [ ] `RAGEngine.query("jaleco hospitalar")` retorna chunks relevantes sobre jaleco
- [ ] `RAGEngine.query("preço do bitcoin")` retorna lista vazia (threshold não atingido)
- [ ] Pipeline chama RAG apenas para perguntas técnicas com LLM confiança baixa
- [ ] Pipeline NÃO chama RAG quando FAQ ou LLM resolvem (Camadas 1 e 2)
- [ ] Resposta RAG usa apenas conteúdo dos chunks — sem alucinação
- [ ] Sem chunks relevantes → encaminha para consultor humano
- [ ] `GET /admin/rag/status` retorna número de chunks indexados
- [ ] Nenhum teste chama API OpenAI real
- [ ] `RAGEngine` não importado em adapters (teste AST)
- [ ] 0 testes falhando
- [ ] Cobertura global >= 82%
- [ ] CI verde na branch `sprint/07-rag`
- [ ] `camisart-sprint-review` aprovado antes do merge
