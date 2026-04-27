# PRD — Sprint 09: Substituição do RAG por Contexto Longo
**Projeto:** Camisart AI  
**Branch:** `sprint/09-context-rag`  
**Status:** Aprovação Pendente  
**Origem:** Artigo Akita "RAG Está Morto?" + avaliação prática Sprint 08 (RAG 0.0% accuracy)  
**Decisão arquitetural:** ADR-003  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Contexto e Motivação

O RAG com pgvector foi implementado no Sprint 07 como Camada 3. Na avaliação do Sprint 08, a acurácia do RAG foi **0.0%** — não porque o código esteja errado, mas porque:

1. O catálogo da Camisart tem ~38 chunks (~6.000 tokens) — cabe inteiramente na janela de contexto do Claude Haiku
2. O pipeline não estava ativando a Camada 3 corretamente no polling
3. Chunking fragmentado perde contexto — o LLM vê 3 pedaços em vez do documento completo

A solução mais simples e mais eficaz para catálogos pequenos é **injetar o catálogo completo no contexto do LLM** e deixar o modelo responder diretamente. Isso é o que o Akita chama de "lazy retrieval" — só usar vector DB quando o volume de dados justificar.

**Quando migrar de volta para RAG:** quando o catálogo crescer além de ~200 produtos (>50.000 tokens) e o custo de contexto longo se tornar proibitivo.

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S09-01 | `docs/` | ADR-003: substituição RAG por contexto longo | 🟢 |
| S09-02 | `engines/` | `ContextEngine` — responde perguntas técnicas com catálogo no contexto | 🔴 |
| S09-03 | `pipeline/` | Pipeline substitui Camada 3 RAG pelo ContextEngine | 🔴 |
| S09-04 | `knowledge/` | `context_config.json` — configuração do ContextEngine | 🟡 |
| S09-05 | `tests/` | Suite completa — zero chamadas reais à Anthropic | 🔴 |
| S09-06 | `scripts/` | Remover `index_knowledge.py` e dependência OpenAI para embeddings | 🟡 |
| S09-07 | `migrations/` | Rollback da tabela `knowledge_chunks` (opcional — manter para histórico) | 🟢 |
| S09-08 | `api/` | Atualizar `GET /admin/rag/status` → `GET /admin/context/status` | 🟢 |

---

## S09-01 — ADR-003

Adicionar em `docs/decisions/ADRs.md`:

```markdown
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
```

---

## S09-02 — ContextEngine

