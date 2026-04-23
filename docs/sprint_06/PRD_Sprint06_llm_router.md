# PRD — Sprint 06: LLM Router (Fase 2)
**Projeto:** Camisart AI  
**Branch:** `sprint/06-llm-router`  
**Status:** Aprovação Pendente  
**Origem:** Spec §9 Fase 2 + decisão arquitetural de evolução  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S06-01 | `engines/` | `LLMRouter` — classifica intenção quando FAQ retorna None | 🔴 |
| S06-02 | `pipeline/` | Integrar `LLMRouter` no `MessagePipeline` como Camada 2 | 🔴 |
| S06-03 | `knowledge/` | `llm_config.json` — prompts, thresholds e mapeamento de intents | 🔴 |
| S06-04 | `api/` | Endpoint `GET /admin/llm/status` — métricas de uso do LLM | 🟡 |
| S06-05 | `tests/` | Suite completa com mocks Anthropic — zero chamadas reais | 🔴 |
| S06-06 | `scripts/` | `scripts/llm_coverage_check.py` — analisa fallback rate no banco | 🟡 |
| S06-07 | `docs/` | ADR-001: decisão de usar Claude Haiku como LLM Router | 🟢 |

---

## Objetivo do Sprint

Implementar a **Camada 2** da arquitetura de 3 camadas definida em `§2` do spec. Quando o `FAQEngine` (Camada 1) não encontra match por regex, o `LLMRouter` classifica a intenção em linguagem natural e retorna o `intent_id` correto — a resposta ainda vem dos templates do `faq.json`. O LLM é um **classificador**, não um gerador de texto livre.

**Princípio fundamental:** o LLM nunca gera a resposta final. Ele apenas diz "esta mensagem é `preco_polo`". A resposta vem do mesmo template que o regex usaria. Zero alucinação no conteúdo entregue ao cliente.

```
Mensagem do usuário
        │
        ▼
┌─────────────────────┐
│  Camada 1: FAQEngine │  → match? → resposta do template
│  (regex, < 1ms)     │
└──────────┬──────────┘
           │ None (fallback)
           ▼
┌─────────────────────┐
│  Camada 2: LLMRouter │  → intent_id + confidence
│  (Claude Haiku)      │       ≥ 0.85 → age diretamente
│                      │  0.60-0.84  → age + loga para revisão
│                      │  0.40-0.59  → pede confirmação
│                      │     < 0.40  → fallback para humano
└──────────┬──────────┘
           │
           ▼
    resposta do template
    (mesmo faq.json)
```

---

## S06-01 — LLMRouter

### Interface (conforme spec §9 Fase 2)

```python
# app/engines/llm_router.py

class LLMClassification(BaseModel):
    intent_id: str | None        # None = fora do escopo
    confidence: float            # 0.0 a 1.0
    reasoning: str | None = None # para debug logs — nunca enviado ao cliente

class LLMRouter:
    """
    Classificador de intenção via Claude Haiku.

    Recebe mensagem + contexto da sessão + lista de intents conhecidos.
    Retorna o intent_id mais provável com score de confiança.

    NÃO gera respostas livres. NÃO conhece os templates.
    É um classificador puro — igual ao FAQEngine, mas com LLM.
    """

    def __init__(self, config_path: Path, client: anthropic.AsyncAnthropic | None = None):
        ...

    async def classify_intent(
        self,
        message: str,
        session_context: dict,       # últimas 3 msgs + estado atual
        known_intents: list[str],    # ids do faq.json
    ) -> LLMClassification:
        ...
```

### Modelo recomendado

**Claude Haiku 4.5** (`claude-haiku-4-5-20251001`)

| Critério | Valor |
|----------|-------|
| Custo input | $0.80/1M tokens |
| Custo output | $4.00/1M tokens |
| Latência típica | 200-400ms |
| Custo estimado (100 fallbacks/dia) | ~R$ 15/mês |
| Qualidade PT-BR | Excelente nativo |

Fallbacks são a minoria das mensagens (meta < 20%) — custo real é baixo.

### Prompt de classificação

```python
SYSTEM_PROMPT = """Você é um classificador de intenções para o chatbot da Camisart Belém,
uma loja de uniformes em Belém/PA. Sua única função é identificar a intenção
do cliente dentre as opções disponíveis.

REGRAS ABSOLUTAS:
1. Responda SOMENTE com JSON válido — nenhum texto fora do JSON
2. Não invente intent_ids — use exatamente os fornecidos ou retorne null
3. Seja conservador: prefira confidence baixa a intent_id errado
4. Contexto da conversa ajuda — use o histórico fornecido

Formato de resposta obrigatório:
{"intent_id": "string_ou_null", "confidence": 0.0_a_1.0, "reasoning": "string_curta"}"""

USER_PROMPT = """Intents disponíveis: {intent_ids}

Histórico recente:
{context}

Mensagem atual: "{message}"

Classifique a intenção."""
```

