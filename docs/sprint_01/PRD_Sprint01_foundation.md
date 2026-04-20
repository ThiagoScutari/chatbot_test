# PRD — Sprint 01: Foundation
**Projeto:** Camisart AI  
**Branch:** `sprint/01-foundation`  
**Status:** Aprovação Pendente  
**Origem:** Spec v1.0 — `docs/project_specz.md`  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Esforço |
|---|---|---|---|
| S01-01 | `app/` | Estrutura FastAPI + lifespan + `GET /health` | P |
| S01-02 | `app/models/` | Modelos SQLAlchemy + migration 01 (4 tabelas) | M |
| S01-03 | `app/engines/` | `FAQEngine` + `CampaignEngine` stub + arquivos knowledge | M |
| S01-04 | `app/adapters/` | `WhatsAppCloudAdapter` + endpoints GET/POST webhook com HMAC | M |
| S01-05 | `app/pipeline/` | `MessagePipeline` canal-agnóstica + `StateMachine` básica | M |
| S01-06 | `app/services/` | `SessionService` + `MessageService` + `LeadService` | M |
| S01-07 | `tests/` | Testes completos — ≥70% cobertura em engines/, services/, pipeline/ | G |
| S01-08 | `.github/` | GitHub Actions CI — pytest + coverage + ruff | P |
| S01-09 | VPS + Meta | Deploy Hostinger + ngrok + validação fim-a-fim com Meta | M |

**Legenda:** P = Pequeno (< 2h) · M = Médio (2-4h) · G = Grande (4-8h)

---

## Objetivo do Sprint

Entregar a **pedra angular** do Camisart AI: uma aplicação FastAPI em produção, conectada ao WhatsApp Cloud API da Meta, capaz de receber mensagens, processá-las via FAQEngine determinístico e responder instantaneamente. Ao final deste sprint, a dona da Camisart poderá mandar uma mensagem de teste e receber uma resposta automática do bot.

---

## S01-01 — Estrutura FastAPI + Lifespan + Health

### Motivação
Base do projeto: app FastAPI com lifespan gerenciando ciclo de vida dos engines, configuração via pydantic-settings e endpoint de healthcheck que verifica o banco.

### Implementação

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.config import settings
from app.database import engine, Base
from app.engines.regex_engine import FAQEngine
from app.engines.campaign_engine import CampaignEngine

campaign_engine: CampaignEngine | None = None
faq_engine: FAQEngine | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global campaign_engine, faq_engine
    Base.metadata.create_all(bind=engine)
    campaign_engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign_engine.reload()
    faq_engine = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign_engine)
    yield

app = FastAPI(title="Camisart AI", lifespan=lifespan)
app.include_router(health_router)
app.include_router(whatsapp_router)
app.include_router(admin_router)
```

```python
# app/config.py
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    APP_ENV: str = "development"
    DATABASE_URL: str
    TEST_DATABASE_URL: str = ""
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str
    WHATSAPP_APP_SECRET: str
    WHATSAPP_API_VERSION: str = "v20.0"
    ADMIN_TOKEN: str
    FAQ_JSON_PATH: Path = Path("app/knowledge/faq.json")
    CAMPAIGNS_JSON_PATH: Path = Path("app/knowledge/campaigns.json")
    APP_LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env"}
