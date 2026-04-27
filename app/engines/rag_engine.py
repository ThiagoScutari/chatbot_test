"""RAGEngine — Camada 3 da arquitetura de 3 camadas.

Busca semântica sobre a base de conhecimento da Camisart usando pgvector.
Responde perguntas técnicas sobre produtos, tecidos e personalizações
com informação fundamentada — sem alucinação.

Contrato arquitetural (§2.1 do spec):
- Sem conhecimento de canais
- Interface: query(text) → RAGResult com chunks relevantes
- Degradação graciosa: sem OPENAI_API_KEY, retorna resultado vazio
"""
from __future__ import annotations

import json
import logging
import re
import uuid

from pydantic import BaseModel
from sqlalchemy import text

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 800


class RAGResult(BaseModel):
    chunks: list[str]
    sources: list[str]
    query: str
    top_k: int


class RAGEngine:
    def __init__(
        self,
        db_session_factory,
        openai_client,
        config: dict | None = None,
    ) -> None:
        self._db_factory = db_session_factory
        self._client = openai_client
        self._config = config or {
            "model": "text-embedding-3-small",
            "top_k": 3,
            "threshold": 0.65,
            "max_tokens_response": 400,
        }

    async def query(
        self,
        query_text: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> RAGResult:
        """
        Busca chunks mais relevantes para query_text.
        Retorna RAGResult com lista vazia se nada encontrado ou em caso de erro.
        """
        k = top_k or self._config.get("top_k", 3)
        t = threshold or self._config.get("threshold", 0.65)

        try:
            embedding = await self._embed(query_text)
            chunks, sources = self._similarity_search(embedding, k, t)
            return RAGResult(
                chunks=chunks,
                sources=sources,
                query=query_text,
                top_k=len(chunks),
            )
        except Exception as exc:
            logger.error("RAGEngine.query erro: %s", exc)
            return RAGResult(chunks=[], sources=[], query=query_text, top_k=0)

    async def index_document(
        self,
        source: str,
        chunks: list[dict],
    ) -> int:
        """
        Indexa chunks de um documento no pgvector.
        chunks: [{"chunk_id": str, "content": str, "metadata": dict}]
        Retorna número de chunks inseridos/atualizados.
        """
        indexed = 0
        with self._db_factory() as db:
            for chunk in chunks:
                try:
                    embedding = await self._embed(chunk["content"])
                    emb_str = "[" + ",".join(str(x) for x in embedding) + "]"
                    db.execute(text("""
                        INSERT INTO knowledge_chunks
                            (id, source, chunk_id, content, embedding, metadata)
                        VALUES
                            (:id, :source, :chunk_id, :content,
                             CAST(:embedding AS vector), CAST(:metadata AS jsonb))
                        ON CONFLICT (source, chunk_id)
                        DO UPDATE SET
                            content   = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            metadata  = EXCLUDED.metadata,
                            updated_at = NOW()
                    """), {
                        "id": str(uuid.uuid4()),
                        "source": source,
                        "chunk_id": chunk["chunk_id"],
                        "content": chunk["content"],
                        "embedding": emb_str,
                        "metadata": json.dumps(chunk.get("metadata", {})),
                    })
                    indexed += 1
                except Exception as exc:
                    logger.error(
                        "Erro ao indexar chunk '%s' de '%s': %s",
                        chunk.get("chunk_id"), source, exc,
                    )
            db.commit()
        return indexed

    async def count_chunks(self) -> int:
        """Retorna total de chunks indexados."""
        with self._db_factory() as db:
            result = db.execute(
                text("SELECT COUNT(*) FROM knowledge_chunks")
            ).scalar()
        return result or 0

    async def clear_source(self, source: str) -> int:
        """Remove todos os chunks de uma fonte. Retorna número removido."""
        with self._db_factory() as db:
            result = db.execute(
                text("DELETE FROM knowledge_chunks WHERE source = :source"),
                {"source": source},
            )
            db.commit()
        return result.rowcount

    def _similarity_search(
        self,
        embedding: list[float],
        top_k: int,
        threshold: float,
    ) -> tuple[list[str], list[str]]:
        with self._db_factory() as db:
            rows = db.execute(text("""
                SELECT content, chunk_id,
                       1 - (embedding <=> CAST(:emb AS vector)) AS similarity
                FROM knowledge_chunks
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> CAST(:emb AS vector)) >= :threshold
                ORDER BY similarity DESC
                LIMIT :top_k
            """), {
                "emb": str(embedding),
                "threshold": threshold,
                "top_k": top_k,
            }).fetchall()
        chunks = [r.content for r in rows]
        sources = [r.chunk_id for r in rows]
        return chunks, sources

    async def _embed(self, text_input: str) -> list[float]:
        """Gera embedding via OpenAI text-embedding-3-small."""
        response = await self._client.embeddings.create(
            model=self._config.get("model", "text-embedding-3-small"),
            input=text_input[:8000],
        )
        return response.data[0].embedding


# ── Chunker ───────────────────────────────────────────────────────────────────

def chunk_markdown(markdown_text: str, source: str) -> list[dict]:
    """
    Divide markdown em chunks semânticos por seção (##).
    Seções longas são subdivididas por parágrafo.
    """
    chunks = []
    current_title = "intro"
    current_content = ""
    section_idx = 0

    for line in markdown_text.split("\n"):
        if line.startswith("## "):
            if current_content.strip():
                chunks.extend(
                    _split_section(
                        current_title, current_content,
                        section_idx, source,
                    )
                )
            current_title = line.lstrip("# ").strip()
            current_content = ""
            section_idx += 1
        else:
            current_content += line + "\n"

    if current_content.strip():
        chunks.extend(
            _split_section(current_title, current_content, section_idx, source)
        )

    return chunks


def chunk_products_json(products_json: dict, source: str) -> list[dict]:
    """
    Converte products.json em chunks — um por produto e um por serviço.
    Usa o campo rag_texto como conteúdo principal do chunk.
    """
    chunks = []
    for product in products_json.get("products", []):
        rag_text = product.get("rag_texto", "")
        if not rag_text:
            rag_text = (
                f"{product['nome']} da Camisart. "
                f"Categoria: {product.get('categoria', '')}. "
                f"Segmentos: {', '.join(product.get('segmentos', []))}."
            )
        chunks.append({
            "chunk_id": f"produto_{product['id']}",
            "content": rag_text,
            "metadata": {
                "type": "product",
                "id": product["id"],
                "nome": product["nome"],
                "categoria": product.get("categoria", ""),
            },
        })

    for service in products_json.get("servicos", []):
        rag_text = service.get("rag_texto", "")
        if rag_text:
            chunks.append({
                "chunk_id": f"servico_{service['id']}",
                "content": rag_text,
                "metadata": {
                    "type": "service",
                    "id": service["id"],
                    "nome": service["nome"],
                },
            })

    return chunks


def _split_section(
    title: str,
    content: str,
    section_idx: int,
    source: str,
) -> list[dict]:
    """Divide seção longa em sub-chunks por parágrafo."""
    full_text = f"{title}\n\n{content}".strip()

    if len(full_text) <= MAX_CHUNK_CHARS:
        return [{
            "chunk_id": f"{source}_s{section_idx:03d}",
            "content": full_text,
            "metadata": {"title": title, "section": section_idx},
        }]

    sub_chunks = []
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    buffer = f"{title}\n\n"
    sub_idx = 0

    for para in paragraphs:
        if (
            len(buffer) + len(para) > MAX_CHUNK_CHARS
            and len(buffer) > len(title) + 3
        ):
            sub_chunks.append({
                "chunk_id": f"{source}_s{section_idx:03d}_{sub_idx:02d}",
                "content": buffer.strip(),
                "metadata": {
                    "title": title, "section": section_idx, "sub": sub_idx,
                },
            })
            buffer = f"{title} (cont.)\n\n{para}\n\n"
            sub_idx += 1
        else:
            buffer += para + "\n\n"

    if buffer.strip():
        sub_chunks.append({
            "chunk_id": f"{source}_s{section_idx:03d}_{sub_idx:02d}",
            "content": buffer.strip(),
            "metadata": {"title": title, "section": section_idx, "sub": sub_idx},
        })

    return sub_chunks


_PRODUCT_QUESTION_KEYWORDS = [
    "tecido", "material", "composição", "gramatura",
    "aguenta", "resiste", "lavar", "lavagem",
    "diferença", "melhor para", "indicado para",
    "serve para", "funciona para", "como é",
    "sublimação", "bordado funciona",
    "qual tecido", "que tecido", "aceita sublimação",
    "aceita bordado", "jaleco", "uniforme industrial",
]

# Padrões regex para perguntas técnicas ambíguas que substring não pega.
# Cobrem comparação de produto, capacidade de produção, uso específico
# e tipos de tecido. Adicionados em [fix-B] após gap medido em evaluate.py.
_PRODUCT_QUESTION_PATTERNS = [
    # GROUP 1 — Comparação/diferença de produto
    r"\bdiferença\b.{0,30}\b(jaleco|polo|camisa|camiseta|tecido|modelo)\b",
    r"\b(jaleco|polo|camisa|camiseta|tecido|modelo)\b.{0,30}\bdiferença\b",
    r"\bmais (adequado|indicado|recomendado)\b",
    r"\bmelhor (tecido|material|modelo|opção)\b",
    r"\bcompatível\b.{0,30}\b(sublimação|bordado|serigrafia)\b",
    # GROUP 2 — Experiência/capacidade de produção
    r"\bvocês (têm|fazem|produzem|trabalham)\b",
    r"\bfazem\b.{0,20}\b(avental|uniforme|jaleco|camiseta|polo|boné)\b",
    r"\bexperiência\b.{0,30}\b(uniforme|jaleco|hospital|saúde|empresa)\b",
    r"\batendem\b.{0,20}\b(hospital|clínica|escola|empresa|indústria)\b",
    # GROUP 3 — Uso específico/ambiente
    r"\b(hospital|cirúrg|clínica|laboratório)\b.{0,30}\b(jaleco|uniforme|tecido)\b",
    r"\b(jaleco|uniforme|tecido)\b.{0,30}\b(hospital|cirúrg|clínica|laboratório)\b",
    r"\blavagem\b.{0,20}\b(frequente|química|alvejante|hospital)\b",
    r"\buso\b.{0,20}\b(industrial|hospitalar|escolar|corporativo)\b",
    # GROUP 4 — Tipo de tecido/material
    r"\bque tipo\b.{0,20}\b(tecido|material|malha|tecidos)\b",
    r"\b(malha|piquet|gabardine|brim|oxford|pv|viscose)\b",
    r"\bcomposição\b.{0,20}\b(tecido|malha|material)\b",
]

_PRODUCT_QUESTION_REGEX = [
    re.compile(p, re.IGNORECASE) for p in _PRODUCT_QUESTION_PATTERNS
]


def is_product_question(text: str) -> bool:
    """Heurística: mensagem parece ser pergunta técnica sobre produto."""
    text_lower = text.lower()
    if any(kw in text_lower for kw in _PRODUCT_QUESTION_KEYWORDS):
        return True
    return any(pat.search(text_lower) for pat in _PRODUCT_QUESTION_REGEX)