### Thresholds de confiança

```python
# app/knowledge/llm_config.json
{
  "model": "claude-haiku-4-5-20251001",
  "max_tokens": 150,
  "thresholds": {
    "high":   0.85,   # age diretamente — responde com template
    "medium": 0.60,   # age + registra para revisão humana
    "low":    0.40,   # pede confirmação: "Você quis dizer X?"
    "reject": 0.00    # < 0.40 → fallback para humano
  },
  "context_window": 3,       # número de mensagens anteriores no contexto
  "timeout_seconds": 8.0,    # timeout da chamada Anthropic
  "fallback_on_error": true  # se API falhar → usa fallback do FAQ, não quebra
}
```

### Comportamento por threshold

```python
# No MessagePipeline, após LLMRouter.classify_intent():

if classification.confidence >= thresholds["high"]:
    # Age diretamente — transparente para o usuário
    return _response_from_intent(classification.intent_id)

elif classification.confidence >= thresholds["medium"]:
    # Age + loga para revisão
    logger.info("LLM medium confidence: %s (%.2f) for: %s",
                classification.intent_id, classification.confidence, message)
    return _response_from_intent(classification.intent_id)

elif classification.confidence >= thresholds["low"]:
    # Pede confirmação
    intent_label = _get_intent_label(classification.intent_id)
    return HandleResult(
        response=FAQResponse(
            type="buttons",
            body=f"Você quis dizer: *{intent_label}*?",
            buttons=[
                {"id": f"confirm_{classification.intent_id}", "title": "✅ Sim"},
                {"id": "falar_humano", "title": "❌ Não, outra coisa"},
            ]
        ),
        next_state=f"aguarda_confirmacao_llm",
    )

else:
    # Confiança muito baixa → fallback para humano
    return _fallback_response()
```

---

## S06-02 — Integração no MessagePipeline

O `MessagePipeline` é o único lugar onde a Camada 2 é invocada. O FAQEngine continua sendo a primeira camada — o LLMRouter só é chamado quando `faq_engine.match()` retorna `None`.

```python
# app/pipeline/message_pipeline.py — atualização do processo

async def process(self, inbound: InboundMessage, db: Session) -> OutboundMessage | None:
    ...
    # Camada 1 — FAQEngine (regex, sem custo)
    faq_match = self._faq_engine.match(inbound.content)

    if faq_match:
        # Camada 1 resolveu — vai direto para resposta
        result = _result_from_faq_match(faq_match, session)
    else:
        # Camada 1 não resolveu — tenta Camada 2
        if self._llm_router:
            context = _build_context(session, db)
            known_intents = self._faq_engine.intent_ids()
            classification = await self._llm_router.classify_intent(
                message=inbound.content,
                session_context=context,
                known_intents=known_intents,
            )
            result = _result_from_classification(
                classification,
                session,
                self._faq_engine,
                self._llm_config,
            )
        else:
            # LLMRouter não configurado — fallback direto
            result = handle(inbound.content, session, self._faq_engine)
    ...
```

**Contrato arquitetural preservado:** o `MessagePipeline` não conhece canais. O `LLMRouter` não conhece canais. A Camada 2 é mais um módulo em `app/engines/` — exatamente como o `FAQEngine`.

### Inicialização no lifespan

```python
# app/main.py — lifespan

from app.engines.llm_router import LLMRouter

llm_router = None
if settings.ANTHROPIC_API_KEY:
    llm_router = LLMRouter(
        config_path=settings.LLM_CONFIG_PATH,
    )
    logger.info("LLMRouter inicializado com Claude Haiku.")
else:
    logger.warning("ANTHROPIC_API_KEY não configurada — LLMRouter desativado.")

pipeline = MessagePipeline(
    faq_engine=faq_engine,
    campaign_engine=campaign_engine,
    llm_router=llm_router,  # None → só Camada 1
)
```

**Degradação graciosa:** se `ANTHROPIC_API_KEY` não estiver configurada, o bot funciona exatamente como antes (só Camada 1). Zero breaking change.

---

## S06-03 — `app/knowledge/llm_config.json`

