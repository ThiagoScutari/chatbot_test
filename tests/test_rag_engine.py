import json
import pytest
import numpy as np
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.engines.rag_engine import (
    RAGEngine, RAGResult,
    chunk_markdown, chunk_products_json, is_product_question,
    _split_section,
)

PRODUCTS_PATH = Path("app/knowledge/products.json")
KB_PATH = Path("app/knowledge/camisart_knowledge_base.md")


def make_fake_embedding() -> list[float]:
    """Embedding falso de 1536 dimensões para testes."""
    rng = np.random.default_rng(seed=42)
    return rng.random(1536).tolist()


@pytest.fixture
def mock_openai_client():
    client = MagicMock()
    client.embeddings = MagicMock()
    client.embeddings.create = AsyncMock(return_value=MagicMock(
        data=[MagicMock(embedding=make_fake_embedding())]
    ))
    return client


@pytest.fixture
def rag_engine(mock_openai_client):
    from app.database import SessionLocal
    return RAGEngine(
        db_session_factory=SessionLocal,
        openai_client=mock_openai_client,
        config={"model": "text-embedding-3-small", "top_k": 3, "threshold": 0.0},
    )


# ── Chunker tests ─────────────────────────────────────────────────────────────

def test_chunk_markdown_divide_por_secao():
    md = "# Título\n\n## Produto 1\n\nTexto do produto 1.\n\n## Produto 2\n\nTexto do produto 2.\n"
    chunks = chunk_markdown(md, "test")
    assert len(chunks) >= 2
    titles = [c["metadata"]["title"] for c in chunks]
    assert "Produto 1" in titles
    assert "Produto 2" in titles


def test_chunk_markdown_secao_longa_subdividida():
    long_section = "## Seção Longa\n\n" + ("Parágrafo longo. " * 50 + "\n\n") * 10
    chunks = chunk_markdown(long_section, "test")
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk["content"]) <= 900  # margem de segurança


def test_chunk_products_json_gera_chunk_por_produto():
    products_data = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    chunks = chunk_products_json(products_data, "products")
    product_ids = [
        c["chunk_id"] for c in chunks if c["chunk_id"].startswith("produto_")
    ]
    assert len(product_ids) == len(products_data["products"])


def test_chunk_products_json_rag_texto_presente():
    products_data = json.loads(PRODUCTS_PATH.read_text(encoding="utf-8"))
    chunks = chunk_products_json(products_data, "products")
    for chunk in chunks:
        assert len(chunk["content"]) > 20, \
            f"Chunk {chunk['chunk_id']} tem conteúdo vazio"


def test_chunk_knowledge_base_real():
    if not KB_PATH.exists():
        pytest.skip("camisart_knowledge_base.md não encontrado")
    md_text = KB_PATH.read_text(encoding="utf-8")
    chunks = chunk_markdown(md_text, "knowledge_base")
    assert len(chunks) >= 5
    contents = " ".join(c["content"] for c in chunks)
    assert "jaleco" in contents.lower()
    assert "bordado" in contents.lower()


# ── is_product_question ───────────────────────────────────────────────────────

@pytest.mark.parametrize("msg,expected", [
    ("qual tecido é melhor para jaleco hospitalar?", True),
    ("o bordado aguenta lavagem?",                   True),
    ("qual a diferença do jaleco premium?",          True),
    ("aceita sublimação no algodão?",                True),
    ("oi",                                           False),
    ("qual o preço da polo?",                        False),
    ("qual o endereço?",                             False),
    ("quero falar com atendente",                    False),
])
def test_is_product_question(msg, expected):
    assert is_product_question(msg) == expected, \
        f"'{msg}' esperava {expected}"


# ── RAGEngine unit tests (DB mockado) ─────────────────────────────────────────