```python
# app/engines/context_engine.py

"""ContextEngine — Camada 3 simplificada via contexto longo.

Substitui o RAGEngine (pgvector + embeddings) por injeção direta do
catálogo completo no contexto do LLM. Adequado para catálogos pequenos
(< 50.000 tokens). Para catálogos maiores, migrar de volta para RAGEngine.

Contrato arquitetural (§2.1 do spec):
- Sem conhecimento de canais
- Interface: answer(question, session_context) → ContextResult
- Degradação graciosa: sem ANTHROPIC_API_KEY retorna resultado vazio
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ContextResult(BaseModel):
    answer: str | None        # resposta gerada — None se erro ou sem conteúdo
    source: str               # "context_engine" | "fallback" | "error"
    tokens_used: int = 0      # estimativa de tokens de contexto usados


class ContextEngine:
    """
    Responde perguntas técnicas sobre produtos da Camisart usando o
    catálogo completo como contexto do LLM.

    Uso:
        engine = ContextEngine(
            knowledge_base_path=Path("app/knowledge/camisart_knowledge_base.md"),
            products_path=Path("app/knowledge/products.json"),
            anthropic_client=client,
        )
        result = await engine.answer(
            question="qual tecido é melhor para jaleco hospitalar?",
            session_context={"nome_cliente": "Maria"}
        )
        # result.answer = "Para uso hospitalar, recomendamos o jaleco em gabardine..."
    """

    SYSTEM_PROMPT = """Você é o assistente especialista da Camisart Belém, uma malharia
de uniformes em Belém/PA. Responda a pergunta do cliente usando APENAS as informações
do catálogo abaixo.

REGRAS ABSOLUTAS:
1. Use SOMENTE informações do catálogo fornecido — nunca invente
2. Se a informação não estiver no catálogo, diga que um consultor pode ajudar melhor
3. Seja direto, amigável e em português — máximo 3 parágrafos curtos
4. Não mencione que está consultando um catálogo — responda naturalmente
5. Se relevante, sugira fazer um orçamento ao final"""

    def __init__(
        self,
        knowledge_base_path: Path,
        products_path: Path,
        anthropic_client,
        config: dict | None = None,
    ) -> None:
        self._kb_path = knowledge_base_path
        self._products_path = products_path
        self._client = anthropic_client
        self._config = config or {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 400,
            "timeout_seconds": 10.0,
        }
        self._context_cache: str | None = None

    def _build_context(self) -> str:
        """Monta o contexto completo do catálogo (cached)."""
        if self._context_cache:
            return self._context_cache

        parts = []

        # Knowledge base (markdown)
        if self._kb_path.exists():
            kb_text = self._kb_path.read_text(encoding="utf-8")
            # Remove seções de metadados/pendências para reduzir tokens
            lines = kb_text.split("\n")
            filtered = []
            skip = False
            for line in lines:
                if "AGUARDANDO VALIDAÇÃO" in line or "⚠️" in line:
                    skip = True
                if line.startswith("## ") and skip:
                    skip = False
                if not skip:
                    filtered.append(line)
            parts.append("## BASE DE CONHECIMENTO CAMISART\n\n" + "\n".join(filtered))

        # Products JSON — resumido para tokens
        if self._products_path.exists():
            products = json.loads(self._products_path.read_text(encoding="utf-8"))
            prod_lines = ["## CATÁLOGO DE PRODUTOS\n"]
            for p in products.get("products", []):
                rag_text = p.get("rag_texto", "")
                if rag_text:
                    prod_lines.append(f"- {rag_text}")
            for s in products.get("servicos", []):
                rag_text = s.get("rag_texto", "")
                if rag_text:
                    prod_lines.append(f"- {rag_text}")
            parts.append("\n".join(prod_lines))

        self._context_cache = "\n\n---\n\n".join(parts)
        return self._context_cache

    def estimated_tokens(self) -> int:
        """Estimativa de tokens do contexto (1 token ≈ 4 chars)."""
        return len(self._build_context()) // 4

    async def answer(
        self,
        question: str,
        session_context: dict | None = None,
    ) -> ContextResult:
        """
        Responde uma pergunta técnica usando o catálogo como contexto.
        Retorna ContextResult com answer=None em caso de erro.
        """
        try:
            context = self._build_context()
            nome = (session_context or {}).get("nome_cliente", "cliente")

            user_prompt = (
                f"CATÁLOGO DA CAMISART:\n\n{context}\n\n"
                f"---\n\n"
                f"Pergunta de {nome}: {question}"
            )

            response = await self._client.messages.create(
                model=self._config.get("model", "claude-haiku-4-5-20251001"),
                max_tokens=self._config.get("max_tokens", 400),
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=self._config.get("timeout_seconds", 10.0),
            )

            answer_text = response.content[0].text.strip()
            tokens = len(context) // 4  # estimativa

            return ContextResult(
                answer=answer_text,
                source="context_engine",
                tokens_used=tokens,
            )

        except Exception as exc:
            logger.error("ContextEngine.answer erro: %s", exc)
            return ContextResult(answer=None, source="error", tokens_used=0)

    def invalidate_cache(self) -> None:
        """Invalida o cache — chamar após atualizar o catálogo."""
        self._context_cache = None
```

---

## S09-03 — Integrar ContextEngine no Pipeline

### Substituição da Camada 3

```python
# app/pipeline/message_pipeline.py

# No __init__, substituir rag_engine por context_engine:
def __init__(
    self,
    faq_engine: FAQEngine,
    campaign_engine: CampaignEngine | None = None,
    llm_router: "LLMRouter | None" = None,
    llm_config: dict | None = None,
    context_engine: "ContextEngine | None" = None,   # ← substitui rag_engine
) -> None:
    ...
    self._context_engine = context_engine

# No process(), substituir bloco RAG:

# ── Camada 3: ContextEngine ──────────────────────────────────────────
if (self._context_engine
        and is_product_question(inbound.content)
        and not result_from_layer2_was_confident):

    ctx_result = await self._context_engine.answer(
        question=inbound.content,
        session_context={
            "nome_cliente": session.nome_cliente,
            "current_state": session.current_state,
        },
    )

    if ctx_result.answer:
        logger.info(
            "ContextEngine Camada 3: '%s' → resposta gerada (%d tokens contexto)",
            inbound.content[:50],
            ctx_result.tokens_used,
        )
        from app.engines.regex_engine import FAQResponse
        from app.engines.state_machine import HandleResult
        result = HandleResult(
            response=FAQResponse(type="text", body=ctx_result.answer),
            next_state=session.current_state,
            matched_intent_id="context_response",
        )
    # Se answer é None, continua para o fallback existente
```

