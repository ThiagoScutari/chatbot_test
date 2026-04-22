# PRD — Sprint 03: Qualidade, Dogfooding e Validação Telegram
**Projeto:** Camisart AI  
**Branch:** `sprint/03-quality`  
**Status:** Aprovação Pendente  
**Origem:** Sprint Review 02 (BK-05, BK-13..BK-16) + Princípio Local→Telegram→Produção  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S03-01 | `migrations/` | Índice explícito em `leads.session_id` | 🟡 |
| S03-02 | `tests/` | Migrar `test_telegram_adapter` para `@pytest.mark.asyncio` | 🟡 |
| S03-03 | `tests/` | Teste de integração para `telegram/routes.py` | 🟡 |
| S03-04 | `adapters/` | `registry.py` — integrar ou remover código morto | 🟢 |
| S03-05 | `docs/` | `CLAUDE.md` — documentar cobertura do lifespan como esperada | 🟢 |
| S03-06 | `scripts/` | Script de dogfooding sistemático com checklist automatizado | 🔴 |
| S03-07 | `engines/` | FAQ gap analysis — identificar e cobrir perguntas reais sem match | 🔴 |
| S03-08 | `scripts/` | Script de relatório de sessão — inspecionar banco após testes | 🔴 |
| S03-09 | `docs/` | Critérios de Go-Live documentados e checklist de pré-produção | 🔴 |
| S03-10 | `tests/` | Suite completa Sprint 03 — 0 falhas, cobertura global ≥ 80% | 🟡 |

---

## Objetivo do Sprint

**Não entregar features. Entregar confiança.**

Ao final deste sprint, o produto passou por validação sistemática no Telegram — fluxos completos documentados, gaps do FAQ identificados e corrigidos, banco inspecionado após cada cenário. O checklist de Go-Live está preenchido e o time tem evidência objetiva de que o produto está pronto para o WhatsApp real.

---

## S03-01 — Índice em `leads.session_id`

### Motivação
BK-05. FK sem índice explícito. Volume atual é baixo, mas queries de `SELECT * FROM leads WHERE session_id = ?` vão aparecer em relatórios e no futuro painel admin.

### Implementação

```python
# app/migrations/migrate_sprint_03.py

INDEX_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'leads' AND indexname = 'idx_leads_session_id'
    ) THEN
        CREATE INDEX idx_leads_session_id ON leads(session_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'leads' AND indexname = 'idx_leads_status'
    ) THEN
        CREATE INDEX idx_leads_status ON leads(status)
        WHERE deleted_at IS NULL;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename = 'leads' AND indexname = 'idx_leads_unsynced_kommo'
    ) THEN
        CREATE INDEX idx_leads_unsynced_kommo ON leads(created_at)
        WHERE synced_to_kommo_at IS NULL AND deleted_at IS NULL;
    END IF;
END $$;
"""
```

Três índices em um sprint: `session_id` (BK-05), `status` parcial e `unsynced_kommo` parcial — os dois últimos já previstos no spec §4.4.3 e necessários para a Fase 4.

### Testes
- Índice `idx_leads_session_id` existe no banco após migration
- Índice `idx_leads_status` existe
- Índice `idx_leads_unsynced_kommo` existe
- Migration idempotente — rodar duas vezes sem erro

---

## S03-02 — Migrar test_telegram_adapter para pytest-asyncio

### Motivação
BK-14. `asyncio.get_event_loop().run_until_complete()` está deprecated no Python 3.13 e vai quebrar em versão futura. Warning ativo desde Sprint 01.

### Implementação

```python
# pytest.ini — adicionar:
[pytest]
asyncio_mode = auto

# tests/test_telegram_adapter.py — substituir padrão deprecated:

# ANTES (deprecated)
def test_parse_text_message():
    result = asyncio.get_event_loop().run_until_complete(
        adapter.parse_inbound(VALID_TEXT_UPDATE, {})
    )

# DEPOIS (correto)
@pytest.mark.asyncio
async def test_parse_text_message():
    result = await adapter.parse_inbound(VALID_TEXT_UPDATE, {})
    assert result is not None
    assert result.channel_id == "telegram"
```

Todos os testes async do arquivo migrados para `async def` com `@pytest.mark.asyncio`.