async def test_query_retorna_resultado_vazio_sem_chunks(mock_openai_client):
    """Sem chunks no banco → resultado vazio, não erro."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.execute = MagicMock(
        return_value=MagicMock(fetchall=MagicMock(return_value=[]))
    )

    engine = RAGEngine(
        db_session_factory=lambda: mock_db,
        openai_client=mock_openai_client,
    )
    result = await engine.query("qual tecido para jaleco?")
    assert isinstance(result, RAGResult)
    assert result.chunks == []
    assert result.top_k == 0


async def test_query_retorna_chunks_relevantes(mock_openai_client):
    """Simula banco com chunks — retorna conteúdo correto."""
    fake_row = MagicMock()
    fake_row.content = "Jaleco da Camisart em gabardine resistente."
    fake_row.chunk_id = "produto_jaleco"

    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.execute = MagicMock(
        return_value=MagicMock(fetchall=MagicMock(return_value=[fake_row]))
    )

    engine = RAGEngine(
        db_session_factory=lambda: mock_db,
        openai_client=mock_openai_client,
    )
    result = await engine.query("jaleco")
    assert len(result.chunks) == 1
    assert "Jaleco" in result.chunks[0]
    assert result.sources[0] == "produto_jaleco"


async def test_query_graceful_on_api_error(mock_openai_client):
    """Erro na API OpenAI → resultado vazio, não exceção."""
    mock_openai_client.embeddings.create.side_effect = Exception("API timeout")
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)

    engine = RAGEngine(
        db_session_factory=lambda: mock_db,
        openai_client=mock_openai_client,
    )
    result = await engine.query("qualquer coisa")
    assert result.chunks == []
    assert result.top_k == 0


async def test_index_document_chama_embed_por_chunk(mock_openai_client):
    """index_document gera um embedding por chunk."""
    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.execute = MagicMock(return_value=MagicMock())
    mock_db.commit = MagicMock()

    engine = RAGEngine(
        db_session_factory=lambda: mock_db,
        openai_client=mock_openai_client,
    )
    chunks = [
        {"chunk_id": "c1", "content": "Texto 1", "metadata": {}},
        {"chunk_id": "c2", "content": "Texto 2", "metadata": {}},
    ]
    n = await engine.index_document("test_source", chunks)
    assert n == 2
    assert mock_openai_client.embeddings.create.call_count == 2


def test_rag_engine_nao_importado_em_adapters():
    """RAGEngine não deve ser importado em adapters."""
    import ast
    import pathlib
    for f in pathlib.Path("app/adapters").rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                assert "rag_engine" not in module, \
                    f"VIOLATION: {f} importa rag_engine linha {node.lineno}"


# ── Integration: pipeline com RAGEngine mockado ───────────────────────────────

async def test_pipeline_chama_rag_para_pergunta_tecnica(sim, pipeline):
    """Pergunta técnica com LLM baixa confiança → RAG é consultado."""
    from app.engines.rag_engine import RAGEngine, RAGResult

    fake_rag = MagicMock(spec=RAGEngine)
    fake_rag.query = AsyncMock(return_value=RAGResult(
        chunks=["Jaleco em gabardine resistente a lavagens frequentes."],
        sources=["produto_jaleco"],
        query="jaleco hospitalar",
        top_k=1,
    ))
    pipeline._rag_engine = fake_rag

    from app.engines.llm_router import LLMClassification
    with patch(
        "app.engines.llm_router.LLMRouter.classify_intent",
        new_callable=AsyncMock,
        return_value=LLMClassification(intent_id=None, confidence=0.30),
    ):
        from app.engines.llm_router import LLMRouter
        from pathlib import Path
        pipeline._llm_router = LLMRouter(Path("app/knowledge/llm_config.json"))

        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("qual tecido é melhor para jaleco hospitalar?")

    fake_rag.query.assert_called_once()


async def test_pipeline_nao_chama_rag_quando_faq_resolve(sim, pipeline):
    """FAQ com match → RAG não é chamado."""
    from app.engines.rag_engine import RAGEngine
    fake_rag = MagicMock(spec=RAGEngine)
    fake_rag.query = AsyncMock()
    pipeline._rag_engine = fake_rag

    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo?")  # FAQ resolve

    fake_rag.query.assert_not_called()