```json
{
  "_comment": "Configuração do LLMRouter — Camada 2 da arquitetura de 3 camadas.",
  "_model_guide": "Use claude-haiku-4-5-20251001 para produção. Claude para custo/qualidade.",
  "version": "1.0",
  "model": "claude-haiku-4-5-20251001",
  "max_tokens": 150,
  "temperature": 0.0,
  "thresholds": {
    "high":   0.85,
    "medium": 0.60,
    "low":    0.40
  },
  "context_window": 3,
  "timeout_seconds": 8.0,
  "fallback_on_error": true,
  "log_all_classifications": false,
  "log_low_confidence": true,
  "system_prompt": "Você é um classificador de intenções para o chatbot da Camisart Belém, uma loja de uniformes em Belém/PA. Sua única função é identificar a intenção do cliente dentre as opções disponíveis.\n\nREGRAS:\n1. Responda SOMENTE com JSON: {\"intent_id\": \"string_ou_null\", \"confidence\": 0.0, \"reasoning\": \"string\"}\n2. Use exatamente os intent_ids fornecidos ou retorne null\n3. Seja conservador: confidence baixa é melhor que intent errado\n4. null significa que a mensagem está fora do escopo da Camisart"
}
```

---

## S06-04 — Endpoint admin LLM status

```python
# app/api/admin.py — adicionar

@router.get("/llm/status", dependencies=[Depends(verify_admin_token)])
async def llm_status() -> StandardResponse:
    """
    Métricas de uso do LLMRouter.
    Requer X-Admin-Token.
    """
    from app.main import llm_router
    if not llm_router:
        return StandardResponse(data={
            "enabled": False,
            "reason": "ANTHROPIC_API_KEY não configurada"
        })
    return StandardResponse(data={
        "enabled": True,
        "model": llm_router.model,
        "total_classifications": llm_router.stats["total"],
        "high_confidence": llm_router.stats["high"],
        "medium_confidence": llm_router.stats["medium"],
        "low_confidence": llm_router.stats["low"],
        "errors": llm_router.stats["errors"],
        "avg_latency_ms": llm_router.stats["avg_latency_ms"],
    })
```

---

## S06-05 — Testes (zero chamadas reais à Anthropic)

**Regra absoluta:** nenhum teste chama a API Anthropic de verdade. Todo teste que envolve o `LLMRouter` usa mock.