### Testes
- Zero `DeprecationWarning` relacionados a asyncio no output do pytest
- Todos os 9 testes do arquivo continuam passando

---

## S03-03 — Teste de integração telegram/routes.py

### Motivação
BK-16. O endpoint `POST /adapters/telegram/webhook` tem 0% de cobertura. A lógica está no adapter e pipeline, mas o endpoint em si não tem teste de integração — um bug de roteamento ou de wiring não seria detectado.

### Implementação

```python
# tests/test_telegram_routes.py

import json
from unittest.mock import AsyncMock, patch

VALID_TEXT_UPDATE = {
    "update_id": 999001,
    "message": {
        "message_id": 1,
        "from": {"id": 5591999990099, "first_name": "TEST_Integration"},
        "chat": {"id": 5591999990099, "type": "private"},
        "text": "qual o preço da polo?",
        "date": 1714000000,
    }
}

NON_TEXT_UPDATE = {
    "update_id": 999002,
    "message": {
        "message_id": 2,
        "from": {"id": 5591999990099, "first_name": "TEST_Integration"},
        "chat": {"id": 5591999990099, "type": "private"},
        "date": 1714000000,
        # sem "text"
    }
}

def test_telegram_webhook_text_message_returns_200(client):
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = "42"
        r = client.post(
            "/adapters/telegram/webhook",
            json=VALID_TEXT_UPDATE,
        )
    assert r.status_code == 200
    assert r.json()["data"]["received"] is True

def test_telegram_webhook_non_text_returns_200_no_send(client):
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock
    ) as mock_send:
        r = client.post(
            "/adapters/telegram/webhook",
            json=NON_TEXT_UPDATE,
        )
    assert r.status_code == 200
    mock_send.assert_not_called()

def test_telegram_webhook_faq_match_calls_send(client):
    """FAQ match deve disparar send_text uma vez."""
    with patch(
        "app.adapters.telegram.client.send_text",
        new_callable=AsyncMock
    ) as mock_send:
        mock_send.return_value = "43"
        r = client.post(
            "/adapters/telegram/webhook",
            json=VALID_TEXT_UPDATE,
        )
    assert r.status_code == 200
    # send_text pode ser chamado 1 ou 2x (ex: boas-vindas + resposta FAQ)
    assert mock_send.call_count >= 1

def test_telegram_webhook_invalid_secret_returns_403(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "mysecret")
    r = client.post(
        "/adapters/telegram/webhook",
        json=VALID_TEXT_UPDATE,
        headers={"x-telegram-bot-api-secret-token": "wrong"}
    )
    assert r.status_code == 403

def test_adapter_isolation_telegram_routes():
    """telegram/routes.py não deve importar de whatsapp_cloud."""
    import ast, pathlib
    src = pathlib.Path("app/adapters/telegram/routes.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            assert "whatsapp_cloud" not in module, \
                f"VIOLATION: telegram/routes.py importa whatsapp_cloud linha {node.lineno}"
```

---

## S03-04 — registry.py: integrar ou remover

### Motivação
BK-13. `app/adapters/registry.py` existe desde Sprint 01 mas nenhum adapter chama `register()` e nenhum código chama `get()`. É código morto.

### Decisão arquitetural

Integrar — o registry é o mecanismo correto para o `MessagePipeline` rotear mensagens quando houver múltiplos canais ativos (WhatsApp + Telegram + Kommo). A Fase 4 vai precisar dele. Mas precisa ser usado agora.

### Implementação

```python
# app/main.py — dentro do lifespan, após criar os adapters:

from app.adapters.registry import register
from app.adapters.whatsapp_cloud.adapter import WhatsAppCloudAdapter
from app.adapters.telegram.adapter import TelegramAdapter

register(WhatsAppCloudAdapter())
if settings.TELEGRAM_BOT_TOKEN:
    register(TelegramAdapter())
```

```python
# app/pipeline/message_pipeline.py — usar registry para lookup do adapter de retorno:

from app.adapters.registry import get as get_adapter

# No método process(), ao construir OutboundMessage:
# adapter = get_adapter(inbound.channel_id)
# await adapter.send(outbound)
# Isso elimina o acoplamento atual onde cada route chama adapter.send() diretamente
```

