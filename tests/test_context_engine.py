"""
Testes do ContextEngine — Camada 3 via contexto longo.
REGRA: zero chamadas reais à API Anthropic.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.engines.context_engine import ContextEngine, ContextResult

KB_PATH = Path("app/knowledge/camisart_knowledge_base.md")
PRODUCTS_PATH = Path("app/knowledge/products.json")


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=MagicMock(
        content=[MagicMock(
            text="Para uso hospitalar recomendamos o jaleco em gabardine."
        )]
    ))
    return client


@pytest.fixture
def engine(mock_client):
    return ContextEngine(
        knowledge_base_path=KB_PATH,
        products_path=PRODUCTS_PATH,
        anthropic_client=mock_client,
    )


# ── Context building ──────────────────────────────────────────────────────────

def test_context_contem_jaleco(engine):
    ctx = engine._build_context()
    assert "jaleco" in ctx.lower()


def test_context_contem_bordado(engine):
    ctx = engine._build_context()
    assert "bordado" in ctx.lower()


def test_context_contem_polo(engine):
    ctx = engine._build_context()
    assert "polo" in ctx.lower()


def test_context_cache_funciona(engine):
    ctx1 = engine._build_context()
    ctx2 = engine._build_context()
    assert ctx1 is ctx2  # mesmo objeto — cache ativo


def test_invalidate_cache(engine):
    ctx1 = engine._build_context()
    engine.invalidate_cache()
    ctx2 = engine._build_context()
    assert ctx1 == ctx2  # conteúdo igual mas objeto diferente
    assert ctx1 is not ctx2


def test_estimated_tokens_razoavel(engine):
    tokens = engine.estimated_tokens()
    assert 1000 < tokens < 50000, f"Tokens fora do esperado: {tokens}"


# ── answer() ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_answer_retorna_resposta(engine):
    result = await engine.answer("qual tecido para jaleco hospitalar?")
    assert isinstance(result, ContextResult)
    assert result.answer is not None
    assert len(result.answer) > 10
    assert result.source == "context_engine"


@pytest.mark.asyncio
async def test_answer_usa_nome_do_cliente(engine, mock_client):
    await engine.answer(
        "qual tecido?",
        session_context={"nome_cliente": "Maria"}
    )
    call_args = mock_client.messages.create.call_args
    messages = call_args.kwargs.get("messages") or call_args.args[0]
    prompt_text = str(messages)
    assert "Maria" in prompt_text


@pytest.mark.asyncio
async def test_answer_graceful_on_api_error(engine, mock_client):
    mock_client.messages.create.side_effect = Exception("API timeout")
    result = await engine.answer("qualquer pergunta")
    assert result.answer is None
    assert result.source == "error"


@pytest.mark.asyncio
async def test_answer_inclui_catalogo_no_contexto(engine, mock_client):
    await engine.answer("quanto custa o jaleco?")
    call_args = mock_client.messages.create.call_args
    messages = call_args.kwargs.get("messages") or call_args.args[0]
    prompt_text = str(messages)
    assert "jaleco" in prompt_text.lower()
    assert "camisart" in prompt_text.lower()


# ── Pipeline integration ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_usa_context_engine_para_pergunta_tecnica(
    sim, pipeline, mock_client
):
    fake_engine = MagicMock(spec=ContextEngine)
    fake_engine.answer = AsyncMock(return_value=ContextResult(
        answer="O jaleco premium usa gabardine superior.",
        source="context_engine",
        tokens_used=5000,
    ))
    pipeline._context_engine = fake_engine

    from app.engines.llm_router import LLMClassification
    from unittest.mock import patch
    with patch(
        "app.engines.llm_router.LLMRouter.classify_intent",
        new_callable=AsyncMock,
        return_value=LLMClassification(intent_id=None, confidence=0.30),
    ):
        from app.engines.llm_router import LLMRouter
        pipeline._llm_router = LLMRouter(
            Path("app/knowledge/llm_config.json")
        )
        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("qual a diferença do jaleco premium para o tradicional?")

    fake_engine.answer.assert_called_once()


@pytest.mark.asyncio
async def test_pipeline_nao_usa_context_quando_faq_resolve(sim, pipeline):
    fake_engine = MagicMock(spec=ContextEngine)
    fake_engine.answer = AsyncMock()
    pipeline._context_engine = fake_engine

    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo?")  # FAQ resolve

    fake_engine.answer.assert_not_called()


def test_context_engine_nao_importado_em_adapters():
    import ast
    import pathlib
    for f in pathlib.Path("app/adapters").rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                assert "context_engine" not in module, \
                    f"VIOLATION: {f} importa context_engine linha {node.lineno}"