```python
# tests/test_llm_router.py

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from app.engines.llm_router import LLMRouter, LLMClassification

CONFIG_PATH = Path("app/knowledge/llm_config.json")


def make_mock_response(intent_id: str | None, confidence: float) -> MagicMock:
    """Cria mock da resposta da API Anthropic."""
    content = json.dumps({
        "intent_id": intent_id,
        "confidence": confidence,
        "reasoning": f"test mock for {intent_id}"
    })
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=content)]
    return mock_msg


@pytest.fixture
def router():
    return LLMRouter(CONFIG_PATH)


@pytest.mark.asyncio
async def test_classifica_intent_com_alta_confianca(router):
    with patch.object(router._client.messages, "create",
                      new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_response("preco_polo", 0.95)
        result = await router.classify_intent(
            message="quanto custa aquela camisa branca?",
            session_context={},
            known_intents=["preco_polo", "endereco", "bordado_prazo"],
        )
    assert result.intent_id == "preco_polo"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_retorna_none_para_fora_do_escopo(router):
    with patch.object(router._client.messages, "create",
                      new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_response(None, 0.95)
        result = await router.classify_intent(
            message="qual o preço do bitcoin?",
            session_context={},
            known_intents=["preco_polo", "endereco"],
        )
    assert result.intent_id is None


@pytest.mark.asyncio
async def test_fallback_em_erro_de_api(router):
    """Se API falhar, retorna classificação vazia sem levantar exceção."""
    with patch.object(router._client.messages, "create",
                      new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = Exception("Connection timeout")
        result = await router.classify_intent(
            message="qualquer coisa",
            session_context={},
            known_intents=["preco_polo"],
        )
    assert result.intent_id is None
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_fallback_em_json_invalido(router):
    """Se API retornar JSON inválido, retorna classificação vazia."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="isso não é json")]
    with patch.object(router._client.messages, "create",
                      new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_msg
        result = await router.classify_intent(
            message="qualquer coisa",
            session_context={},
            known_intents=["preco_polo"],
        )
    assert result.intent_id is None
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_intent_id_invalido_descartado(router):
    """Se LLM retornar intent_id que não existe na lista, descartar."""
    with patch.object(router._client.messages, "create",
                      new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_response("intent_inventado", 0.99)
        result = await router.classify_intent(
            message="mensagem qualquer",
            session_context={},
            known_intents=["preco_polo", "endereco"],
        )
    assert result.intent_id is None  # inventado não é aceito


@pytest.mark.asyncio
async def test_contexto_incluido_no_prompt(router):
    """Verifica que o contexto da sessão é incluído no prompt enviado."""
    with patch.object(router._client.messages, "create",
                      new_callable=AsyncMock) as mock_create:
        mock_create.return_value = make_mock_response("preco_polo", 0.9)
        await router.classify_intent(
            message="e quanto fica com bordado?",
            session_context={"last_messages": ["quero comprar polo"]},
            known_intents=["preco_polo", "bordado_prazo"],
        )
    call_kwargs = mock_create.call_args
    # O prompt deve conter o histórico
    messages_arg = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
    prompt_text = str(messages_arg)
    assert "polo" in prompt_text.lower()


# ── Testes de integração: pipeline com LLMRouter mockado ──────────────────

@pytest.mark.asyncio
async def test_pipeline_usa_llm_quando_faq_retorna_none(sim, pipeline):
    """Mensagem sem match no FAQ → LLMRouter é chamado."""
    mock_classification = LLMClassification(
        intent_id="preco_polo",
        confidence=0.90,
        reasoning="test"
    )
    with patch(
        "app.engines.llm_router.LLMRouter.classify_intent",
        new_callable=AsyncMock,
        return_value=mock_classification
    ):
        # Injetar llm_router no pipeline
        from app.engines.llm_router import LLMRouter
        pipeline._llm_router = LLMRouter(CONFIG_PATH)

        await sim.send("/start")
        await sim.send("Thiago")
        # Mensagem que não casa com regex mas LLM classifica como preco_polo
        await sim.send("quanto fica aquela camisa de manga curta branca?")

    # Com LLM classificando como preco_polo, deve conter info de polo
    assert sim.last_response  # respondeu algo


@pytest.mark.asyncio
async def test_pipeline_sem_llm_funciona_normalmente(sim):
    """Pipeline sem LLMRouter configurado funciona igual ao Sprint 05."""
    # sim usa pipeline sem llm_router (None)
    await sim.send("/start")
    await sim.send("Thiago")
    await sim.send("qual o preço da polo?")
    assert any(w in sim.last_response for w in ["45", "42", "polo"])


@pytest.mark.asyncio
async def test_pipeline_llm_com_baixa_confianca_pede_confirmacao(sim, pipeline):
    """Confiança < 0.40 → fallback, não resposta do intent."""
    mock_classification = LLMClassification(
        intent_id="preco_polo",
        confidence=0.30,  # abaixo do threshold low
        reasoning="test"
    )
    with patch(
        "app.engines.llm_router.LLMRouter.classify_intent",
        new_callable=AsyncMock,
        return_value=mock_classification
    ):
        from app.engines.llm_router import LLMRouter
        pipeline._llm_router = LLMRouter(CONFIG_PATH)

        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("mensagem ambígua xpto")

    # Com confiança baixa, deve ir para humano ou mostrar fallback
    assert sim.last_response


@pytest.mark.asyncio
async def test_llm_never_called_when_faq_matches(sim, pipeline):
    """FAQ com match não chama LLMRouter — verificado por mock."""
    from app.engines.llm_router import LLMRouter
    pipeline._llm_router = LLMRouter(CONFIG_PATH)

    with patch.object(
        pipeline._llm_router, "classify_intent",
        new_callable=AsyncMock
    ) as mock_classify:
        await sim.send("/start")
        await sim.send("Thiago")
        await sim.send("qual o preço da polo?")  # FAQ match

    mock_classify.assert_not_called()


def test_llm_router_nao_importado_em_adapters():
    """LLMRouter não deve ser importado em adapters."""
    import ast, pathlib
    for f in pathlib.Path("app/adapters").rglob("*.py"):
        src = f.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                assert "llm_router" not in module, \
                    f"VIOLATION: {f} importa llm_router"
```

---

## S06-06 — `scripts/llm_coverage_check.py`

Script que analisa o banco e calcula o fallback rate real — quantas mensagens o FAQ não resolveu e o LLM precisou atuar.