### Testes
- `registry.get("whatsapp_cloud")` retorna instância de `WhatsAppCloudAdapter`
- `registry.get("telegram")` retorna instância de `TelegramAdapter`
- `registry.get("canal_inexistente")` levanta `KeyError`
- `registry.py` cobertura > 80%

---

## S03-05 — CLAUDE.md: documentar cobertura do lifespan

### Motivação
BK-15. `app/main.py` fica em ~57% porque o bloco do lifespan não é executado pelo `TestClient`. Sem documentação, futuros auditores vão questionar.

### Implementação

Adicionar seção em `CLAUDE.md`:

```markdown
## Coverage Notes

### app/main.py — lifespan block (~57% coverage)
The lifespan context manager (lines 20-37) initializes CampaignEngine, FAQEngine
and registers adapters. This block does NOT run during tests because TestClient
uses dependency_overrides instead of the full lifespan.

This is expected and intentional. The lifespan IS tested indirectly via:
- test_health.py (DB connectivity)
- test_campaign_engine.py (engine logic)
- test_regex_engine.py (FAQ engine logic)

Do not add fake tests to inflate this number.

### app/adapters/*/client.py — ~50-61% coverage
HTTP client modules are always mocked in tests (never call real APIs).
Missing lines are the actual HTTP call paths — correct behavior.
```

---

## S03-06 — Script de dogfooding sistemático

### Motivação
Testes automatizados validam código. Dogfooding valida **experiência**. Este script executa um roteiro de conversas no Telegram e registra o resultado de cada cenário — pass/fail/observação — em um arquivo de relatório.

### Implementação

```python
# scripts/dogfood_checklist.py
"""
Roteiro de validação manual sistemática via Telegram.
Gera relatório em docs/dogfood/YYYY-MM-DD_relatorio.md

Uso:
    python scripts/dogfood_checklist.py

O script imprime cada cenário com instrução clara.
O testador confirma pass/fail/observação via input().
Ao final, salva o relatório em docs/dogfood/.
"""
```

### Cenários do roteiro (20 cenários obrigatórios)

```
BLOCO 1 — Onboarding (4 cenários)
  C01: Enviar /start → espera boas-vindas sem pedir menu
  C02: Enviar nome "Thiago" → espera "Prazer, Thiago!" + menu
  C03: Aguardar 2h e enviar nova mensagem → espera retorno com nome salvo
  C04: Enviar /start novamente após sessão ativa → espera boas-vindas, não fallback

BLOCO 2 — FAQ (6 cenários)
  C05: "qual o preço da polo?" → preço correto sem acionar orçamento
  C06: "camiza polo" (erro ortográfico) → mesmo resultado que C05
  C07: "onde fica a loja?" → endereço + mapa
  C08: "tem pedido mínimo?" → resposta correta
  C09: "quanto demora o bordado?" → prazo + sem mínimo
  C10: "entregam para São Paulo?" → confirma entrega nacional

BLOCO 3 — Fluxo de orçamento (6 cenários)
  C11: Selecionar "Ver catálogo" → catálogo completo entregue
  C12: Iniciar orçamento → segmento → produto → quantidade → personalização → prazo → confirmação
  C13: Digitar quantidade inválida ("muitas") → bot pede novamente sem avançar
  C14: Digitar "corrigir" na confirmação → volta para quantidade
  C15: Confirmar orçamento → lead gravado no banco (verificar via S03-08)
  C16: Orçamento para segmento "saúde" → lista apenas jaleco tradicional e premium

BLOCO 4 — Handoff (2 cenários)
  C17: "falar com atendente" → mensagem de handoff + estado AGUARDA_RETORNO_HUMANO
  C18: Mensagem após handoff → bot responde aguardando, não trava

BLOCO 5 — Edge cases (2 cenários)
  C19: Enviar 11 mensagens em 1 minuto → 11ª bloqueada por rate limit
  C20: Pergunta completamente fora do escopo ("qual o preço do bitcoin?") → fallback com menu
```

### Output do script

```markdown
# Relatório de Dogfooding — 2026-04-22

**Testador:** Thiago Scutari
**Canal:** Telegram (@camisart_dev_bot)
**Duração:** 45 min

## Resultado

| Cenário | Status | Observação |
|---------|--------|-----------|
| C01 /start | ✅ PASS | |
| C02 nome | ✅ PASS | |
...
| C15 lead capturado | ✅ PASS | Lead ID: uuid... |
...

## Gaps identificados
- C20: fallback não mostrou menu — apenas texto simples

## Veredicto
APROVADO COM RESSALVAS / REPROVADO / APROVADO
```