```

### Testes
- `GET /health` retorna 200 com `{"status": "ok", "db": "up"}`
- `GET /health` com banco inacessível retorna 503

---

## S01-02 — Modelos SQLAlchemy + Migration 01

### Motivação
Criar as 4 tabelas canal-agnósticas definidas em §4.4 do spec: `sessions`, `messages`, `leads`, `audit_logs`. Com UUID PKs, timestamps, soft delete e constraints.

### Tabelas a criar
- `sessions` — conversa por cliente (canal-agnóstica), UNIQUE `(channel_id, channel_user_id)`
- `messages` — log imutável in/out, UNIQUE `(channel_id, channel_message_id)`, campo `matched_intent_id`
- `leads` — orçamentos capturados com campos de sync CRM (NULL na Fase 1)
- `audit_logs` — eventos de domínio auditáveis

### Implementação
Seguir exatamente o schema de §4.4.1–4.4.5 do `project_specz.md`.

```python
# app/migrations/migrate_sprint_01.py — idempotente
def migrate():
    """Cria tabelas do Sprint 01. Idempotente."""
    with engine.connect() as conn:
        # Trigger set_updated_at (idempotente)
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
            $$ LANGUAGE plpgsql;
        """))
        # Tabelas via SQLAlchemy (cria apenas se não existirem)
    Base.metadata.create_all(bind=engine)
    print("✅ Migration Sprint 01 aplicada.")
```

### Testes
- Todas as tabelas existem com colunas corretas após migration
- UNIQUE constraints funcionam (inserção duplicada falha corretamente)
- `audit_logs` é imutável — sem `updated_at`

---

## S01-03 — FAQEngine + CampaignEngine + Knowledge Files

### Motivação
O coração da Fase 1: FAQEngine puro (sem I/O) que casa regex com prioridade e retorna `FAQMatch | None`. CampaignEngine inicializado mas sem campanhas ativas (arquivo `campaigns.json` com lista vazia).

### Implementação
Seguir exatamente §4.2 e §4.7 do spec.

**`app/knowledge/faq.json`** — versão inicial com 9 intents:
`preco_polo`, `preco_jaleco`, `endereco`, `bordado_prazo`, `pedido_minimo`, `prazo_entrega`, `entrega_nacional`, `tamanhos_disponiveis`, `instagram_referencia`

Fallback com botões interativos (3 botões).

**`app/knowledge/campaigns.json`** — sem campanhas ativas:
```json
{ "version": "1.0", "campaigns": [] }
```

**`app/knowledge/products.json`** — catálogo completo de §4.3.

### Testes
- Match correto para cada um dos 9 intents
- Input sem match retorna `None`
- Pattern regex malformado não derruba o app (log + ignora)
- Intent de maior priority ganha quando dois padrões casam
- CampaignEngine com lista vazia não injeta nada no FAQEngine
- Erros ortográficos comuns ("camiza polo", "bordao") são reconhecidos

---

## S01-04 — WhatsAppCloudAdapter + Endpoints Webhook

### Motivação
Única camada que conhece os detalhes do WhatsApp Cloud API. Implementa `ChannelAdapter` ABC com `parse_inbound()`, `send()` e `verify_auth()`.

### Endpoints
- `GET /adapters/whatsapp_cloud/webhook` — handshake com Meta (responde hub.challenge)
- `POST /adapters/whatsapp_cloud/webhook` — recebe mensagens, valida HMAC, chama pipeline

### Contrato de segurança HMAC
```python
# Validação obrigatória — antes de qualquer processamento
import hmac, hashlib
def verify_auth(self, raw_payload: bytes, headers: dict) -> None:
    signature = headers.get("X-Hub-Signature-256", "")
    if not signature.startswith("sha256="):
        raise HTTPException(403)
    expected = "sha256=" + hmac.new(
        settings.WHATSAPP_APP_SECRET.encode(),
        raw_payload,
        hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(403)
```

### Testes
- GET com verify_token correto → 200 + hub.challenge no body
- GET com verify_token errado → 403
- POST com HMAC válido + payload de texto → 200
- POST sem header HMAC → 403
- POST com HMAC inválido → 403
- POST com `wamid` já processado → 200 sem reprocessar (dedup)
- POST com status update (delivered) → 200 sem processamento
- `WhatsAppCloudAdapter.send()` é mockado — nunca chama Meta de verdade nos testes

---

## S01-05 — MessagePipeline + StateMachine básica

### Motivação
O cérebro do bot: canal-agnóstico, recebe `InboundMessage` e devolve `OutboundMessage`. StateMachine cobre o fluxo básico da Fase 1: INICIO → MENU → handoffs.

### Fluxo básico implementado
```
INICIO ──► AGUARDA_NOME ──► MENU ─┬─► AGUARDA_PEDIDO ──► FIM
                                  ├─► ENVIA_CATALOGO ──► FIM
                                  ├─► COLETA_ORCAMENTO_SEGMENTO ──► ...
                                  └─► ENCAMINHAR_HUMANO ──► FIM
```

Em qualquer estado: `FAQEngine.match()` é tentado primeiro. Match de alta prioridade (≥50) responde sem alterar estado.

### Contrato inviolável
```python
# MessagePipeline.process() — assinatura final
async def process(
    self,
    inbound: InboundMessage,
    db: Session,
) -> OutboundMessage | None:
    # NÃO conhece WhatsApp, Kommo, Instagram
    # Apenas InboundMessage → OutboundMessage
```

### Testes
- Primeira mensagem cria sessão no estado `INICIO`
- Sessão existente reutiliza estado atual
- Session timeout de 2h reseta estado e preserva `nome_cliente`
- FAQEngine match no estado MENU responde sem mudar estado
- Fallback correto quando sem match
- Nenhum import de `app.adapters.whatsapp_cloud` em `pipeline/` ou `engines/`

---

## S01-06 — SessionService + MessageService + LeadService

### Motivação
Camada de persistência separada da lógica. Services são os únicos que fazem I/O com o banco.

### Implementação

**`SessionService`:**
- `get_or_create_session()` — com detecção de timeout (2h) e reset de estado
- `check_rate_limit()` — 10 msgs/min via session_data
- `update_state()` — persiste novo estado + `last_interaction_at`

**`MessageService`:**
- `record_inbound()` — persiste mensagem com `matched_intent_id` e `state_before/after`
- `record_outbound()` — persiste resposta enviada

**`LeadService`:**
- `capture()` — cria Lead com `status='novo'`, usa `campaign_engine.default_segmento()` como fallback
- `write_audit_log()` — registra `lead.captured` antes do commit

### Testes
- `get_or_create_session()` cria sessão nova corretamente
- Session timeout reseta estado e preserva nome
- `check_rate_limit()` bloqueia na 11ª mensagem no minuto
- `record_inbound()` persiste `matched_intent_id` corretamente
- `capture()` cria lead com segmento de campanha quando ativo
- `write_audit_log()` é chamado antes do commit (ordem garantida)

---

## S01-07 — Testes Completos

### Meta de cobertura
- `app/engines/` ≥ 70%
- `app/services/` ≥ 70%
- `app/pipeline/` ≥ 70%
- `app/adapters/` ≥ 60% (webhook endpoints cobertos)

### Arquivos de teste a criar
```
tests/
  conftest.py                   ← fixtures: client, db, test_session, mock_whatsapp_client
  test_health.py                ← 2 testes
  test_webhook.py               ← 8 testes (HMAC, dedup, status update)
  test_regex_engine.py          ← 12 testes (9 intents + edge cases)
  test_campaign_engine.py       ← 8 testes (já especificados em §4.7.6 do spec)
  test_state_machine.py         ← 8 testes (estados básicos + timeout)
  test_session_service.py       ← 6 testes
  test_message_service.py       ← 4 testes
  test_lead_service.py          ← 4 testes
  test_admin.py                 ← 4 testes (reload + status + auth)
  fixtures/
    whatsapp_payloads.json      ← payloads reais da Meta para testes
```

**Total alvo: ≥ 56 testes, 0 falhas.**

---

## S01-08 — GitHub Actions CI

### Motivação
Todo PR deve ter CI verde antes de revisão. Obrigatório por Regra 3 do projeto.

### Implementação

```yaml
# .github/workflows/ci.yml
name: CI — Camisart AI

on:
  push:
    branches: ["sprint/*", "main"]
  pull_request:
    branches: ["main"]

jobs:
  test:
    name: pytest + ruff
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: camisart_test_db
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Lint — ruff
        run: ruff check app/

      - name: Test — pytest
        run: pytest tests/ -v --cov=app --cov-report=term-missing --cov-fail-under=65
        env:
          APP_ENV: test
          DATABASE_URL: postgresql://postgres:test@localhost:5432/camisart_test_db
          TEST_DATABASE_URL: postgresql://postgres:test@localhost:5432/camisart_test_db
          WHATSAPP_VERIFY_TOKEN: test-verify-token
          WHATSAPP_APP_SECRET: test-app-secret-32-chars-minimum-ok
          ADMIN_TOKEN: test-admin-token-32-chars-minimum-ok
          CAMPAIGNS_JSON_PATH: app/knowledge/campaigns.json
          FAQ_JSON_PATH: app/knowledge/faq.json
```

### Testes do CI
- CI passa em push para `sprint/01-foundation`
- CI passa em PR para `main`
- PR não mergeável se CI falhar (configurar branch protection em `main`)

---

## S01-09 — Deploy VPS + Validação Fim-a-Fim

### Motivação
Critério de aceite final: a dona da Camisart envia uma mensagem de WhatsApp e recebe resposta do bot em < 5 segundos.

### Passos
1. Deploy na VPS Hostinger (via `git pull + systemctl restart`)
2. Certificado TLS via Let's Encrypt (certbot)
3. Nginx configurado como reverse proxy
4. Webhook registrado na Meta (URL pública)
5. Número de teste adicionado no sandbox da Meta
6. Teste manual com mensagem "qual o preço da polo?"

### Teste de validação local (pré-VPS)
Usar ngrok para expor o servidor local:
```bash
uvicorn app.main:app --reload --port 8000 &
ngrok http 8000
# Configurar URL ngrok no webhook Meta
# Enviar mensagem do WhatsApp para o número registrado
# Verificar que resposta chega em < 5s
```

---

## Ordem de Execução

```
S01-01 → S01-02 → S01-03 → S01-04 → S01-05 → S01-06 → S01-07 → S01-08 → S01-09
```

S01-01 e S01-02 são bloqueadores para todos os demais.
S01-03, S01-04, S01-06 podem ser desenvolvidos em paralelo após S01-02.
S01-05 depende de S01-03, S01-04 e S01-06.
S01-07 acompanha cada item (testes escritos junto com cada feature).
S01-08 pode ser feito após S01-01.
S01-09 só após todos os outros.

---

## Commits Atômicos Esperados

```
feat(app): estrutura FastAPI + lifespan + config [S01-01]
feat(health): GET /health com verificação de banco [S01-01]
feat(models): tabelas sessions, messages, leads, audit_logs [S01-02]
feat(migrations): migration Sprint 01 idempotente com rollback [S01-02]
feat(engine): FAQEngine regex multipadrão com priority [S01-03]
feat(engine): CampaignEngine stub + campaigns.json inicial [S01-03]
feat(knowledge): faq.json com 9 intents + products.json [S01-03]
feat(adapter): ChannelAdapter ABC + InboundMessage/OutboundMessage [S01-04]
feat(adapter): WhatsAppCloudAdapter com HMAC + dedup [S01-04]
feat(pipeline): MessagePipeline canal-agnóstica [S01-05]
feat(engine): StateMachine básica INICIO→MENU→handoffs [S01-05]
feat(services): SessionService com timeout e rate limit [S01-06]
feat(services): MessageService + LeadService com audit log [S01-06]
test(sprint01): suite completa 56+ testes, 0 falhas [S01-07]
devops(ci): GitHub Actions pytest + ruff [S01-08]
devops(deploy): VPS Hostinger + systemd + nginx + certbot [S01-09]
```

---

## Critérios de Aceite

- [ ] `GET /health` retorna 200 em produção
- [ ] Webhook Meta verificado e recebendo mensagens
- [ ] Mensagem "qual o preço da polo?" respondida corretamente em < 5s
- [ ] Os 9 intents do FAQ respondidos corretamente nos testes
- [ ] Mensagem com erro ortográfico ("camiza polo") reconhecida corretamente
- [ ] Deduplicação funcionando — reenvio da Meta não duplica resposta
- [ ] HMAC inválido retorna 403
- [ ] Fluxo de captura de lead cria registro no banco com `status='novo'`
- [ ] Session timeout de 2h reseta estado corretamente
- [ ] Nenhum módulo fora de `app/adapters/whatsapp_cloud/` importa símbolos da Meta
- [ ] Cobertura ≥ 70% nas camadas `engines/`, `services/`, `pipeline/`
- [ ] CI verde em `sprint/01-foundation` antes do PR
- [ ] `camisart-sprint-review` executado e aprovado antes do merge
- [ ] Dona da Camisart validou o fluxo em pelo menos 1 sessão de teste manual