### Inicialização no `app/main.py`

```python
# Substituir bloco do RAGEngine:

from app.engines.context_engine import ContextEngine

context_engine = None
if settings.ANTHROPIC_API_KEY:
    import anthropic as _anthropic
    _context_client = _anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    context_engine = ContextEngine(
        knowledge_base_path=settings.KNOWLEDGE_BASE_PATH,
        products_path=Path("app/knowledge/products.json"),
        anthropic_client=_context_client,
    )
    logger.info(
        "ContextEngine inicializado — ~%d tokens de contexto.",
        context_engine.estimated_tokens(),
    )
else:
    logger.info(
        "ANTHROPIC_API_KEY não configurada — ContextEngine desativado."
    )

pipeline = MessagePipeline(
    faq_engine=faq_engine,
    campaign_engine=campaign_engine,
    llm_router=llm_router,
    llm_config=llm_config,
    context_engine=context_engine,
)
app.state.context_engine = context_engine
```

### Atualizar `scripts/telegram_polling.py`

```python
# Substituir bloco do RAGEngine por ContextEngine:
context_engine = None
if settings.ANTHROPIC_API_KEY:
    import anthropic as _anthropic
    from app.engines.context_engine import ContextEngine
    _ctx_client = _anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    context_engine = ContextEngine(
        knowledge_base_path=settings.KNOWLEDGE_BASE_PATH,
        products_path=Path("app/knowledge/products.json"),
        anthropic_client=_ctx_client,
    )

pipeline = MessagePipeline(
    faq_engine=faq_engine,
    campaign_engine=campaign_engine,
    llm_router=_llm_router,
    llm_config=_llm_config,
    context_engine=context_engine,
)
```

---

## S09-04 — `context_config.json`

```json
// app/knowledge/context_config.json
{
  "_comment": "Configuração do ContextEngine — Camada 3 via contexto longo.",
  "_decision": "ADR-003: substitui RAGEngine para catálogos < 50.000 tokens.",
  "_migrate_when": "Catálogo > 200 produtos (~50k tokens) — ver ADR-002.",
  "version": "1.0",
  "model": "claude-haiku-4-5-20251001",
  "max_tokens": 400,
  "timeout_seconds": 10.0,
  "estimated_context_tokens": 6000,
  "max_context_tokens_before_migration": 50000
}
```

Atualizar `app/config.py`:
```python
CONTEXT_CONFIG_PATH: Path = Path("app/knowledge/context_config.json")
```

---

## S09-05 — Testes

```python
# tests/test_context_engine.py

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
    from app.engines.context_engine import ContextEngine

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
    from app.engines.context_engine import ContextEngine
    fake_engine = MagicMock(spec=ContextEngine)
    fake_engine.answer = AsyncMock()
    pipeline._context_engine = fake_engine

    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo?")  # FAQ resolve

    fake_engine.answer.assert_not_called()


def test_context_engine_nao_importado_em_adapters():
    import ast, pathlib
    for f in pathlib.Path("app/adapters").rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                assert "context_engine" not in module, \
                    f"VIOLATION: {f} importa context_engine linha {node.lineno}"
```

---

## S09-06 — Limpeza

### Remover dependência OpenAI para embeddings

O `openai` SDK pode ser mantido no `requirements.txt` comentado — pode ser necessário no futuro para BERTimbau ou outros embeddings.

```
# requirements.txt
# openai>=1.0  # Removido Sprint 09 — RAG substituído por contexto longo (ADR-003)
#              # Reabilitar quando catálogo > 200 produtos
```

### Marcar `index_knowledge.py` como deprecated

```python
# scripts/index_knowledge.py — adicionar no topo:

"""
DEPRECATED — Sprint 09 (ADR-003)

Este script indexava o catálogo no pgvector para busca semântica (RAG).
Foi substituído pelo ContextEngine que injeta o catálogo completo no contexto
do LLM — mais simples e mais preciso para catálogos pequenos.

Para reabilitar: ver ADR-002 e ADR-003 em docs/decisions/ADRs.md.
Condição: catálogo > 200 produtos (~50.000 tokens).
"""
import sys
print("DEPRECATED: index_knowledge.py não é mais necessário.")
print("Ver ADR-003: app/engines/context_engine.py")
sys.exit(0)
```