---

## S03-07 — FAQ gap analysis e cobertura de perguntas reais

### Motivação
O `relatorio_instagram_camisart.md` tem 427 comentários reais. Os 9 intents do FAQ foram criados a partir da análise, mas podem estar faltando padrões ou intents. Este item é análise + implementação.

### Processo

1. Ler `docs/relatorio_instagram_camisart.md` — extrair as top 20 perguntas por frequência
2. Testar cada uma no `FAQEngine` via script:

```python
# scripts/faq_coverage_check.py
"""
Testa uma lista de perguntas reais contra o FAQEngine.
Imprime match/fallback para cada uma.

Uso:
    python scripts/faq_coverage_check.py
"""
from pathlib import Path
from app.engines.regex_engine import FAQEngine
from app.engines.campaign_engine import CampaignEngine
from app.config import settings

PERGUNTAS_REAIS = [
    # extraídas do relatorio_instagram_camisart.md
    "quanto custa a polo?",
    "tem polo plus size?",
    "faz entrega para o interior?",
    "aceita cartão?",
    "tem camisa manga longa?",
    "qual o tamanho maior que tem?",
    "faz personalização com foto?",
    "tem camisa feminina?",
    "qual o prazo para 100 peças?",
    "faz uniforme para restaurante?",
    "tem jaleco feminino?",
    "faz camiseta para time de futebol?",
    "qual o Whatsapp de vocês?",
    "tem loja física?",
    "aceita pix?",
    "tem desconto para quantidade?",
    "faz camisa polo infantil?",
    "tem tecido dry fit?",
    "qual o instagram de vocês?",
    "tem estoque pronto?",
]

def main():
    engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    engine.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=engine)

    matched = 0
    gaps = []
    for pergunta in PERGUNTAS_REAIS:
        result = faq.match(pergunta)
        if result:
            matched += 1
            print(f"✅ {pergunta!r} → {result.intent_id}")
        else:
            gaps.append(pergunta)
            print(f"❌ {pergunta!r} → FALLBACK")

    print(f"\n{'='*50}")
    print(f"Cobertura: {matched}/{len(PERGUNTAS_REAIS)} = {matched*100//len(PERGUNTAS_REAIS)}%")
    if gaps:
        print(f"\nGaps ({len(gaps)}):")
        for g in gaps:
            print(f"  - {g!r}")

if __name__ == "__main__":
    main()
```

3. Para cada gap identificado: adicionar intent ou padrão no `faq.json`
4. Meta: cobertura ≥ 80% das 20 perguntas reais

### Intents prováveis a adicionar (baseado no relatório)

```json
// intents candidatos — confirmar após rodar o script
{ "id": "pagamento",       "patterns": ["pix|cartão|boleto|pagamento|parcel"] }
{ "id": "tamanho_plus",    "patterns": ["plus.size|plus|gg2|g3|tamanho.grande"] }
{ "id": "manga_longa",     "patterns": ["manga.longa|manga comprida"] }
{ "id": "feminino",        "patterns": ["feminina|feminino|fem|mulher"] }
{ "id": "infantil",        "patterns": ["infantil|criança|kids|mini"] }
{ "id": "desconto_qtd",    "patterns": ["desconto|atacado|quantidade|lote|por.atacado"] }
{ "id": "contato_wpp",     "patterns": ["whatsapp|zap|número|contato|ligar"] }
{ "id": "dry_fit",         "patterns": ["dry.fit|dryfit|poliéster|esporte|técnica"] }
```

### Testes
- Rodar `faq_coverage_check.py` e cobertura ≥ 80%
- Novos intents adicionados têm testes correspondentes em `test_regex_engine.py`

---

## S03-08 — Script de inspeção de sessão e leads

### Motivação
Durante o dogfooding, o testador precisa verificar rapidamente se o lead foi gravado corretamente, qual o estado da sessão, quantas mensagens foram trocadas — sem precisar escrever SQL manualmente a cada teste.

### Implementação