```python
# scripts/llm_coverage_check.py
"""
Analisa fallback rate no banco de dados.
Compara mensagens resolvidas pelo FAQ (matched_intent_id NOT NULL)
vs não resolvidas (NULL).

Uso:
    python scripts/llm_coverage_check.py
    python scripts/llm_coverage_check.py --days 7
    python scripts/llm_coverage_check.py --show-gaps
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database import SessionLocal

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--show-gaps", action="store_true",
                        help="Mostra mensagens que cairam em fallback")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE matched_intent_id IS NOT NULL) as matched,
                COUNT(*) FILTER (WHERE matched_intent_id IS NULL) as fallback,
                COUNT(*) as total
            FROM messages
            WHERE direction = 'in'
              AND created_at >= NOW() - INTERVAL ':days days'
        """), {"days": args.days}).fetchone()

        matched, fallback, total = result
        if total == 0:
            print("Nenhuma mensagem no período.")
            return

        faq_rate = matched * 100 / total
        fallback_rate = fallback * 100 / total

        print(f"\n{'='*55}")
        print(f"FAQ COVERAGE — últimos {args.days} dias")
        print(f"{'='*55}")
        print(f"  ✅ FAQ resolveu:   {matched:4d} msgs ({faq_rate:.1f}%)")
        print(f"  🤖 LLM necessário: {fallback:4d} msgs ({fallback_rate:.1f}%)")
        print(f"  Total:             {total:4d} msgs")
        print(f"\n  Meta: fallback < 20%")
        status = "✅ OK" if fallback_rate < 20 else \
                 "⚠️  ATENÇÃO" if fallback_rate < 35 else \
                 "🔴 CRÍTICO — retreinar FAQ"
        print(f"  Status: {status}")

        if args.show_gaps and fallback > 0:
            gaps = db.execute(text("""
                SELECT content, COUNT(*) as freq
                FROM messages
                WHERE direction = 'in'
                  AND matched_intent_id IS NULL
                  AND created_at >= NOW() - INTERVAL ':days days'
                GROUP BY content
                ORDER BY freq DESC
                LIMIT 20
            """), {"days": args.days}).fetchall()

            print(f"\n{'─'*55}")
            print(f"Top {len(gaps)} mensagens sem match no FAQ:")
            for msg, freq in gaps:
                print(f"  [{freq:3d}x] {msg[:60]!r}")

        print(f"{'='*55}\n")

    finally:
        db.close()

if __name__ == "__main__":
    main()
```

---

## S06-07 — ADR-001: Decisão de usar Claude Haiku como LLM Router

Criar `docs/decisions/ADRs.md`:

```markdown
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
```

---

## Ordem de Execução

```
S06-07 → S06-03 → S06-01 → S06-02 → S06-04 → S06-05 → S06-06
```

S06-07 (ADR) primeiro — decisão documentada antes de código.  
S06-03 (config JSON) antes do código — o `LLMRouter` lê o config.  
S06-01 (LLMRouter) antes do pipeline — dependência direta.  
S06-02 (pipeline) integra tudo.  
S06-04 (endpoint admin) é independente.  
S06-05 (testes) acompanha cada item.  
S06-06 (script análise) fecha o sprint.

---

## Variáveis de Ambiente

Acrescentar ao `.env.example`:

```env
# LLM Router — Fase 2
ANTHROPIC_API_KEY=          # deixar em branco desativa o LLMRouter graciosamente
LLM_CONFIG_PATH=app/knowledge/llm_config.json
```

---

## Commits Atômicos Esperados

```
docs(adr): ADR-001 decisão Claude Haiku como LLM Router [S06-07]
feat(knowledge): llm_config.json com prompts e thresholds [S06-03]
feat(engine): LLMRouter — classificador de intenção via Claude Haiku [S06-01]
feat(pipeline): integra LLMRouter como Camada 2 com degradação graciosa [S06-02]
feat(api): GET /admin/llm/status com métricas de uso [S06-04]
test(llm): suite completa com mocks Anthropic — zero chamadas reais [S06-05]
feat(scripts): llm_coverage_check.py — fallback rate no banco [S06-06]
```

---

## Critérios de Aceite

- [ ] Mensagem sem match no FAQ → `LLMRouter.classify_intent()` é chamado
- [ ] Mensagem com match no FAQ → `LLMRouter` **não** é chamado (verificado por mock)
- [ ] `ANTHROPIC_API_KEY` ausente → bot funciona normalmente sem LLM (Camada 1 apenas)
- [ ] API Anthropic com erro → fallback gracioso, bot não quebra
- [ ] LLM retorna intent_id inválido → descartado, não alucinado
- [ ] Confiança < 0.40 → fallback para humano (não resposta incorreta)
- [ ] `GET /admin/llm/status` retorna métricas com token válido
- [ ] `LLMRouter` não importado em nenhum adapter (teste AST)
- [ ] Nenhum teste chama API Anthropic real (verificar com `grep -r "anthropic" tests/`)
- [ ] `llm_coverage_check.py` roda e mostra fallback rate do banco
- [ ] 0 testes falhando
- [ ] Cobertura global >= 82%
- [ ] CI verde na branch `sprint/06-llm-router`
- [ ] `camisart-sprint-review` aprovado antes do merge