---

## S09-07 — Tabela `knowledge_chunks`

Manter a tabela no banco — não fazer rollback. Motivo: preservar histórico e facilitar eventual migração de volta para RAG sem re-criar a estrutura.

Documentar no `CLAUDE.md`:
```
### knowledge_chunks (Sprint 07 — inativa desde Sprint 09)
A tabela knowledge_chunks existe no banco mas não é mais usada.
O RAGEngine foi substituído pelo ContextEngine (ADR-003).
Manter a tabela para eventual migração futura quando catálogo > 200 produtos.
```

---

## S09-08 — Endpoint admin

```python
# app/api/admin.py — substituir /rag/status por /context/status

@router.get("/context/status", dependencies=[Depends(verify_admin_token)])
async def context_status(request: Request) -> StandardResponse:
    """
    Status do ContextEngine (Camada 3).

    Mostra tamanho do catálogo em tokens e quando migrar para RAG.
    """
    engine = getattr(request.app.state, "context_engine", None)
    if not engine:
        return StandardResponse(data={
            "enabled": False,
            "reason": "ANTHROPIC_API_KEY não configurada.",
        })

    tokens = engine.estimated_tokens()
    pct = round(tokens / 50000 * 100, 1)

    return StandardResponse(data={
        "enabled": True,
        "model": engine._config.get("model"),
        "estimated_context_tokens": tokens,
        "max_before_migration": 50000,
        "usage_percent": pct,
        "recommendation": (
            "OK — contexto longo adequado para este tamanho de catálogo"
            if tokens < 30000
            else "ATENÇÃO — considerar migração para RAG (ADR-002)"
        ),
    })
```

---

## Ordem de Execução

```
S09-01 → S09-04 → S09-02 → S09-03 → S09-05 → S09-06 → S09-07 → S09-08
```

ADR primeiro — decisão documentada antes de código.  
Config JSON antes do engine — o engine lê o config.  
ContextEngine antes do pipeline — dependência direta.  
Pipeline integra tudo.  
Testes acompanham.  
Limpeza e deprecação ao final.  

---

## Commits Atômicos Esperados

```
docs(adr): ADR-003 substituição RAG por contexto longo [S09-01]
feat(knowledge): context_config.json [S09-04]
feat(engine): ContextEngine — Camada 3 via contexto longo [S09-02]
feat(pipeline): substitui RAGEngine por ContextEngine [S09-03]
test(context): suite completa zero chamadas reais à Anthropic [S09-05]
chore(cleanup): depreca index_knowledge.py + remove openai de requirements [S09-06]
docs(claude): documenta knowledge_chunks inativa [S09-07]
feat(api): GET /admin/context/status [S09-08]
```

---

## Critérios de Aceite

- [ ] `ContextEngine.answer("qual tecido para jaleco hospitalar?")` retorna resposta fundamentada no catálogo
- [ ] Catálogo completo está no contexto da chamada API (verificado por mock)
- [ ] Pipeline ativa ContextEngine apenas quando FAQ e LLM têm baixa confiança
- [ ] Pipeline NÃO ativa ContextEngine quando FAQ resolve (Camada 1)
- [ ] `GET /admin/context/status` retorna tokens estimados e recomendação
- [ ] `ContextEngine` não importado em adapters (teste AST)
- [ ] Nenhum teste chama API Anthropic ou OpenAI real
- [ ] `index_knowledge.py` marcado como deprecated
- [ ] `openai` removido de requirements ativos
- [ ] 0 testes falhando
- [ ] Cobertura global >= 82%
- [ ] CI verde
- [ ] `camisart-sprint-review` aprovado antes do merge

---

## Comparação de Complexidade

| | RAGEngine (Sprint 07) | ContextEngine (Sprint 09) |
|---|---|---|
| Dependências | pgvector + openai SDK | Só anthropic (já existe) |
| Infra adicional | Extensão PostgreSQL + tabela + índice HNSW | Nenhuma |
| Pipeline | Embedding → pgvector → chunks → LLM | LLM direto com contexto |
| Custo/query técnica | ~$0.002 (embedding) + $0.005 (LLM) | ~$0.005 (só LLM) |
| Latência | ~2.3s (embedding + LLM) | ~1.5s (só LLM) |
| Manutenção | Re-indexar após cada atualização | Nenhuma |
| Acurácia Sprint 08 | 0.0% | A medir |