```python
# scripts/inspect_session.py
"""
Inspeciona sessão, mensagens e leads de um usuário pelo channel_user_id.

Uso:
    python scripts/inspect_session.py 5591999990001
    python scripts/inspect_session.py --last   # última sessão criada
    python scripts/inspect_session.py --leads  # todos os leads novos
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.session import Session as SessionModel
from app.models.message import Message
from app.models.lead import Lead
from app.models.audit_log import AuditLog


def inspect_user(db: Session, channel_user_id: str):
    session = db.query(SessionModel).filter_by(
        channel_user_id=channel_user_id
    ).order_by(SessionModel.created_at.desc()).first()

    if not session:
        print(f"❌ Nenhuma sessão encontrada para {channel_user_id}")
        return

    print(f"\n{'='*60}")
    print(f"SESSÃO: {session.id}")
    print(f"  Canal: {session.channel_id}")
    print(f"  User ID: {session.channel_user_id}")
    print(f"  Nome: {session.nome_cliente}")
    print(f"  Estado atual: {session.current_state}")
    print(f"  Última interação: {session.last_interaction_at}")
    print(f"  session_data: {session.session_data}")

    msgs = db.query(Message).filter_by(session_id=session.id)\
             .order_by(Message.created_at).all()
    print(f"\nMENSAGENS ({len(msgs)}):")
    for m in msgs[-10:]:  # últimas 10
        arrow = "→" if m.direction == "in" else "←"
        intent = f" [{m.matched_intent_id}]" if m.matched_intent_id else ""
        print(f"  {arrow} {m.content[:60]}{intent}")

    leads = db.query(Lead).filter_by(session_id=session.id).all()
    if leads:
        print(f"\nLEADS ({len(leads)}):")
        for l in leads:
            print(f"  • {l.nome_cliente} | {l.segmento} | {l.produto} "
                  f"| {l.quantidade}x | {l.personalizacao} | prazo: {l.prazo_desejado}"
                  f" | status: {l.status}")

    print(f"{'='*60}\n")


def list_new_leads(db: Session):
    leads = db.query(Lead).filter_by(status="novo")\
               .order_by(Lead.created_at.desc()).limit(10).all()
    print(f"\n{'='*60}")
    print(f"LEADS NOVOS (últimos {len(leads)}):")
    for l in leads:
        print(f"  • [{l.created_at.strftime('%H:%M')}] {l.nome_cliente} "
              f"| {l.segmento} | {l.produto} | {l.quantidade}x")
    print(f"{'='*60}\n")


def main():
    db = SessionLocal()
    try:
        args = sys.argv[1:]
        if not args:
            print("Uso: python scripts/inspect_session.py <channel_user_id>")
            print("     python scripts/inspect_session.py --last")
            print("     python scripts/inspect_session.py --leads")
            return
        if args[0] == "--leads":
            list_new_leads(db)
        elif args[0] == "--last":
            s = db.query(SessionModel).order_by(
                SessionModel.last_interaction_at.desc()
            ).first()
            if s:
                inspect_user(db, s.channel_user_id)
        else:
            inspect_user(db, args[0])
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

---

## S03-09 — Critérios de Go-Live documentados

### Motivação
O time precisa de um critério **objetivo e binário** para decidir quando abrir o Sprint de Go-Live. Não "parece bom" — sim ou não, medido.

### Implementação

Criar `docs/go_live_checklist.md`:

```markdown
# Checklist de Go-Live — Camisart AI

Preencher antes de abrir Sprint de Go-Live (Deploy VPS + WhatsApp).
Todos os itens devem estar ✅ APROVADO.

## Critérios Técnicos
- [ ] 0 testes falhando na suite completa
- [ ] Cobertura global >= 80%
- [ ] state_machine.py >= 70%
- [ ] ruff: 0 erros
- [ ] CI verde no main

## Critérios de Produto (validados via Telegram)
- [ ] 20/20 cenários do dogfooding concluídos (docs/dogfood/)
- [ ] FAQ coverage >= 80% nas perguntas reais (faq_coverage_check.py)
- [ ] Fallback rate < 20% em 48h de uso contínuo
- [ ] Fluxo de orçamento completo end-to-end sem intervenção humana
- [ ] Lead capturado no banco com todos os campos corretos
- [ ] Session timeout testado e funcionando
- [ ] Rate limiting testado (11ª mensagem bloqueada)

## Critérios Operacionais (manual)
- [ ] Número dedicado adquirido (não o número atual da Camisart)
- [ ] Conta Meta Business verificada
- [ ] Display name aprovado pela Meta
- [ ] .env de produção criado na VPS (nunca commitado)
- [ ] ADMIN_TOKEN e WHATSAPP_APP_SECRET >= 32 chars na VPS
- [ ] Certbot configurado e HTTPS válido
- [ ] Webhook registrado na Meta e respondendo
- [ ] Migration Sprint 01-03 executadas na VPS
- [ ] Dona da Camisart validou o fluxo completo ao vivo

## Autorização final
**Data:** ___________  
**Aprovado por:** Thiago Scutari  
**Veredicto:** APROVADO / REPROVADO
```

---

## S03-10 — Suite completa Sprint 03

### Meta de cobertura
- Cobertura global ≥ **80%** (era 78% no Sprint 02)
- `adapters/registry.py` ≥ 80%
- `adapters/telegram/routes.py` ≥ 70%
- 0 `DeprecationWarning` no output do pytest

### Arquivos de teste

```
tests/
  test_migration_03.py          ← S03-01 (4 testes — índices)
  test_telegram_adapter.py      ← S03-02 (refatorado, sem warnings)
  test_telegram_routes.py       ← S03-03 (5 testes novos)
  test_adapter_registry.py      ← S03-04 (3 testes)
  test_faq_real_questions.py    ← S03-07 (20 testes — perguntas reais)
```

**Total alvo: ≥ 35 testes novos. Total acumulado: ≥ 155 testes. 0 falhas.**

---

## Ordem de Execução

```
S03-01 → S03-02 → S03-03 → S03-04 → S03-05 → S03-07 → S03-08 → S03-06 → S03-09 → S03-10
```

S03-01..S03-05 fecham o backlog técnico — rápidos, sem risco.  
S03-07 (FAQ gaps) precisa do script S03-07 rodando antes de escrever os testes.  
S03-08 é pré-requisito para o dogfooding S03-06 ser eficiente.  
S03-06 (dogfooding) é o item central — roda **após** o código estar completo.  
S03-09 é preenchido **após** o dogfooding passar.  
S03-10 fecha o sprint com suite verde.

---

## Commits Atômicos Esperados

```
feat(migrations): índices leads session_id + status + unsynced_kommo [S03-01]
test(telegram): migrar para @pytest.mark.asyncio sem DeprecationWarning [S03-02]
test(telegram): integração telegram/routes.py — 5 testes [S03-03]
refactor(adapters): registry integrado no lifespan + pipeline [S03-04]
docs(claude): documentar cobertura esperada lifespan e clients [S03-05]
feat(faq): gaps cobertos — 8 novos intents de perguntas reais [S03-07]
feat(scripts): inspect_session.py — inspeção de sessão e leads [S03-08]
feat(scripts): dogfood_checklist.py + faq_coverage_check.py [S03-06]
docs(golive): checklist de go-live com critérios objetivos [S03-09]
test(sprint03): suite completa >= 155 testes, 0 falhas, 80% cobertura [S03-10]
```

---

## Critérios de Aceite

- [ ] 3 índices criados em `leads` — verificado via `pg_indexes`
- [ ] Zero `DeprecationWarning` de asyncio no pytest
- [ ] `POST /adapters/telegram/webhook` com texto → 200 e `send_text` chamado
- [ ] `registry.get("whatsapp_cloud")` retorna adapter correto
- [ ] `faq_coverage_check.py` mostra cobertura ≥ 80% das 20 perguntas reais
- [ ] `inspect_session.py --last` mostra sessão, mensagens e lead corretamente
- [ ] `dogfood_checklist.py` executado e relatório salvo em `docs/dogfood/`
- [ ] 20/20 cenários do dogfooding com status documentado
- [ ] `docs/go_live_checklist.md` criado com critérios preenchíveis
- [ ] Cobertura global ≥ 80%
- [ ] 0 testes falhando
- [ ] CI verde na branch `sprint/03-quality`
- [ ] `camisart-sprint-review` executado e aprovado antes do merge
