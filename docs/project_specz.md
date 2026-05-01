# Camisart AI — Especificação Técnica Oficial

**Projeto:** Camisart AI — Chatbot de atendimento via WhatsApp para Camisart Belém
**Status:** Spec ativa — Fase 1 concluída, Sprint NPS entregue
**Versão:** 1.1
**Data:** 2026-05-01
**Autor:** Thiago Scutari
**Escopo desta versão:** Fase 1 especificada em profundidade. Sprint NPS adicionado (§4.8 e §9.0). Fases 2–4 apenas como roadmap arquitetural.
**Changelog v1.1:** Sprint NPS — bot de pesquisa de satisfação, tabela `nps_responses`, dashboard HTML de análise. Ver `docs/sprint_13/02_PRD.md`.

---

## Índice

1. [Visão do Produto](#1-visão-do-produto)
2. [Arquitetura de 3 Camadas — Contrato Macro](#2-arquitetura-de-3-camadas--contrato-macro)
   - 2.1. Contratos invioláveis
   - 2.2. Estratégia de canal (construir na nossa casa, migrar depois)
   - 2.3. Estratégia de migração para Kommo
   - 2.4. Channel Adapter Pattern
3. [Stack Técnica](#3-stack-técnica)
4. [Fase 1 — Especificação Técnica Profunda](#4-fase-1--especificação-técnica-profunda)
   - 4.1. [Fluxo de Mensagem Ponta-a-Ponta](#41-fluxo-de-mensagem-ponta-a-ponta)
     - 4.1.1. Proteções do webhook (dedup e rate limiting)
   - 4.2. [FAQ Engine — Regex + Respostas](#42-faq-engine--regex--respostas)
     - 4.2.1. WhatsApp Interactive Messages
     - 4.2.2. Métricas de cobertura e gatilho para Fase 2
     - 4.2.3. Intents adicionais baseados no Instagram
   - 4.3. [Catálogo Camisart — Dados de Produto](#43-catálogo-camisart--dados-de-produto)
   - 4.4. [Modelo de Dados PostgreSQL](#44-modelo-de-dados-postgresql)
   - 4.5. [Máquina de Estados — Evolução do core/](#45-máquina-de-estados--evolução-do-core)
     - 4.5.1. Session timeout e reset
     - 4.5.2. Fluxo de orçamento com qualificação
   - 4.6. [Contratos de API Internos](#46-contratos-de-api-internos)
   - 4.7. [Campaign Engine — Ações Sazonais Configuráveis](#47-campaign-engine--ações-sazonais-configuráveis)
     - 4.7.1. Design principles
     - 4.7.2. Schema de `campaigns.json`
     - 4.7.3. Código do `CampaignEngine`
     - 4.7.4. Integração com FAQEngine e Pipeline
     - 4.7.5. Endpoints admin
     - 4.7.6. Inicialização via lifespan
     - 4.7.7. Testes
     - 4.7.8. Guia operacional
   - 4.8. [NPS Bot — Pesquisa de Satisfação](#48-nps-bot--pesquisa-de-satisfação) ← **v1.1**
5. [Integração WhatsApp Cloud API — Onboarding](#5-integração-whatsapp-cloud-api--onboarding)
6. [Ambientes e Deploy](#6-ambientes-e-deploy)
7. [Qualidade — Testes, Logs e Observabilidade](#7-qualidade--testes-logs-e-observabilidade)
8. [Workflow de Desenvolvimento](#8-workflow-de-desenvolvimento)
9. [Roadmap — Fases 2, 3 e 4](#9-roadmap--fases-2-3-e-4)
   - 9.0. [Sprint NPS — Feedback Loop](#90-sprint-nps--feedback-loop) ← **v1.1**
   - 9.1. Fase 2 — LLM Router
   - 9.2. Fase 3 — RAG
   - 9.3. Fase 4 — Integrações Externas
10. [Critérios de Aceite da Fase 1](#10-critérios-de-aceite-da-fase-1)
11. [Glossário e Referências](#11-glossário-e-referências)

---

## 1. Visão do Produto

### 1.1. Problema Real

A Camisart Belém é uma malharia de uniformes (Av. Magalhães Barata, 445 — Belém/PA) com atendimento nacional via WhatsApp `(91) 99180-0637`. A análise de 190 posts do Instagram [@camisart_belem](https://www.instagram.com/camisart_belem/) e 427 comentários ([docs/relatorio_instagram_camisart.md](relatorio_instagram_camisart.md)) revelou:

- **38,4% das perguntas no Instagram são sobre preço** — e raramente respondidas publicamente.
- **O gargalo declarado pelos clientes é o WhatsApp:** *"desrespeitoso, ficamos horas esperando"*, *"só dá caixa postal"*, *"ninguém responde msg no Instagram"*.
- O fluxo de perda de venda é: cliente comenta → sem resposta → vai pro WhatsApp → aguarda horas → desiste.

### 1.2. Proposta de Valor

Um chatbot no WhatsApp Business que responde **instantaneamente** às perguntas de maior volume (preço, tamanhos, cores, pedido mínimo, bordado, prazo de entrega, endereço), faz **triagem inteligente** (perguntas resolvidas sozinho vs. encaminhar para humano), e captura **leads estruturados** para orçamentos de uniformes corporativos.

### 1.2.1. Ações Sazonais — COP30 como Caso de Uso Original

A ideia de campanhas sazonais surgiu do contexto da **COP30** (realizada em Belém em novembro de 2025), que gerou demanda concentrada por uniformes corporativos. O mecanismo desenvolvido para capturar esse tipo de oportunidade é o **Campaign Engine** (§4.7), que permite criar campanhas para qualquer evento — Copa do Mundo 2026, Natal, Volta às Aulas, Carnaval, eventos locais — sem nenhum deploy de código.

O campo `segmento` na tabela `leads` (§4.4.3) aceita valores como `"cop30"`, `"copa_2026"`, `"natal"`, `"volta_aulas"` para segmentação e relatórios futuros.

### 1.3. Métricas de Sucesso da Fase 1

| Métrica | Baseline (hoje) | Meta Fase 1 |
|---|---|---|
| Tempo de 1ª resposta no WhatsApp | horas | < 5 segundos |
| % de perguntas de preço respondidas sozinho | 0% | ≥ 80% |
| Leads estruturados capturados/semana | 0 | ≥ 10 |
| Disponibilidade do bot | — | ≥ 99% (VPS) |
| **NPS Score** (Sprint NPS) | não medido | baseline coletado | ← v1.1

### 1.4. Fora do Escopo da Fase 1

- Compreensão de linguagem livre (Camada 2 — LLM). Na Fase 1, respostas são 100% determinísticas via regex.
- RAG sobre catálogo (Camada 3). PDFs do catálogo são enviados como arquivos estáticos, não consultados por IA.
- Pagamento, checkout, reserva de estoque.
- Integração com Instagram DM ou outros canais além do WhatsApp.
- UI de administração. Preços e FAQs mudam via edição de JSON + commit + deploy.
- **Integração com CRM externo** (Kommo, RD Station). Fase 1 apenas **persiste** leads no Postgres com os campos necessários para sincronização futura.

### 1.5. Ecossistema da Cliente — Ferramentas em Uso

A Camisart usa (ou pretende usar) as seguintes ferramentas que terão interface com o bot em algum momento:

| Ferramenta | Papel esperado | Quando integrar |
|---|---|---|
| **Kommo** (CRM + WhatsApp nativo) | Destino dos leads qualificados, pipeline de vendas, histórico de cliente | Fase 4 (a definir cenário — ver §2.1) |
| **RD Station** (automação de marketing) | Nutrição de leads, campanhas por segmento, lead scoring | Fase 4 |

**Importante:** a arquitetura da Fase 1 deve preservar a possibilidade de qualquer um dos dois sistemas virar **destino de sincronização** (via API pública dessas plataformas) ou **fonte de contexto** (o bot consulta o Kommo antes de responder para saber quem é o cliente). Ver regras em §2.1.

---

## 2. Arquitetura de 3 Camadas — Contrato Macro

O [Camisart_AI_Blueprint](Camisart_AI_Blueprint.pdf) define uma arquitetura em 3 camadas. **Apenas a Camada 1 é implementada na Fase 1.** As camadas seguintes ficam documentadas aqui para garantir que a Fase 1 não feche portas arquiteturais.

```
┌───────────────────────────────────────────────────────────────────────┐
│  WhatsApp Cloud API (Meta) ⇄ Webhook /whatsapp/webhook (FastAPI)       │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  CAMADA 1 — Regex + FAQ Engine (FASE 1) ← ÚNICA IMPLEMENTADA          │
│  - Reconhecimento por padrões de palavras-chave                       │
│  - Resposta de JSON estático + template                               │
│  - Latência < 200ms, zero custo de IA, zero alucinação                │
└───────────────────────────────────────────────────────────────────────┘
                                 │  (fallback quando nenhum regex casa)
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  CAMADA 2 — LLM para Intenção (FASE 2, não implementada)              │
│  - Compreensão em linguagem livre + geração de orçamentos             │
│  - Interface: LLMRouter.classify_intent(msg) → intent_id              │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│  CAMADA 3 — RAG (FASE 3, não implementada)                            │
│  - Consulta vetorial sobre PDFs segmentados + histórico de pedidos     │
│  - Interface: RAGEngine.query(intent, context) → answer               │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
                    Fila humana (operador Camisart)
```

### 2.1. Contratos que a Fase 1 NÃO pode violar

Para não bloquear as Fases 2–4 e a **migração futura para Kommo** (ver §2.3), a Fase 1 obedece a estas regras:

1. **Toda mensagem recebida é persistida** em `messages` antes de qualquer processamento. Isso permite treinar LLMs e popular RAG depois.
2. **O `FAQEngine` é um módulo desacoplado** (`app/engines/regex_engine.py`), não misturado aos handlers da máquina de estados. Na Fase 2, um `LLMRouter` adicional plugará no mesmo ponto de entrada.
3. **A sessão de conversa é opaca** — qualquer lógica futura pode adicionar campos ao dicionário `session_data` sem quebrar retrocompatibilidade.
4. **Identificadores são UUIDs** (não autoincrement), para permitir replicação e merge de dados entre ambientes, e para não gerar conflito com PKs de sistemas externos.
5. **Leads carregam metadata de sincronização externa** (`external_crm_id`, `synced_to_kommo_at`, `synced_to_rdstation_at`, `sync_metadata`). Fase 1 só preenche `NULL`; Fase 4 popula. Migrar um schema já em produção é caro — melhor prever agora.
6. **Eventos de domínio são auditáveis** via `audit_logs` — toda criação/atualização de `Lead` e `Session` gera linha em `audit_logs`. Isso dá rastreabilidade e permite uma arquitetura de *event sourcing* leve para dispararmos webhooks para CRM no futuro.
7. **Isolamento de canal (Channel Adapter Pattern)** — o cérebro do bot (engines + state machine + services) NÃO pode conhecer detalhes do WhatsApp Cloud API. A camada `app/adapters/` é a ÚNICA que sabe falar com a Meta. Trocar o adapter (para Kommo, Instagram DM, SMS, etc.) não pode exigir tocar em `engines/` ou `services/`. Ver padrão em §2.4.

### 2.2. Estratégia de Canal — "Construir na Nossa Casa, Migrar Depois"

**Situação atual:** a Camisart já recebe WhatsApp **dentro do Kommo** (o número `(91) 99180-0637` está vinculado ao Kommo via integração nativa da ferramenta).

**Decisão estratégica travada:**

> Construímos a Fase 1 no nosso próprio stack (FastAPI + WhatsApp Cloud API direto). Validamos, iteramos e medimos impacto com total liberdade. Quando o produto estiver maduro, migramos/integramos ao Kommo — que é a ferramenta oficial da cliente. A arquitetura é projetada agora para que essa migração custe o mínimo possível.

**Consequências:**

1. A Camisart precisará destinar **um número novo** (ou migrar o atual) para o bot — porque um número WhatsApp não pode estar simultaneamente no Kommo e no Cloud API direto.
2. Durante a Fase 1, Kommo e bot operam em **canais paralelos**. Pode ser necessário comunicar aos clientes da Camisart que existem dois números (ou direcionar toda entrada pública para o novo número).
3. Um plano de migração formal é definido em §2.3.

### 2.3. Estratégia de Migração para Kommo (Fase 4+)

Quando o produto estiver validado, a migração acontece em um dos 3 modos — ainda a definir em conjunto com a cliente:

| Modo | Como funciona | Esforço |
|---|---|---|
| **M1 — Bot como serviço externo chamado pelo Kommo** | Kommo recebe o WhatsApp; usa *webhook outbound* do Kommo para POSTar cada mensagem na nossa API (`/kommo/inbound`); nossa resposta volta para o Kommo, que envia ao cliente | **Baixo** — só adicionamos um novo adapter; cérebro inteiro reaproveitado |
| **M2 — Salesbot do Kommo (DSL nativa)** | Reescrevemos fluxos simples como Salesbot; fluxos complexos chamam nossa API via webhook step | **Médio** — precisa recriar fluxos em DSL; cérebro reaproveitado para casos avançados |
| **M3 — Bot continua como canal primário + Kommo recebe leads qualificados** | Bot atende, qualifica, captura lead; `KommoClient` cria o Lead no pipeline do Kommo via API; atendente humano assume lá | **Baixo** — é o que o spec já prepara em §4.4.3 |

**Ponto crítico:** M1 e M3 são suportadas pela arquitetura atual sem reescrita. M2 exige refazer fluxos, mas o cérebro (engine + services) continua reutilizável por webhook steps. O padrão **Channel Adapter** (§2.4) é o que garante isso.

### 2.4. Channel Adapter Pattern — O Contrato Arquitetural-Chave

Toda mensagem que entra no sistema, venha de onde vier, é convertida por um **Adapter** em um objeto interno padronizado (`InboundMessage`). Toda resposta é convertida por um **Adapter** de volta para o formato do canal. O cérebro não conhece canais.

```
┌─────────────────────────┐      ┌─────────────────────────┐
│ WhatsApp Cloud API      │      │ Kommo webhook outbound  │
│ Meta → POST webhook     │      │ (FASE 4)                │
└───────────┬─────────────┘      └──────────┬──────────────┘
            │                                 │
            ▼                                 ▼
┌──────────────────────────┐   ┌──────────────────────────┐
│ WhatsAppCloudAdapter     │   │ KommoAdapter (FASE 4)    │
│ - verifica HMAC da Meta  │   │ - verifica auth Kommo    │
│ - Meta payload → Inbound │   │ - Kommo payload → Inbound│
│ - envia via Graph API    │   │ - envia via Kommo API    │
└──────────┬───────────────┘   └──────────┬───────────────┘
           │                               │
           └──────────┬────────────────────┘
                      │ InboundMessage (objeto interno)
                      ▼
          ┌────────────────────────────────┐
          │ MessagePipeline (core)         │
          │ services → engines → services  │
          │   (NÃO sabe de canal)          │
          └──────────┬─────────────────────┘
                      │ OutboundMessage
                      ▼
              (roteia para o adapter de origem)
```

**Interface abstrata — `app/adapters/base.py`:**

```python
from abc import ABC, abstractmethod
from app.schemas.messaging import InboundMessage, OutboundMessage

class ChannelAdapter(ABC):
    """Contrato único que todo canal deve implementar."""

    channel_id: str  # 'whatsapp_cloud', 'kommo', 'instagram_dm', ...

    @abstractmethod
    async def parse_inbound(self, raw_payload: dict, headers: dict) -> InboundMessage | None:
        """Converte payload do canal em mensagem interna. Retorna None se for
        apenas um event de status (delivery receipt) que não requer processamento."""

    @abstractmethod
    async def send(self, outbound: OutboundMessage) -> str:
        """Envia mensagem. Retorna id externo (ex: wamid da Meta, message_id do Kommo)."""

    @abstractmethod
    def verify_auth(self, raw_payload: bytes, headers: dict) -> None:
        """Valida HMAC/token. Levanta HTTPException 403 se inválido."""
```

**InboundMessage (objeto canônico):**

```python
class InboundMessage(BaseModel):
    channel_id: Literal["whatsapp_cloud", "kommo", "instagram_dm"]
    channel_message_id: str                  # wamid, kommo msg id, etc.
    channel_user_id: str                     # wa_id, kommo contact id, etc.
    display_name: str | None                  # nome do usuário como o canal reporta
    content: str                              # texto da mensagem
    timestamp: datetime
    raw_payload: dict                         # payload original preservado (log + debug)
```

**Endpoints atuais com adapter explícito:**

```
POST /adapters/whatsapp_cloud/webhook  →  WhatsAppCloudAdapter.parse_inbound(...)
GET  /adapters/whatsapp_cloud/webhook  →  WhatsAppCloudAdapter.verify_handshake(...)
```

Nota: o path atual `/whatsapp/webhook` (em §4.6) fica como **alias** para compatibilidade, mas o path canônico é `/adapters/whatsapp_cloud/webhook`. A Fase 4 adiciona `/adapters/kommo/webhook` sem mexer em nada mais.

**Por que esse contrato é inegociável:** se não aplicarmos isso na Fase 1, migrar para Kommo depois vai exigir refatorar services, engines e state_machine — justamente o código que mais testes carregará. Uma hora de desenho hoje economiza semanas depois.

---

## 3. Stack Técnica

| Camada | Tecnologia | Justificativa |
|---|---|---|
| Linguagem | Python 3.12+ | Padrão dos projetos do arquiteto |
| Framework HTTP | **FastAPI** | Async nativo (ideal para webhooks), validação Pydantic, OpenAPI automático. Padrão ConfexAI (`confexai-architecture-decisions` ADR-002: monolito FastAPI) |
| Banco de dados | **PostgreSQL 15+** | Padrão dos projetos do arquiteto; VPS Hostinger já dispõe |
| ORM | SQLAlchemy 2.x + Alembic (ou migrations manuais) | Consistente com ConfexAI |
| Validação | Pydantic v2 com `Literal` types | Obrigatório por `confexai-api-contracts` |
| Canal | WhatsApp Cloud API (Meta oficial) | Decisão travada — sem risco de banimento |
| Servidor ASGI | Uvicorn + Gunicorn (prod) | Padrão FastAPI |
| Testes | pytest + pytest-asyncio | Padrão `confexai-testing-standards` |
| Processo prod | systemd unit + nginx reverse proxy | Padrão VPS Hostinger |
| TLS | Let's Encrypt (certbot) | Webhook WhatsApp exige HTTPS válido |
| Logs | stdlib `logging` + rotação em arquivo | Simplicidade na Fase 1; ELK/Loki na Fase 4 |

### 3.1. Dependências Python

```
# requirements.txt — Fase 1
fastapi>=0.110
uvicorn[standard]>=0.29
gunicorn>=21.2
sqlalchemy>=2.0
psycopg2-binary>=2.9
alembic>=1.13
pydantic>=2.6
pydantic-settings>=2.2
httpx>=0.27                 # chamadas à Meta Graph API + TestClient async
python-multipart>=0.0.9     # uploads
python-dotenv>=1.0
pytest>=8.0
pytest-asyncio>=0.23
pytest-cov>=4.1
```

### 3.2. Estrutura de Diretórios (alvo da Fase 1)

```
chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py                       ← FastAPI app + lifespan
│   ├── config.py                     ← Settings (pydantic-settings)
│   ├── database.py                   ← engine, SessionLocal, Base
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── health.py                 ← GET /health
│   │   └── admin.py                  ← POST /admin/campaigns/reload, GET /admin/campaigns/status
│   │
│   ├── adapters/                     ← ÚNICA camada que conhece canais externos
│   │   ├── __init__.py
│   │   ├── base.py                   ← ChannelAdapter (ABC) + InboundMessage/OutboundMessage
│   │   ├── registry.py               ← resolve channel_id → adapter
│   │   └── whatsapp_cloud/
│   │       ├── __init__.py
│   │       ├── adapter.py            ← WhatsAppCloudAdapter(ChannelAdapter)
│   │       ├── client.py             ← HTTP client para Meta Graph API
│   │       ├── routes.py             ← /adapters/whatsapp_cloud/webhook (GET+POST)
│   │       └── schemas.py            ← Pydantic dos payloads da Meta
│   │                                  (Fase 4: app/adapters/kommo/ com a mesma forma)
│   │
│   ├── engines/
│   │   ├── __init__.py
│   │   ├── regex_engine.py           ← FAQEngine: match(msg) → response
│   │   ├── campaign_engine.py        ← CampaignEngine: campanhas sazonais
│   │   └── state_machine.py          ← evolução de core/handlers.py
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   └── message_pipeline.py       ← orquestra inbound→engine→outbound (agnóstico de canal)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── session_service.py        ← persistência de sessões
│   │   ├── message_service.py        ← persistência de mensagens in/out
│   │   └── lead_service.py           ← captura de orçamentos
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                   ← Base + mixins (TimestampMixin, SoftDeleteMixin)
│   │   ├── session.py                ← Session (conversa)
│   │   ├── message.py                ← Message (in/out)
│   │   ├── lead.py                   ← Lead (orçamento capturado)
│   │   └── audit_log.py              ← AuditLog
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── whatsapp.py               ← payloads do webhook Meta
│   │   ├── response.py               ← StandardResponse
│   │   └── lead.py
│   │
│   ├── knowledge/
│   │   ├── faq.json                  ← padrões regex → resposta (permanente)
│   │   ├── products.json             ← catálogo Camisart
│   │   ├── templates.json            ← templates de saudação, despedida, erros
│   │   └── campaigns.json            ← campanhas sazonais (editável sem deploy)
│   │
│   └── migrations/
│       ├── migrate_sprint_01.py
│       └── rollback_sprint_01.py
│
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_webhook.py
│   ├── test_regex_engine.py
│   ├── test_campaign_engine.py
│   ├── test_state_machine.py
│   ├── test_whatsapp_client.py
│   ├── test_session_service.py
│   ├── test_lead_service.py
│   └── fixtures/
│       └── whatsapp_payloads.json
│
├── docs/
│   ├── project_specz.md                              ← este documento
│   ├── Camisart_AI_Blueprint.pdf
│   ├── relatorio_instagram_camisart.md
│   ├── PRD_Sprint01_foundation.md                    ← a ser criado
│   ├── decisions/
│   │   └── ADRs.md                                   ← a ser criado
│   └── superpowers/
│       └── plans/ & specs/                           ← planos de implementação
│
├── .env.example
├── .gitignore
├── pyrightconfig.json
├── pytest.ini
├── requirements.txt
└── README.md
```

### 3.3. Padrões de Código Herdados das Skills

Ver skills em `.claude/skills/`. Resumo operacional:

| Padrão | Skill de referência |
|---|---|
| Soft delete universal (`is_archived`, `deleted_at`) | `confexai-architecture-decisions` ADR-003 |
| Migrations idempotentes com rollback | ADR-004 |
| `StandardResponse(data=...)` em toda rota | `confexai-api-contracts` |
| `Literal` types em Pydantic para valores fixos | ADR-012 |
| `write_audit_log` antes de `db.commit()` | `sgp-sprint-review` §2 |
| Banco de teste separado (`camisart_test_db`) | `confexai-testing-standards` |
| Mocks obrigatórios para APIs externas (Meta) | `confexai-testing-standards` |
| Auditoria `sgp-sprint-review` antes do merge | ADR-015 |

---

## 4. Fase 1 — Especificação Técnica Profunda

### 4.1. Fluxo de Mensagem Ponta-a-Ponta

**Fluxo canônico (independente de canal):**

```
1.  Canal externo (Meta Cloud API hoje; Kommo na Fase 4) faz POST no
    endpoint do adapter: /adapters/{channel_id}/webhook
2.  Adapter.verify_auth(raw_body, headers)  → valida HMAC / token
3.  Adapter.parse_inbound(payload, headers) → InboundMessage canônica | None
    (retorna None se for status update como 'delivered', 'read')
4.  MessagePipeline.process(inbound) é chamado — e é aqui que o cérebro
    começa, sem qualquer conhecimento do canal:

    4.1. session_service.get_or_create(channel_id, channel_user_id) → Session
    4.2. Idempotência: se messages.channel_message_id já existe, retorna 200
    4.3. message_service.persist_inbound(session, inbound) → Message (in)
    4.4. state_machine.handle(inbound.content, session, faq_engine) → HandleResult
         - dentro do handle, FAQEngine.match() é tentado primeiro
    4.5. message_service.persist_outbound(session, result.response) → Message (out)
    4.6. db.commit() com audit_log.write(...)
    4.7. Retorna OutboundMessage(channel_id, channel_user_id, response)

5.  Adapter.send(outbound) → envia via API do canal, retorna id externo
6.  Pipeline grava o id externo em messages.channel_message_id da linha 'out'
7.  Endpoint retorna 200 OK ao canal (< 20s, obrigatório para Meta)
```

**Regras de ouro (continuam válidas):**

- **Responder < 20s** (timeout da Meta).
- **Idempotência** via `messages.channel_message_id` UNIQUE — se a Meta reenviar, retornamos 200 sem reprocessar.
- **Async:** endpoint do adapter é `async def`. Chamadas HTTP via `httpx.AsyncClient`.
- **Ordenação garantida:** lock da sessão por `channel_id + channel_user_id` serializa mensagens concorrentes do mesmo cliente.
- **Nenhum módulo abaixo de `app/adapters/` importa de `app/adapters/whatsapp_cloud/`.** Sempre via `InboundMessage` / `OutboundMessage`.

#### 4.1.1. Proteções do Webhook — Dedup e Rate Limiting

**Deduplicação** — garantida pelo UNIQUE `(channel_id, channel_message_id)` em `messages` (§4.4.2). A checagem acontece **antes** de adquirir o lock da sessão, para não bloquear processamento de outros clientes em casos de reenvio em burst da Meta.

**Rate limiting por `channel_user_id`** — um cliente não processa mais que **10 mensagens/minuto**. Implementação sem Redis na Fase 1, usando `session_data` como janela deslizante:

```python
# app/services/session_service.py
from datetime import datetime, timedelta

RATE_LIMIT_WINDOW = timedelta(minutes=1)
RATE_LIMIT_MAX_MSGS = 10

def check_rate_limit(session: SessionModel) -> bool:
    """Retorna True se permitido, False se excedeu o limite."""
    now = datetime.utcnow()
    window_start_iso = session.session_data.get("rl_window_start")
    count = session.session_data.get("rl_count", 0)

    if not window_start_iso or now - datetime.fromisoformat(window_start_iso) > RATE_LIMIT_WINDOW:
        # Nova janela
        session.session_data["rl_window_start"] = now.isoformat()
        session.session_data["rl_count"] = 1
        return True

    session.session_data["rl_count"] = count + 1
    return (count + 1) <= RATE_LIMIT_MAX_MSGS
```

Quando bloqueado, o pipeline responde com uma única mensagem informando o limite e não avança estado. Redis entra na Fase 4 (quando a carga justificar).

**Regras de ouro:**

- **Responder < 20s** (timeout da Meta).
- **Idempotência:** a Meta reenviará webhooks se não receber 200. O `message_id` da Meta é único — se já existe em `messages.whatsapp_message_id`, retornar 200 sem reprocessar.
- **Async:** endpoint `/whatsapp/webhook` é `async def`. Chamadas HTTP à Graph API via `httpx.AsyncClient`.
- **Ordenação garantida:** o `lock` da sessão (por `wa_id`) serializa mensagens concorrentes do mesmo cliente.

### 4.2. FAQ Engine — Regex + Respostas

O `FAQEngine` é puro: recebe uma string, retorna `FAQMatch | None`. Sem efeitos colaterais, sem I/O. Fácil de testar.

**Schema Pydantic (`app/engines/regex_engine.py`):**

Resposta estruturada para suportar `text`, `buttons` e `list` da WhatsApp Cloud API (ver §4.2.1).

```python
from typing import Literal
from pydantic import BaseModel, Field

class ResponseButton(BaseModel):
    id: str                   # máx 256 chars — retornado como conteúdo quando clicado
    title: str                # máx 20 chars

class ResponseListItem(BaseModel):
    id: str
    title: str                # máx 24 chars
    description: str | None = None   # máx 72 chars

class FAQResponse(BaseModel):
    type: Literal["text", "buttons", "list"]
    body: str                                          # texto principal (máx 1024 chars em interactive)
    buttons: list[ResponseButton] | None = None        # se type == "buttons" (2-3 itens)
    list_items: list[ResponseListItem] | None = None   # se type == "list" (1-10 itens)
    list_button_label: str | None = None               # label do botão que abre a lista (máx 20 chars)
    footer: str | None = None                          # rodapé opcional (máx 60 chars)

class FAQIntent(BaseModel):
    id: str
    priority: int = 0
    patterns: list[str]
    response: FAQResponse
    follow_up_state: Literal["menu", "aguarda_pedido", "aguarda_orcamento"] | None = None

class FAQMatch(BaseModel):
    intent_id: str
    response: FAQResponse
    follow_up_state: str | None
```

**Arquivo de conhecimento: `app/knowledge/faq.json`** (exemplos — lista completa em §4.2.3)

```json
{
  "version": "1.0",
  "intents": [
    {
      "id": "preco_polo",
      "priority": 10,
      "patterns": [
        "\\b(pre[çc]o|valor|quanto)\\b.*\\bpolo\\b",
        "\\bpolo\\b.*\\b(pre[çc]o|valor|quanto)\\b"
      ],
      "response": {
        "type": "text",
        "body": "Olá! A nossa *Polo em malha Piquet* custa:\n• *R$ 45,00* no varejo\n• *R$ 42,00* no atacado (12+ peças)\n\nFazemos bordado da sua logo sem pedido mínimo. Deseja um orçamento?"
      },
      "follow_up_state": "menu"
    },
    {
      "id": "preco_jaleco",
      "priority": 10,
      "patterns": ["\\b(pre[çc]o|valor|quanto)\\b.*\\bjaleco\\b"],
      "response": {
        "type": "text",
        "body": "*Jalecos Camisart (gabardine):*\n• Tradicional — *R$ 120,00*\n• Premium (amarração em laço + botões) — *R$ 145,00*\n\nIndicado para saúde, odonto, estética. Fazemos bordado da sua logo. Deseja um orçamento?"
      },
      "follow_up_state": "menu"
    },
    {
      "id": "endereco",
      "priority": 5,
      "patterns": ["\\b(endere[çc]o|onde|local|localiza)\\b"],
      "response": {
        "type": "text",
        "body": "*Camisart Belém*\n📍 Av. Magalhães Barata, 445 (altos da Só Modas)\n📞 (91) 99180-0637\n📦 Entregamos para todo o Brasil"
      }
    },
    {
      "id": "bordado_prazo",
      "priority": 5,
      "patterns": ["\\bbordad", "\\bprazo\\b.*\\bborda"],
      "response": {
        "type": "text",
        "body": "✅ *Bordado Camisart*\n• Prazo: *5 dias úteis*\n• Pedido mínimo: *nenhum* (bordamos 1 peça só)\n• Preço: varia conforme o desenho — me envie a logo?"
      }
    }
  ],
  "fallback": {
    "response": {
      "type": "buttons",
      "body": "Não entendi sua mensagem 😊 Como posso ajudar?",
      "buttons": [
        { "id": "consultar_pedido", "title": "📦 Meu pedido" },
        { "id": "ver_catalogo",     "title": "👕 Ver catálogo" },
        { "id": "falar_humano",     "title": "🧑 Falar com atendente" }
      ]
    }
  }
}
```

**Algoritmo:**

1. Normaliza a mensagem: `lower()`, strip, remove acentos (`unicodedata.normalize("NFD")`).
2. Ordena intents por `priority` (maior primeiro).
3. Para cada intent, testa todos os `patterns` com `re.search(flags=re.IGNORECASE)`.
4. Primeiro match ganha — retorna `FAQMatch`.
5. Se nenhum match, retorna `None` (o `state_machine` decide se usa fallback ou avança).

**Invariantes testados:**

- Patterns inválidos (regex malformado) não derrubam o app — logam e são ignorados.
- Um intent com `priority` maior sempre ganha de outro menor que também bate.
- Templates suportam placeholders `{nome}`, `{numero_pedido}` substituídos pelo `state_machine`.

#### 4.2.1. Tipos de Resposta — WhatsApp Interactive Messages

O `FAQResponse` suporta 3 tipos de formato que o `WhatsAppCloudAdapter` converte para os payloads nativos da Meta. Botões e listas **são gratuitos dentro da janela de 24h** e entregam UX significativamente superior a menus textuais numerados.

| Tipo | Quando usar | Formato Meta |
|------|------------|--------------|
| `text` | Respostas informativas, preços, endereço | `type: "text"` |
| `buttons` | 2–3 opções exclusivas (ex: "Prazo normal / Urgente") | `type: "interactive", interactive.type: "button"` |
| `list` | 3–10 opções (ex: seleção de segmento ou produto) | `type: "interactive", interactive.type: "list"` |

**Gatilho de input do usuário em interactive:** quando o cliente clica em um botão ou item de lista, a Meta envia o `id` do botão no campo `interactive.button_reply.id` ou `interactive.list_reply.id`. O `WhatsAppCloudAdapter.parse_inbound()` extrai esse id e o entrega como conteúdo textual ao `MessagePipeline` — o cérebro enxerga "o cliente disse `consultar_pedido`" como se tivesse sido digitado.

**Impacto no `WhatsAppCloudAdapter.send()`:** o método recebe `OutboundMessage` contendo um `FAQResponse`. Para `type == "buttons"`, converte para o payload `interactive.action.buttons` da Meta. O `MessagePipeline` permanece canal-agnóstico.

**Limite crítico da Meta:** mensagens interativas exigem que a conta WhatsApp Business esteja com **status de qualidade Alto ou Médio** e com **display name aprovado**. Estratégia da Fase 1:

1. Subir em produção com todas as respostas `type: "text"` até o display name ser aprovado (5–10 dias úteis).
2. Após aprovação, flipar os `faq.json` para `buttons` e `list` — é só dado, sem deploy de código.

#### 4.2.2. Métricas de Cobertura e Gatilho Objetivo para Fase 2

Cada mensagem inbound grava `matched_intent_id` na tabela `messages` — `NULL` indica fallback. Três métricas são calculáveis por SQL puro:

```sql
-- Taxa de fallback nos últimos 7 dias
SELECT
    COUNT(*) FILTER (WHERE matched_intent_id IS NULL)  * 100.0 / COUNT(*) AS fallback_rate,
    COUNT(*) FILTER (WHERE matched_intent_id IS NOT NULL) * 100.0 / COUNT(*) AS coverage_rate,
    COUNT(*) AS total_messages
FROM messages
WHERE direction = 'in'
  AND created_at >= NOW() - INTERVAL '7 days';

-- Top intents da semana
SELECT matched_intent_id, COUNT(*) AS hits
FROM messages
WHERE direction = 'in' AND matched_intent_id IS NOT NULL
  AND created_at >= NOW() - INTERVAL '7 days'
GROUP BY matched_intent_id
ORDER BY hits DESC;

-- Candidatas a novos intents (mensagens sem match, agrupadas por similaridade manual)
SELECT content, COUNT(*) AS freq
FROM messages
WHERE direction = 'in' AND matched_intent_id IS NULL
  AND created_at >= NOW() - INTERVAL '14 days'
GROUP BY content
ORDER BY freq DESC
LIMIT 50;
```

**Gatilho objetivo para iniciar Fase 2 (LLM Router):**

| Condição medida em janela de 2 semanas | Decisão |
|---|---|
| Fallback rate `< 15%` | FAQ Engine suficiente — adiar Fase 2 |
| Fallback rate `15–30%` | Priorizar ampliar `faq.json` (incluir intents top-freq não cobertas) |
| Fallback rate `> 30%` | Iniciar desenvolvimento da Fase 2 |
| Fallback rate `> 50%` | Fase 2 é bloqueadora — congelar novas features da Fase 1 |

O log em `messages` com `matched_intent_id IS NULL` é também o **dataset de treino** do futuro classificador NLP.

#### 4.2.3. Intents Adicionais — Baseados em Perguntas Reais do Instagram

Conjunto inicial de intents extraído do [relatório do Instagram](relatorio_instagram_camisart.md) (427 comentários analisados). Cobre as 10 perguntas mais frequentes da Camisart.

```json
{
  "id": "pedido_minimo",
  "priority": 8,
  "patterns": [
    "\\b(pedido\\s+m[íi]nimo|m[íi]nimo\\s+de\\s+pe[çc]as|m[íi]nimo\\s+pra|quantas\\s+pe[çc]as\\s+m[íi]nimo)\\b",
    "\\bcomprar\\s+(1|uma|s[oó]\\s+uma)\\s+pe[çc]a\\b",
    "\\btem\\s+m[íi]nimo\\b"
  ],
  "response": {
    "type": "text",
    "body": "✅ *Pedido Mínimo Camisart*\n\n• Vendas avulsas: *sem mínimo* (compramos 1 peça)\n• Bordado: *sem mínimo*\n• Serigrafia: *mínimo 40 peças*\n• Preço de atacado: a partir de *12 peças*\n\nQuer um orçamento?"
  },
  "follow_up_state": "menu"
},
{
  "id": "prazo_entrega",
  "priority": 8,
  "patterns": [
    "\\b(prazo|demora|quanto\\s+tempo|quando\\s+fica|dias\\s+para|entrega\\s+em)\\b",
    "\\b(urgente|r[áa]pido|preciso\\s+para\\s+amanh[ãa]|preciso\\s+logo)\\b"
  ],
  "response": {
    "type": "buttons",
    "body": "⏱️ *Prazos Camisart*\n\n• Sem bordado: *2-3 dias úteis*\n• Com bordado: *5 dias úteis*\n• Entrega nacional: +prazo dos Correios\n\nSeu pedido é:",
    "buttons": [
      { "id": "prazo_normal",  "title": "🗓️ Prazo normal" },
      { "id": "prazo_urgente", "title": "⚡ É urgente" }
    ]
  },
  "follow_up_state": "menu"
},
{
  "id": "entrega_nacional",
  "priority": 7,
  "patterns": [
    "\\b(entrega|envi[ao]|manda|frete|correios|sedex)\\b",
    "\\b(fora\\s+de\\s+bel[ée]m|outro\\s+estado|s[ãa]o\\s+paulo|rio|brasil)\\b"
  ],
  "response": {
    "type": "text",
    "body": "📦 *Entregamos para todo o Brasil!*\n\nVia Correios (PAC/SEDEX) ou transportadora.\nO frete é calculado pelo CEP de destino.\n\nQuer um orçamento com frete incluso?"
  },
  "follow_up_state": "menu"
},
{
  "id": "tamanhos_disponiveis",
  "priority": 6,
  "patterns": [
    "\\b(tamanho|tamanhos|tam|n[úu]mero|talla|grade|gg|plus\\s+size|g[0-9]|xl)\\b",
    "\\b(tem\\s+(P|M|G|GG)|serve\\s+em|numeros\\s+que)\\b"
  ],
  "response": {
    "type": "buttons",
    "body": "📏 *Tamanhos disponíveis:* P, M, G, GG\n\nAlgumas peças têm G1, G2, G3. Para qual produto você precisa de tamanhos?",
    "buttons": [
      { "id": "tam_polo",   "title": "👕 Polo" },
      { "id": "tam_jaleco", "title": "🥼 Jaleco" },
      { "id": "tam_basica", "title": "👚 Básica" }
    ]
  },
  "follow_up_state": "menu"
},
{
  "id": "instagram_referencia",
  "priority": 4,
  "patterns": [
    "\\b(instagram|insta|@camisart|vi\\s+no\\s+insta|vi\\s+nas\\s+foto)\\b",
    "\\b(foto\\s+que\\s+vi|modelo\\s+do\\s+post|aquele\\s+uniforme)\\b"
  ],
  "response": {
    "type": "text",
    "body": "📸 Que bom que viu a gente no Instagram!\n\nMe descreva o modelo que você viu (ou me envie o print da foto) que eu te passo as informações de preço e prazo. 😊"
  },
  "follow_up_state": "menu"
}
```

**Contrato de cobertura de teste (§7.5):** para cada intent acima, a suite garante `≥ 3 frases que casam` e `≥ 2 frases que NÃO casam`.

### 4.3. Catálogo Camisart — Dados de Produto

**Arquivo: `app/knowledge/products.json`**

Baseado no [relatório do Instagram §2](relatorio_instagram_camisart.md):

```json
{
  "version": "1.0",
  "products": [
    {
      "id": "polo_piquet",
      "nome": "Camisa Polo",
      "tecido": "Malha Piquet",
      "precos": {"varejo": 45.00, "atacado_12": 42.00},
      "tamanhos": ["P", "M", "G", "GG"],
      "segmentos": ["corporativo", "industria", "agro", "varejo"],
      "personalizacoes": ["bordado", "serigrafia_40+"]
    },
    {
      "id": "basica_algodao",
      "nome": "Básica Algodão",
      "tecido": "100% Algodão",
      "precos": {"a_partir_de": 29.00},
      "tamanhos": ["P", "M", "G"],
      "segmentos": ["varejo", "atacado", "igrejas", "esportes"]
    },
    {
      "id": "basica_pv",
      "nome": "Básica PV",
      "tecido": "Poliéster + Viscose",
      "precos": {},
      "tamanhos": ["P", "M", "G", "GG"],
      "segmentos": ["industria", "sublimacao"],
      "observacao": "Recomendada para sublimação"
    },
    {
      "id": "jaleco_tradicional",
      "nome": "Jaleco Tradicional",
      "tecido": "Gabardine",
      "precos": {"unidade": 120.00},
      "segmentos": ["saude"],
      "nichos": ["odonto", "medicina", "estetica"]
    },
    {
      "id": "jaleco_premium",
      "nome": "Jaleco Premium",
      "tecido": "Gabardine",
      "precos": {"unidade": 145.00},
      "detalhes": "Amarração em laço + botões",
      "segmentos": ["saude"]
    },
    {
      "id": "uniforme_domestica",
      "nome": "Uniforme Doméstica",
      "tecido": "UniOffice Camisaria",
      "precos": {"unidade": 120.00},
      "segmentos": ["domestica"],
      "observacao": "Babás, faxineiras, cuidadoras"
    },
    {
      "id": "regata",
      "nome": "Regata",
      "tecido": "100% Algodão",
      "precos": {"unidade": 20.00},
      "variantes": ["masculina", "feminina"]
    }
  ],
  "servicos": [
    {
      "id": "bordado",
      "nome": "Bordado de Logo",
      "prazo_dias_uteis": 5,
      "pedido_minimo": 1,
      "observacao": "Preço variável conforme desenho"
    },
    {
      "id": "serigrafia",
      "nome": "Serigrafia",
      "pedido_minimo": 40,
      "observacao": "Ideal para eventos e grupos grandes"
    },
    {
      "id": "sublimacao",
      "nome": "Sublimação",
      "tecido_obrigatorio": "malha_pv",
      "observacao": "Necessita camisa PV"
    }
  ]
}
```

**Observação crítica:** o catálogo PDF atual (`Catalogo.pdf` no projeto do protótipo) é da loja **Ferla, não Camisart**. Um catálogo PDF real Camisart deve ser fornecido pela loja ou montado a partir das imagens do Instagram antes do go-live. A Fase 1 pode funcionar sem o PDF — só no texto do bot.

### 4.4. Modelo de Dados PostgreSQL

**Convenções universais aplicadas a TODAS as tabelas** (herdado de `sgp-sprint-review` §1 e ADR-003):

- PK: `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` com trigger `set_updated_at()`
- Soft delete: `is_archived BOOLEAN NOT NULL DEFAULT FALSE` quando aplicável; `deleted_at TIMESTAMPTZ NULL` quando aplicável
- Nomes de tabela em **plural** e `snake_case`

#### 4.4.1. `sessions` — conversa por cliente (canal-agnóstica)

```sql
CREATE TABLE sessions (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id           TEXT NOT NULL,                  -- 'whatsapp_cloud', 'kommo', ...
    channel_user_id      TEXT NOT NULL,                  -- wa_id / kommo contact_id / ...
    display_name         TEXT,                           -- nome reportado pelo canal
    nome_cliente         TEXT,                           -- nome coletado no fluxo
    current_state        TEXT NOT NULL DEFAULT 'inicio',
    session_data         JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_interaction_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    deleted_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_sessions_channel_user UNIQUE (channel_id, channel_user_id)
);

CREATE INDEX idx_sessions_last_inter ON sessions(last_interaction_at DESC);
```

A chave composta `(channel_id, channel_user_id)` permite que o mesmo número apareça em dois canais sem colisão (ex: mesmo cliente migra para o Kommo e o registro antigo do WhatsApp Cloud não conflita).

#### 4.4.2. `messages` — log completo (in e out), canal-agnóstico

```sql
CREATE TABLE messages (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id            UUID NOT NULL REFERENCES sessions(id) ON DELETE RESTRICT,
    direction             TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    channel_id            TEXT NOT NULL,           -- redundante com sessions mas facilita query
    channel_message_id    TEXT,                    -- id externo do canal (wamid, kommo id...)
    content               TEXT NOT NULL,
    matched_intent_id     TEXT,                    -- id do intent FAQ que casou (null se nenhum)
    state_before          TEXT,
    state_after           TEXT,
    raw_payload           JSONB,                   -- payload original do canal (para debug e treino)
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_messages_channel_msg UNIQUE (channel_id, channel_message_id)
);

CREATE INDEX idx_messages_session ON messages(session_id, created_at DESC);
CREATE INDEX idx_messages_channel ON messages(channel_id, channel_message_id);
```

O UNIQUE composto `(channel_id, channel_message_id)` garante idempotência sem bloquear que dois canais diferentes usem o mesmo esquema de id externo.

**Observação:** `messages` não tem `updated_at` nem soft delete — é tabela de log, imutável por design. Limpeza de logs é feita por ferramenta de manutenção (fora da Fase 1).

#### 4.4.3. `leads` — orçamentos capturados

```sql
CREATE TABLE leads (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              UUID NOT NULL REFERENCES sessions(id),
    nome_cliente            TEXT NOT NULL,
    telefone                TEXT,                    -- wa_id copiado para facilitar export
    segmento                TEXT,                    -- corporativo, saude, industria, agro, ...
    produto                 TEXT,                    -- id do produto ou texto livre
    quantidade              INTEGER,
    personalizacao          TEXT,                    -- bordado, serigrafia, nenhuma
    prazo_desejado          TEXT,
    observacao              TEXT,
    status                  TEXT NOT NULL DEFAULT 'novo' CHECK (status IN ('novo','em_atendimento','convertido','perdido')),

    -- Campos reservados para integração CRM (Fase 4). Fase 1 deixa NULL.
    external_crm_id         TEXT,                    -- id do lead no CRM destino (Kommo lead id, p.ex.)
    synced_to_kommo_at      TIMESTAMPTZ,
    synced_to_rdstation_at  TIMESTAMPTZ,
    sync_metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
                                                      -- ex: {"kommo_pipeline_id":..., "rd_contact_id":...}

    is_archived             BOOLEAN NOT NULL DEFAULT FALSE,
    deleted_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_leads_status         ON leads(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_leads_created        ON leads(created_at DESC);
CREATE INDEX idx_leads_unsynced_kommo ON leads(created_at) WHERE synced_to_kommo_at IS NULL AND deleted_at IS NULL;
```

O índice parcial `idx_leads_unsynced_kommo` torna trivial, na Fase 4, rodar um worker que sincroniza leads pendentes: `SELECT * FROM leads WHERE synced_to_kommo_at IS NULL LIMIT 100;`.

#### 4.4.4. `audit_logs` — auditoria de ações

```sql
CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type     TEXT NOT NULL,              -- 'session.created', 'lead.captured', ...
    resource_type   TEXT NOT NULL,              -- 'session', 'lead', 'message'
    resource_id     UUID NOT NULL,
    actor           TEXT NOT NULL,              -- 'bot', 'system', 'operator:<user_id>'
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_resource ON audit_logs(resource_type, resource_id);
CREATE INDEX idx_audit_action   ON audit_logs(action_type, created_at DESC);
```

#### 4.4.5. Migration Sprint 01

Arquivo: `app/migrations/migrate_sprint_01.py` — idempotente, com rollback em `rollback_sprint_01.py`. Padrão estabelecido em `confexai-sprint-workflow`.

#### 4.4.6. `nps_responses` — pesquisas de satisfação ← v1.1

Criada no Sprint NPS. Armazena cada resposta completa do bot de NPS. Não referencia
`sessions` porque o NPS opera como script standalone sem o pipeline principal.

```sql
CREATE TABLE IF NOT EXISTS nps_responses (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id         BIGINT NOT NULL,
    nome                     TEXT NOT NULL,
    nota_logistica           INTEGER CHECK (nota_logistica BETWEEN 0 AND 10),
    nota_produto_qualidade   INTEGER CHECK (nota_produto_qualidade BETWEEN 0 AND 10),
    nota_produto_expectativa INTEGER CHECK (nota_produto_expectativa BETWEEN 0 AND 10),
    nota_atendimento         INTEGER CHECK (nota_atendimento BETWEEN 0 AND 10),
    nota_indicacao           INTEGER CHECK (nota_indicacao BETWEEN 0 AND 10),
    comentario               TEXT,
    media_geral              NUMERIC(4,2),
    nps_classificacao        TEXT CHECK (nps_classificacao IN ('promotor', 'neutro', 'detrator')),
    raw_data                 JSONB NOT NULL DEFAULT '{}',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nps_classificacao ON nps_responses (nps_classificacao);
CREATE INDEX IF NOT EXISTS idx_nps_created_at    ON nps_responses (created_at DESC);
```

**Design decisions:**
- Sem FK para `sessions` — o NPS é um canal paralelo ao bot de vendas, não usa `SessionLocal`.
- `raw_data JSONB` preserva o payload completo para análise futura e alimentação de dashboards.
- `telegram_user_id BIGINT` (não UUID) — usa o chat_id nativo do Telegram para identificação.
- Mock de dados: `telegram_user_id` no range `10000001–10000099` identifica registros gerados pelo `generate_nps_mock.py` e pode ser limpo sem risco.

Migration: `app/migrations/migrate_sprint_nps.py` | Rollback: `app/migrations/rollback_sprint_nps.py`

### 4.5. Máquina de Estados — Evolução do core/

O `core/` do protótipo (states.py, handlers.py, database.py) **é o ponto de partida, não o produto final.** Evolui assim:

| Arquivo atual | Destino | Mudança |
|---|---|---|
| `core/states.py` | `app/engines/state_machine.py` (constantes) | Acrescentar estados: `AGUARDA_SEGMENTO`, `COLETA_ORCAMENTO_QTD`, `COLETA_ORCAMENTO_PERSONALIZACAO`, `ENCAMINHAR_HUMANO` |
| `core/handlers.py` | `app/engines/state_machine.py` (função `handle`) | Integra `FAQEngine.match()` como primeiro passo de cada estado aberto (INICIO/MENU) |
| `core/database.py` (SQLite pedidos) | Obsoleto | Postgres substitui; lógica vira `SessionService`, `MessageService` |

**Nova assinatura:**

```python
def handle(
    message: str,
    session: Session,           # SQLAlchemy model
    faq_engine: FAQEngine,      # injeção para facilitar teste
) -> HandleResult:
    ...

class HandleResult(BaseModel):
    response: str
    next_state: str
    action: Literal["send_catalog", "capture_lead", "forward_to_human"] | None = None
    action_payload: dict | None = None
```

Mantém a filosofia do `core/` original: **lógica pura, sem I/O**. A persistência é responsabilidade dos services.

**Fluxo base da Fase 1:**

```
INICIO ──► AGUARDA_NOME ──► MENU ─┬─► AGUARDA_PEDIDO ──► FIM
                                  │
                                  ├─► ENVIA_CATALOGO ──► FIM
                                  │
                                  ├─► COLETA_ORCAMENTO ──► FIM (+ lead capturado)
                                  │
                                  └─► ENCAMINHAR_HUMANO ──► FIM
```

Em **qualquer estado**, o `FAQEngine.match()` é tentado primeiro. Se casar um intent de alta prioridade (ex: "qual endereço?"), responde e mantém o estado.

#### 4.5.1. Session Timeout e Reset

**Regra:** se `last_interaction_at < NOW() - INTERVAL '2 hours'`, a sessão é considerada expirada. Na próxima mensagem recebida, o `SessionService` reseta `current_state = 'inicio'` e limpa `session_data`, **preservando `nome_cliente`** (se já coletado) para personalizar o recomeço.

```python
# app/services/session_service.py
SESSION_TIMEOUT = timedelta(hours=2)  # configurável via env no futuro

def get_or_create_session(
    db: Session,
    channel_id: str,
    channel_user_id: str,
    display_name: str | None,
) -> tuple[SessionModel, bool]:   # (session, was_reset)
    session = db.query(SessionModel).filter_by(
        channel_id=channel_id,
        channel_user_id=channel_user_id,
    ).first()

    if session is None:
        session = SessionModel(
            channel_id=channel_id,
            channel_user_id=channel_user_id,
            display_name=display_name,
        )
        db.add(session)
        db.flush()
        return session, False

    if datetime.utcnow() - session.last_interaction_at > SESSION_TIMEOUT:
        nome_salvo = session.nome_cliente
        session.current_state = "inicio"
        session.session_data = {}
        session.nome_cliente = nome_salvo
        session.last_interaction_at = datetime.utcnow()
        return session, True

    return session, False
```

**Mensagens de abertura:**

| Condição | Template |
|---|---|
| Primeira vez (`nome_cliente IS NULL`) | "Olá! Seja bem-vindo(a) à *Camisart*. Com quem tenho o prazer? 😊" |
| Retorno após timeout com `nome_cliente` conhecido | "Olá de novo, *{nome}*! 😊 Como posso te ajudar hoje?" |

**Por que 2 horas:** alinha com o SLA humano real da Camisart (cliente que espera 2h sem resposta procura concorrente). Manter uma sessão em estado intermediário além desse prazo gera mais confusão que valor.

#### 4.5.2. Fluxo de Orçamento com Qualificação por Segmento

A Fase 1 implementa fluxo de orçamento com **qualificação estruturada** — segmento + produto + quantidade + personalização + prazo. Leads qualificados têm taxa de conversão substancialmente maior que leads "fui contatado e é interessado".

```
COLETA_ORCAMENTO
  │
  ├─► COLETA_SEGMENTO          (buttons: Corporativo / Saúde / Outro → lista completa)
  │       │
  │       ▼
  │   COLETA_PRODUTO            (list dinâmica filtrada pelo segmento)
  │       │
  │       ▼
  │   COLETA_QUANTIDADE         ("Quantas peças?")
  │       │
  │       ▼
  │   COLETA_PERSONALIZACAO     (buttons: Bordado / Serigrafia / Sem)
  │       │
  │       ▼
  │   COLETA_PRAZO              (buttons: Normal / Urgente + texto livre "Quando precisa?")
  │       │
  │       ▼
  │   CONFIRMACAO_ORCAMENTO     (resumo + buttons: Confirmar / Corrigir)
  │       │                                         │
  │       ▼                                         ▼
  └─► LEAD_CAPTURADO             ◄── retorna para COLETA_SEGMENTO
           │
           │ grava Lead(status='novo'), audit_log(action_type='lead.captured')
           ▼
        FIM (ou fluxo de boas-vindas para nova interação)
```

**Filtro de produto por segmento** (dicionário em `app/knowledge/products_by_segment.py` ou derivado de `products.json`):

```python
PRODUTOS_POR_SEGMENTO = {
    "corporativo":  ["polo_piquet", "basica_algodao"],
    "saude":        ["jaleco_tradicional", "jaleco_premium"],
    "industria":    ["polo_piquet", "basica_pv"],
    "agro":         ["polo_piquet", "basica_algodao"],
    "domestica":    ["uniforme_domestica"],
    "cop30":        ["polo_piquet", "basica_algodao"],      # ver §1.2.1
    "outro":        ["polo_piquet", "basica_algodao", "jaleco_tradicional",
                     "jaleco_premium", "uniforme_domestica", "basica_pv", "regata"],
}
```

**Captura do Lead** (ação `capture_lead` emitida pelo `state_machine`):

O `lead_service.capture()` cria o `Lead` com `status='novo'` e registra `audit_log(action_type='lead.captured', resource_type='lead', resource_id=lead.id)`. A notificação proativa de operador (Telegram ou WhatsApp) fica como melhoria pós-Fase 1; a estrutura de `audit_logs` já suporta subscription por webhook.

### 4.6. Contratos de API Internos

Aplicando `confexai-api-contracts` SKILL. Endpoints expostos pela Fase 1:

| Método | Rota | Responsável | Descrição |
|---|---|---|---|
| `GET` | `/health` | `app/api/health.py` | Healthcheck — retorna 200 com status do DB |
| `GET` | `/adapters/whatsapp_cloud/webhook` | `app/adapters/whatsapp_cloud/routes.py` | Handshake da Meta — responde o `hub_challenge` |
| `POST` | `/adapters/whatsapp_cloud/webhook` | `app/adapters/whatsapp_cloud/routes.py` | Recebe mensagens do WhatsApp Cloud API |
| `POST` | `/admin/campaigns/reload` | `app/api/admin.py` | Recarrega `campaigns.json` sem restart — requer `X-Admin-Token` |
| `GET` | `/admin/campaigns/status` | `app/api/admin.py` | Lista campanhas ativas e próximas — requer `X-Admin-Token` |

#### `GET /adapters/whatsapp_cloud/webhook` — Verificação da Meta

```python
@router.get("/adapters/whatsapp_cloud/webhook")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> PlainTextResponse:
    """Primeira configuração do webhook na Meta — responde o challenge."""
    if hub_mode == "subscribe" and hub_verify_token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, detail="Verify token inválido.")
```

#### `POST /adapters/whatsapp_cloud/webhook` — Recebimento de mensagens

```python
@router.post("/adapters/whatsapp_cloud/webhook", status_code=200)
async def receive_message(
    request: Request,
    db: Session = Depends(get_db),
    adapter: WhatsAppCloudAdapter = Depends(get_whatsapp_adapter),
    pipeline: MessagePipeline = Depends(get_message_pipeline),
) -> StandardResponse:
    raw = await request.body()
    adapter.verify_auth(raw, dict(request.headers))

    inbound = await adapter.parse_inbound(json.loads(raw), dict(request.headers))
    if inbound is None:
        # status update (delivered/read) — nada a processar
        return StandardResponse(data={"received": True, "processed": False})

    outbound = await pipeline.process(inbound, db)
    if outbound:
        external_id = await adapter.send(outbound)
        pipeline.record_external_id(outbound, external_id, db)

    return StandardResponse(data={"received": True, "processed": True})
```

**Nota:** o cérebro (`MessagePipeline`) recebe `InboundMessage` canônica. Para adicionar o Kommo na Fase 4, criamos `app/adapters/kommo/routes.py` com o mesmo shape — zero mudança em pipeline, engines ou services.

#### `GET /health`

```python
@router.get("/health")
async def health(db: Session = Depends(get_db)) -> StandardResponse:
    db.execute(text("SELECT 1"))
    return StandardResponse(data={"status": "ok", "db": "up"})
```

**Sem outros endpoints públicos de negócio na Fase 1.** Gestão de leads é feita por SQL direto no VPS (o volume é pequeno). UI de admin vira Fase 2. Os endpoints `/admin/campaigns/*` existem apenas para operação (recarga de campanhas sazonais) e são protegidos por `X-Admin-Token`.

---

### 4.7. Campaign Engine — Ações Sazonais Configuráveis

O `CampaignEngine` permite criar campanhas sazonais (Copa do Mundo, Natal, Volta às Aulas, Dia dos Pais, Carnaval, eventos locais) que injetam novos intents e sobrescrevem respostas existentes **sem nenhum deploy de código**. Toda configuração vive em `app/knowledge/campaigns.json` — um arquivo editável diretamente no VPS ou via `git pull`, com recarga imediata via endpoint admin.

#### 4.7.1. Design Principles

| Princípio | Como se manifesta |
|-----------|------------------|
| **Configurável** | `campaigns.json` é a única fonte de verdade. Nenhum código muda entre campanhas. |
| **Dinâmico** | `POST /admin/campaigns/reload` recarrega o arquivo em memória sem restart do processo. |
| **Didático** | JSON com campos `_comment` embutidos e seção "Como criar uma campanha" incluída no próprio arquivo. |
| **Fácil de configurar** | Schema mínimo obrigatório com defaults sensatos. Uma campanha simples precisa de 5 campos. |
| **Zero-risco de regressão** | Campanhas se sobrepõem ao `faq.json` base via prioridade — quando expiram, o comportamento volta ao normal automaticamente. |

#### 4.7.2. `app/knowledge/campaigns.json` — Schema Completo

```json
{
  "_comment": "Campanhas sazonais da Camisart. Edite este arquivo e use POST /admin/campaigns/reload para ativar sem restart.",
  "_date_format": "YYYY-MM-DD (ex: 2026-12-25)",
  "_priority_guide": "Intents de campanha usam priority >= 50 para sobrepor o FAQ base (max 10-15). Use 50-99.",
  "_how_to_create": "Veja a seção de exemplos no final deste arquivo.",

  "version": "1.0",
  "campaigns": [

    {
      "_comment": "--- CAMPANHA: Copa do Mundo 2026 ---",
      "id": "copa_2026",
      "name": "Copa do Mundo 2026 ⚽",
      "description": "Uniformes para torcidas organizadas, empresas patrocinadoras e grupos de amigos durante a Copa 2026.",
      "enabled": false,
      "active_from": "2026-05-15",
      "active_until": "2026-07-20",

      "lead_segmento_default": "copa_2026",

      "greeting_override": "⚽ Olá! Bem-vindo(a) à Camisart na Copa do Mundo 2026!\n\nEstamos com coleção especial para torcidas, empresas e grupos. Como posso ajudar?",

      "intents": [
        {
          "id": "copa_uniformes_torcida",
          "priority": 55,
          "patterns": [
            "\\bcopa\\b",
            "\\bworld\\s*cup\\b",
            "\\btorcida\\b",
            "\\buniforme\\s*de\\s*time\\b",
            "\\bcamisa\\s*de\\s*time\\b",
            "\\bgrupo\\s*de\\s*amigos\\b.*\\buniforme\\b"
          ],
          "response": {
            "type": "buttons",
            "body": "⚽ *Uniformes Copa 2026 — Camisart*\n\nFazemos camisetas personalizadas para:\n• Torcidas organizadas (sublimação total)\n• Grupos de amigos\n• Empresas e patrocinadores\n• Equipes amadoras\n\nQual é o seu caso?",
            "buttons": [
              { "id": "copa_torcida",   "title": "⚽ Torcida/Grupo" },
              { "id": "copa_empresa",   "title": "🏢 Empresa" },
              { "id": "copa_orcamento", "title": "📋 Quero orçamento" }
            ]
          },
          "follow_up_state": "aguarda_orcamento"
        }
      ],

      "response_overrides": {
        "_comment": "Sobrescreve respostas de intents existentes no faq.json durante esta campanha.",
        "preco_polo": {
          "type": "text",
          "body": "⚽ *Polo Camisart — Coleção Copa 2026*\n\n• *R$ 45,00* no varejo\n• *R$ 42,00* no atacado (12+ peças)\n• Bordado da logo: sem mínimo\n• *Prazo especial:* confirmando até 15/06, entregamos antes da final!\n\nDeseja um orçamento com tema Copa?"
        }
      }
    },

    {
      "_comment": "--- CAMPANHA: Volta às Aulas ---",
      "id": "volta_aulas_2027",
      "name": "Volta às Aulas 2027 📚",
      "description": "Uniformes escolares e para instituições de ensino. Pico em jan-fev.",
      "enabled": false,
      "active_from": "2027-01-05",
      "active_until": "2027-02-28",

      "lead_segmento_default": "educacao",

      "greeting_override": "📚 Olá! Pronto(a) para a Volta às Aulas?\n\nA Camisart faz uniformes escolares personalizados com bordado e serigrafia. Como posso ajudar?",

      "intents": [
        {
          "id": "volta_aulas_uniforme",
          "priority": 55,
          "patterns": [
            "\\bvolta\\s*(as|às)\\s*aulas\\b",
            "\\buniforme\\s*escolar\\b",
            "\\bcol[eé]gio\\b.*\\buniforme\\b",
            "\\bescola\\b.*\\bcamisa\\b",
            "\\bturma\\b.*\\bcamisa\\b"
          ],
          "response": {
            "type": "text",
            "body": "📚 *Uniformes Escolares — Camisart*\n\nAtendemos colégios, turmas e instituições com:\n• Polo com bordado do colégio\n• Camiseta básica com estampa da turma\n• Jaleco para laboratório\n\nFazemos bordado a partir de 1 peça. Qual produto você precisa?"
          },
          "follow_up_state": "aguarda_orcamento"
        }
      ],

      "response_overrides": {}
    },

    {
      "_comment": "--- MODELO EM BRANCO (copie para criar nova campanha) ---",
      "id": "modelo_campanha",
      "name": "Nome da Campanha",
      "description": "Descrição interna — não aparece para o cliente.",
      "enabled": false,
      "active_from": "2099-01-01",
      "active_until": "2099-01-02",
      "lead_segmento_default": null,
      "greeting_override": null,
      "intents": [],
      "response_overrides": {}
    }

  ],

  "_examples": {
    "_comment": "Como criar uma campanha em 5 passos:",
    "passo_1": "Copie o bloco 'modelo_campanha' acima",
    "passo_2": "Mude 'id' para algo único (ex: 'natal_2026')",
    "passo_3": "Preencha 'active_from' e 'active_until' com as datas",
    "passo_4": "Mude 'enabled' para true",
    "passo_5": "Use POST /admin/campaigns/reload ou reinicie o bot"
  }
}
```

#### 4.7.3. Schema Pydantic — `app/engines/campaign_engine.py`

```python
from datetime import date
from pathlib import Path
from typing import Any
import json
import logging

from pydantic import BaseModel, Field, model_validator

from app.engines.regex_engine import FAQIntent, FAQResponse

logger = logging.getLogger(__name__)


class Campaign(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool
    active_from: date
    active_until: date
    lead_segmento_default: str | None = None
    greeting_override: str | None = None
    intents: list[FAQIntent] = Field(default_factory=list)
    response_overrides: dict[str, FAQResponse] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_dates(self) -> "Campaign":
        if self.active_from > self.active_until:
            raise ValueError(
                f"Campanha '{self.id}': active_from ({self.active_from}) "
                f"deve ser anterior a active_until ({self.active_until})"
            )
        return self

    @model_validator(mode="after")
    def validate_intent_priorities(self) -> "Campaign":
        for intent in self.intents:
            if intent.priority < 50:
                logger.warning(
                    "Campanha '%s': intent '%s' tem priority=%d. "
                    "Recomendado >= 50 para sobrepor FAQ base.",
                    self.id, intent.id, intent.priority,
                )
        return self


class CampaignsFile(BaseModel):
    version: str
    campaigns: list[Campaign]


class CampaignEngine:
    """Gerencia campanhas sazonais configuradas em campaigns.json."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._campaigns: list[Campaign] = []

    def reload(self) -> int:
        """Relê campaigns.json. Retorna número de campanhas carregadas."""
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        cleaned = self._strip_comments(raw)
        data = CampaignsFile(**cleaned)
        self._campaigns = data.campaigns
        logger.info(
            "CampaignEngine: %d campanhas carregadas (%d ativas hoje).",
            len(self._campaigns),
            len(self.active_campaigns()),
        )
        return len(self._campaigns)

    def active_campaigns(self, at: date | None = None) -> list[Campaign]:
        today = at or date.today()
        return [
            c for c in self._campaigns
            if c.enabled and c.active_from <= today <= c.active_until
        ]

    def merged_intents(self, base_intents: list[FAQIntent]) -> list[FAQIntent]:
        """Intents de campanha (priority>=50) + intents base. Campanhas ganham."""
        campaign_intents: list[FAQIntent] = []
        for campaign in self.active_campaigns():
            campaign_intents.extend(campaign.intents)
        ordered = sorted(campaign_intents, key=lambda i: i.priority, reverse=True)
        ordered += base_intents
        return ordered

    def apply_override(self, intent_id: str, base: FAQResponse) -> FAQResponse:
        for campaign in self.active_campaigns():
            if intent_id in campaign.response_overrides:
                return campaign.response_overrides[intent_id]
        return base

    def active_greeting(self) -> str | None:
        for campaign in self.active_campaigns():
            if campaign.greeting_override:
                return campaign.greeting_override
        return None

    def default_segmento(self) -> str | None:
        for campaign in self.active_campaigns():
            if campaign.lead_segmento_default:
                return campaign.lead_segmento_default
        return None

    def status(self) -> dict[str, Any]:
        today = date.today()
        return {
            "today": today.isoformat(),
            "total_loaded": len(self._campaigns),
            "active": [
                {
                    "id": c.id,
                    "name": c.name,
                    "active_until": c.active_until.isoformat(),
                    "days_remaining": (c.active_until - today).days,
                    "intents_count": len(c.intents),
                    "has_overrides": bool(c.response_overrides),
                    "has_greeting": bool(c.greeting_override),
                }
                for c in self.active_campaigns()
            ],
            "upcoming": [
                {
                    "id": c.id,
                    "name": c.name,
                    "active_from": c.active_from.isoformat(),
                    "days_until": (c.active_from - today).days,
                }
                for c in self._campaigns
                if c.enabled and c.active_from > today
            ],
        }

    @staticmethod
    def _strip_comments(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                k: CampaignEngine._strip_comments(v)
                for k, v in obj.items()
                if not k.startswith("_")
            }
        if isinstance(obj, list):
            return [CampaignEngine._strip_comments(item) for item in obj]
        return obj
```

#### 4.7.4. Integração com FAQEngine e MessagePipeline

O `FAQEngine` recebe o `CampaignEngine` no construtor:

```python
class FAQEngine:
    def __init__(
        self,
        faq_path: Path,
        campaign_engine: "CampaignEngine | None" = None,
    ) -> None:
        self._faq_path = faq_path
        self._campaign_engine = campaign_engine
        self._base_intents: list[FAQIntent] = []
        self._fallback: FAQResponse | None = None
        self._load()

    def match(self, message: str) -> FAQMatch | None:
        normalized = self._normalize(message)
        intents = (
            self._campaign_engine.merged_intents(self._base_intents)
            if self._campaign_engine
            else self._base_intents
        )
        for intent in intents:
            for pattern in intent.patterns:
                try:
                    if re.search(pattern, normalized, re.IGNORECASE):
                        response = (
                            self._campaign_engine.apply_override(intent.id, intent.response)
                            if self._campaign_engine
                            else intent.response
                        )
                        return FAQMatch(
                            intent_id=intent.id,
                            response=response,
                            follow_up_state=intent.follow_up_state,
                        )
                except re.error as exc:
                    logger.warning("Pattern inválido em intent '%s': %s", intent.id, exc)
        return None
```

O `MessagePipeline` consulta o `CampaignEngine` em dois pontos:

```python
# app/pipeline/message_pipeline.py — pontos de integração

async def _handle_inicio(self, session, inbound) -> str:
    greeting = self._campaign_engine.active_greeting()
    if greeting:
        return greeting
    nome = session.nome_cliente
    if nome:
        return f"Olá de novo, {nome}! 😊 Como posso ajudar hoje?"
    return "Olá! Seja bem-vindo(a) à Camisart. Com quem tenho o prazer?"
```

```python
# app/services/lead_service.py — uso do segmento default da campanha ativa
def capture(self, session, data, db, campaign_engine) -> Lead:
    segmento = data.segmento or campaign_engine.default_segmento()
    ...
```

#### 4.7.5. Endpoints Admin — Reload e Status

```python
# app/api/admin.py
from fastapi import APIRouter, Depends, Header, HTTPException
from app.config import settings
from app.engines.campaign_engine import CampaignEngine
from app.schemas.response import StandardResponse

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido.")


@router.post("/campaigns/reload", dependencies=[Depends(verify_admin_token)])
async def reload_campaigns(
    engine: CampaignEngine = Depends(get_campaign_engine),
) -> StandardResponse:
    count = engine.reload()
    active = engine.active_campaigns()
    return StandardResponse(data={
        "reloaded": True,
        "campaigns_loaded": count,
        "active_now": [c.id for c in active],
    })


@router.get("/campaigns/status", dependencies=[Depends(verify_admin_token)])
async def campaigns_status(
    engine: CampaignEngine = Depends(get_campaign_engine),
) -> StandardResponse:
    return StandardResponse(data=engine.status())
```

**Regra de segurança:** `ADMIN_TOKEN` tem no mínimo 32 caracteres (gerar com `secrets.token_hex(32)`). Endpoint admin sem o header retorna 403. Na Fase 4, substituir por JWT quando houver painel web.

#### 4.7.6. Inicialização via Lifespan

```python
# app/main.py — lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    global campaign_engine, faq_engine
    campaign_engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    campaign_engine.reload()
    faq_engine = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=campaign_engine)
    yield
    campaign_engine = None
    faq_engine = None


def get_campaign_engine() -> CampaignEngine:
    assert campaign_engine is not None, "CampaignEngine não inicializado"
    return campaign_engine
```

#### 4.7.7. Testes — Cenários Mínimos

| Cenário | Validação |
|---|---|
| Campanha com `enabled=True` + hoje dentro da janela | Aparece em `active_campaigns()` |
| Campanha com `enabled=False` | Nunca aparece em `active_campaigns()` |
| Campanha expirada (`active_until` no passado) | Nunca aparece em `active_campaigns()`, mesmo com `enabled=True` |
| `greeting_override` presente | Retornado por `active_greeting()` |
| `lead_segmento_default` presente | Retornado por `default_segmento()` |
| `response_overrides["preco_polo"]` definido | `apply_override` retorna resposta da campanha; outros intents ficam intactos |
| Edição do arquivo + `reload()` | Novo estado reflete imediatamente sem restart |
| `active_from > active_until` | `Campaign` levanta `ValidationError` |

Arquivo: `tests/test_campaign_engine.py`. Suite completa em [confexai-testing-standards](/.claude/skills/confexai-testing-standards/SKILL.md) — cobertura 100% dos métodos públicos do `CampaignEngine`.

#### 4.7.8. Guia Operacional — Como Criar uma Campanha

> Esta seção é para o time operacional — linguagem não-técnica intencional.

1. **Abra** o arquivo `app/knowledge/campaigns.json` no servidor (ou edite localmente e faça `git push`).
2. **Copie** o bloco `modelo_campanha` que está no final do arquivo.
3. **Preencha** os campos:
   - `"id"`: identificador único sem espaços (ex: `"natal_2026"`)
   - `"name"`: nome legível (ex: `"Natal 2026 🎄"`)
   - `"active_from"` e `"active_until"`: datas no formato `"YYYY-MM-DD"`
   - `"enabled"`: mude para `true` quando quiser ativar
4. **Adicione intents** (perguntas novas que aparecem durante a campanha) em `"intents"`. Use `priority >= 50`.
5. **Adicione overrides** (respostas existentes com texto sazonal) em `"response_overrides"`. A chave é o `id` do intent do `faq.json`.
6. **Ative sem reiniciar o bot:**
   ```bash
   curl -X POST https://camisart-bot.seu-dominio.com/admin/campaigns/reload \
        -H "X-Admin-Token: SEU_TOKEN_ADMIN"
   ```
7. **Verifique o que está ativo:**
   ```bash
   curl https://camisart-bot.seu-dominio.com/admin/campaigns/status \
        -H "X-Admin-Token: SEU_TOKEN_ADMIN"
   ```

**Desativar antes do prazo:** mude `"enabled"` para `false` e recarregue.
**Testar sem ativar:** mude as datas para janela no passado — o bot ignora mesmo com `enabled: true`.

---

## 4.8. NPS Bot — Pesquisa de Satisfação ← v1.1

Sprint entregue na preparação para reunião com o cliente Matheus. PRD completo em
`docs/sprint_13/02_PRD.md`.

### 4.8.1. Visão Geral

Um segundo script de long-polling (`scripts/telegram_nps.py`) que roda **em paralelo e
de forma completamente independente** do bot de vendas (`scripts/telegram_polling.py`).
Não usa `MessagePipeline`, `FAQEngine`, `SessionService` nem qualquer engine do núcleo
— é um bot dedicado à coleta de feedback estruturado.

```
Terminal 1                     Terminal 2
──────────────────────         ──────────────────────
python scripts/                python scripts/
  telegram_polling.py            telegram_nps.py
  (bot de vendas)                (bot NPS)
       │                                │
       │ MessagePipeline                │ state machine própria
       │ FAQEngine                      │ 6 estados simples
       │ SessionService                 │ sem pipeline
       │ PostgreSQL sessions            │ PostgreSQL nps_responses
       └─────────────────              └──────────────────────
```

### 4.8.2. As 5 Perguntas e Classificação

| # | Dimensão | Classificação da nota |
|---|---|---|
| 1 | Logística | promotor (9-10) / neutro (7-8) / detrator (0-6) |
| 2 | Produto — Qualidade | idem |
| 3 | Produto — Expectativa | idem |
| 4 | Atendimento | idem |
| 5 | Indicação (NPS clássico) | **base do NPS Score** |

**Fórmula NPS:** `NPS = % Promotores(nota ≥ 9) − % Detratores(nota ≤ 6)` da pergunta 5.

### 4.8.3. Arquitetura do Script

```
/start ou /nps
      │
AGUARDA_NOME
      │ nome coletado
LOGISTICA         ← pergunta + teclado 0-10
      │ nota validada (0-10 obrigatório)
PRODUTO_QUALIDADE ← pergunta + teclado
      │
PRODUTO_EXPECTATIVA
      │
ATENDIMENTO
      │
INDICACAO
      │
COMENTARIO        ← texto livre ("pular" aceito)
      │
   dual-write
   ├── PostgreSQL: INSERT INTO nps_responses (§4.4.6)
   └── JSON: append data/nps_results.json
      │
   Agradecimento + média calculada exibida ao cliente
```

**Padrões obrigatórios:** raw `httpx.AsyncClient` (sem `python-telegram-bot`);
`sys.path.insert` + `load_dotenv()`; `settings.TELEGRAM_BOT_TOKEN`; logging igual
ao `telegram_polling.py`; `/cancelar` universal sem salvar parcialmente.

### 4.8.4. Persistência Dual-Write

```python
def salvar_resultado(registro: dict) -> None:
    try:
        salvar_postgres(registro)   # primário — nps_responses
    except Exception:
        logger.exception("Falha PostgreSQL — salvando apenas JSON")
    salvar_json(registro)           # secundário — data/nps_results.json (dashboard)
```

PostgreSQL é o primário. O JSON é mantido como secundário para alimentar o dashboard
HTML standalone sem depender de servidor.

### 4.8.5. Gerador de Dados Mock

`scripts/generate_nps_mock.py` popula 20 registros realistas com 6 perfis de cliente
(promotor entusiasmado 30%, promotor fiel 25%, neutro satisfeito 20%, detrator por
logística 10%, detrator por atendimento 10%, detrator geral 5%). Usa `random.seed(42)`
para reprodutibilidade. Identifica registros mock por `telegram_user_id` 10000001–10000099.

### 4.8.6. Dashboard de Análise (`nps_dashboard.html`)

Arquivo HTML standalone (sem servidor) em `docs/evaluation/reports/nps_dashboard.html`.
7 seções didáticas: NPS Score com gauge SVG, radar por dimensão, distribuição das
notas, análise de comentários, mapa de calor temporal, ações recomendadas por dimensão
com badge de prioridade, comparativo promotores vs detratores. Usa Chart.js via CDN.
Fallback para dados mock hardcoded quando `fetch()` falha (arquivo aberto diretamente).

### 4.8.7. Variáveis de Ambiente

Nenhuma nova. Usa apenas `TELEGRAM_BOT_TOKEN` e `DATABASE_URL` já existentes.

---

## 5. Integração WhatsApp Cloud API — Onboarding

Guia prático para ativar a integração **quando chegar o momento**. Não precisa ser executado agora.

### 5.1. Pré-requisitos

- **Conta Facebook Business** (business.facebook.com) com CNPJ da Camisart
- **Número de telefone dedicado** que NÃO esteja ativo em outro WhatsApp (nem o app normal, nem o Business app). Importante: a Camisart hoje usa `(91) 99180-0637` no WhatsApp Business app — esse número precisaria migrar OU adquirir um número novo dedicado ao bot.
- Cartão de crédito para configuração de billing na Meta (cobrança só após 1.000 conversas/mês grátis)

### 5.2. Passo a Passo

1. **Criar/acessar conta Meta Business** → https://business.facebook.com
2. **Criar um App** em https://developers.facebook.com/apps → tipo "Business"
3. **Adicionar o produto WhatsApp** ao app → "Configurar"
4. **Registrar número de telefone**:
   - Na seção WhatsApp → API Setup, clicar em "Adicionar número de telefone"
   - Inserir o número dedicado, receber código por SMS/voz, verificar
   - Dar um **display name** à conta Business (ex: "Camisart Uniformes")
5. **Obter credenciais** (copiar e guardar em lugar seguro):
   - `WHATSAPP_TOKEN` — token temporário (24h) para testes; depois criar **System User token permanente** em Business Settings
   - `WHATSAPP_PHONE_NUMBER_ID` — id do número registrado
   - `WHATSAPP_BUSINESS_ACCOUNT_ID` — id da conta business
6. **Configurar o webhook**:
   - URL pública HTTPS: `https://seu-dominio.com/whatsapp/webhook`
   - `WHATSAPP_VERIFY_TOKEN`: qualquer string secreta que você gerar; a Meta envia no handshake inicial
   - Subscribe em: `messages`, `message_statuses`
7. **Testar no sandbox**:
   - Adicionar até 5 números de teste (você, a dona da Camisart)
   - Enviar uma mensagem do WhatsApp desses números para o número registrado
   - Verificar que chega no webhook
8. **Ir para produção**:
   - Preencher o **formulário de business verification** da Meta (prazo 1–3 dias úteis)
   - Após aprovação, remover a limitação de números de teste
   - Criar **message templates** (exigidos para iniciar conversa com cliente após 24h de silêncio)

### 5.3. Variáveis de Ambiente Resultantes

```env
# .env
WHATSAPP_TOKEN=<token permanente>
WHATSAPP_PHONE_NUMBER_ID=<id>
WHATSAPP_BUSINESS_ACCOUNT_ID=<id>
WHATSAPP_VERIFY_TOKEN=<string secreta escolhida por você>
WHATSAPP_APP_SECRET=<app secret para validar HMAC>
WHATSAPP_API_VERSION=v20.0
```

### 5.4. Desenvolvimento Local

Para testar localmente sem VPS pública, usar `ngrok`:

```bash
ngrok http 8000
# Copiar o URL HTTPS gerado (ex: https://abc123.ngrok.io)
# Configurar na Meta como webhook: https://abc123.ngrok.io/whatsapp/webhook
```

---

## 6. Ambientes e Deploy

### 6.1. Ambiente Local (Dev)

```bash
# Setup inicial
cd c:\workspace\chatbot
python -m venv .venv
.venv\Scripts\activate                   # Windows
pip install -r requirements.txt

# Postgres local (usar Docker para isolamento)
docker run -d --name camisart-pg \
  -e POSTGRES_DB=camisart_db \
  -e POSTGRES_PASSWORD=dev \
  -p 5432:5432 postgres:15

# Variáveis
cp .env.example .env
# editar DATABASE_URL=postgresql://postgres:dev@localhost:5432/camisart_db

# Migrations
python app/migrations/migrate_sprint_01.py

# Rodar
uvicorn app.main:app --reload --port 8000

# Expor webhook para Meta testar
ngrok http 8000
```

### 6.2. Ambiente de Produção — VPS Hostinger

```bash
# Estrutura na VPS (exemplo)
/opt/camisart/
├── app/                     # checkout do git
├── .venv/
├── .env                     # secrets (fora do git)
└── logs/

# systemd unit: /etc/systemd/system/camisart.service
[Unit]
Description=Camisart WhatsApp Bot
After=network.target postgresql.service

[Service]
Type=simple
User=camisart
WorkingDirectory=/opt/camisart
Environment="PATH=/opt/camisart/.venv/bin"
EnvironmentFile=/opt/camisart/.env
ExecStart=/opt/camisart/.venv/bin/gunicorn app.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 2 -b 127.0.0.1:8000 \
  --access-logfile /opt/camisart/logs/access.log \
  --error-logfile /opt/camisart/logs/error.log
Restart=always

[Install]
WantedBy=multi-user.target
```

Nginx reverse proxy + Let's Encrypt via certbot:

```nginx
server {
    listen 443 ssl http2;
    server_name camisart-bot.seu-dominio.com;
    ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6.3. Processo de Deploy (herdado de `confexai-sprint-workflow`)

```bash
# Após merge no main (na VPS)
cd /opt/camisart
git pull origin main
.venv/bin/pip install -r requirements.txt
.venv/bin/python app/migrations/migrate_sprint_NN.py
sudo systemctl restart camisart

# Verificar
curl https://camisart-bot.seu-dominio.com/health
journalctl -u camisart --since "2 minutes ago"
```

### 6.4. Variáveis de Ambiente (`.env.example`)

```env
# App
APP_ENV=development                # development | production
APP_LOG_LEVEL=INFO

# PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost:5432/camisart_db
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/camisart_test_db

# WhatsApp Cloud API
WHATSAPP_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_BUSINESS_ACCOUNT_ID=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_APP_SECRET=
WHATSAPP_API_VERSION=v20.0

# Admin API — CampaignEngine (§4.7)
ADMIN_TOKEN=                          # gere com: python -c "import secrets; print(secrets.token_hex(32))"
CAMPAIGNS_JSON_PATH=app/knowledge/campaigns.json
FAQ_JSON_PATH=app/knowledge/faq.json
```

---

## 7. Qualidade — Testes, Logs e Observabilidade

Aplica `confexai-testing-standards`.

### 7.1. Banco de Teste

- **SEMPRE** `camisart_test_db` — nunca `camisart_db`.
- Fixture de sessão recria o schema a cada teste (SQLAlchemy `Base.metadata.create_all`).
- Rollback automático via `pytest-asyncio` + transaction no `yield`.

### 7.2. Mock Obrigatório da Meta Cloud API

```python
# Exemplo — envio de mensagem
with patch("app.services.whatsapp_client.httpx.AsyncClient") as mock_client:
    mock_client.return_value.__aenter__.return_value.post.return_value = \
        MagicMock(status_code=200, json=lambda: {"messages": [{"id": "wamid.xxx"}]})
    ...
```

**Nunca chamar a API real da Meta em teste** — custa dinheiro e é flaky.

### 7.3. Cenários Mínimos por Endpoint

| Endpoint | Cenários |
|---|---|
| `GET /health` | 200 ok |
| `GET /adapters/whatsapp_cloud/webhook` (verify) | 200 com token correto, 403 com token errado |
| `POST /adapters/whatsapp_cloud/webhook` | 200 mensagem nova, 200 idempotente (msg duplicada), 403 HMAC inválido, 200 status update (delivered/read) sem side effects |

### 7.4. Testes do Padrão Adapter

Regra forte: **é proibido importar símbolos de `app/adapters/whatsapp_cloud/` a partir de `app/engines/`, `app/services/` ou `app/pipeline/`.** Um teste estrutural garante:

```python
def test_pipeline_nao_importa_adapter_concreto():
    import ast, pathlib
    raiz = pathlib.Path("app/pipeline")
    proibidos = ["whatsapp_cloud", "kommo"]
    for py in raiz.rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modulo = (node.module or "") if isinstance(node, ast.ImportFrom) \
                         else node.names[0].name
                for p in proibidos:
                    assert p not in modulo, f"{py} importa adapter proibido: {modulo}"
```

Um teste análogo vale para `app/engines/` e `app/services/`.

### 7.5. Testes de FAQEngine

Cobertura 100% dos intents do `faq.json`. Para cada intent:

- ao menos 3 variações de frase que devem casar
- ao menos 2 frases que NÃO devem casar
- verifica `priority` quando há sobreposição

### 7.6. Estrutura de Log

```python
# logger config em app/main.py
logging.basicConfig(
    level=settings.APP_LOG_LEVEL,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler("logs/app.log", maxBytes=10_000_000, backupCount=10),
    ],
)
```

Nível por módulo:
- `app.api.whatsapp`: INFO para cada mensagem recebida (sem conteúdo para LGPD; só `wa_id`, intent_id, latência)
- `app.services.whatsapp_client`: INFO para envio, WARN para erros, ERROR para 4xx/5xx da Meta
- `app.engines.regex_engine`: DEBUG (silencioso em prod)

### 7.7. Observabilidade Mínima (Fase 1)

- `GET /health` consumido por uptime monitor externo (UptimeRobot gratuito)
- Logs em arquivo com rotação
- Métrica manual via SQL: `SELECT COUNT(*), matched_intent_id FROM messages WHERE direction='in' GROUP BY matched_intent_id;`

Observabilidade completa (Prometheus/Grafana) vira Fase 4.

---

## 8. Workflow de Desenvolvimento

**Obrigatório seguir o ritual de 7 passos de `confexai-sprint-workflow`:**

1. **Inspeção** → gerar prompt de inspeção, NÃO implementar
2. **Feedback** → arquiteto valida; Claude descarta falsos positivos
3. **Aprovação** explícita
4. **Implementação** em ordem exata, referenciando as skills relevantes
5. **Testes** (`pytest -v`) → 100% verde obrigatório
6. **Commits atômicos** no formato `tipo(módulo): descrição [SNN-NN]`
7. **PR** com auditoria `sgp-sprint-review` antes do merge

### 8.1. Primeiro Sprint — `Sprint01_foundation`

PRD a ser criado em `docs/PRD_Sprint01_foundation.md`. Sugestão de itens (a serem refinados no planning):

- S01-01: estrutura FastAPI + Postgres + lifespan
- S01-02: modelos `sessions`, `messages`, `audit_logs` + migration 01
- S01-03: `FAQEngine` + `faq.json` inicial + testes
- S01-04: endpoints `GET/POST /whatsapp/webhook` com HMAC
- S01-05: `whatsapp_client.send_text()` mockado nos testes
- S01-06: integração fim-a-fim testada local com ngrok

### 8.2. Commits — Tipos Aceitos

Herdado de `confexai-sprint-workflow`:

`feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `devops`, `security`, `prompt`

Mensagem em português, formato: `tipo(módulo): descrição curta [S01-NN]`.

### 8.3. Registro de Decisões — ADRs

Todo desvio do spec ou decisão arquitetural relevante vira um ADR em `docs/decisions/ADRs.md`. Herdado de `confexai-architecture-decisions`.

---

## 9. Roadmap — Fases 2, 3 e 4

**Fora do escopo desta versão do spec.** Documentado apenas para garantir que a Fase 1 não bloqueie as fases seguintes.

### 9.0. Sprint NPS — Feedback Loop ← v1.1

**Status: entregue.** Sprint intercalado entre a conclusão da Fase 1 e o início da Fase 2.
Motivação: demonstração para o cliente Matheus da capacidade analítica do sistema.

**O que foi entregue:**

| Entregável | Arquivo | Status |
|---|---|---|
| Migration `nps_responses` | `app/migrations/migrate_sprint_nps.py` | ✅ |
| Bot NPS (long-polling) | `scripts/telegram_nps.py` | ✅ |
| Gerador de mock | `scripts/generate_nps_mock.py` | ✅ |
| Dashboard HTML standalone | `docs/evaluation/reports/nps_dashboard.html` | ✅ |

**Impacto arquitetural:** zero. O Sprint NPS é completamente aditivo — não toca no
`MessagePipeline`, `FAQEngine`, `StateMachine` nem em nenhum model existente. A única
adição ao banco é a tabela `nps_responses` (§4.4.6), sem FK para as tabelas core.

**Próximo passo natural:** usar os dados coletados pelo NPS para calibrar o `faq.json`
com as dimensões mais críticas apontadas pelos detratores — fechando o loop
vendas → feedback → melhoria.

---

### Fase 2 — LLM Router: Classificador de Intenções em Linguagem Livre

**Papel exato:** quando `FAQEngine.match()` retorna `None` (fallback), o `LLMRouter` recebe a mensagem + contexto da sessão e classifica a intenção em um dos `intent_id`s conhecidos do `faq.json` — ou retorna `"fora_do_escopo"`. **Não gera texto livre** — apenas classifica. A resposta ao cliente ainda vem do template do `faq.json` correspondente. Isso elimina risco de alucinação e preserva tom de voz.

**Interface já preparada pela Fase 1 (apenas documentada aqui):**

```python
# app/engines/llm_router.py (Fase 2)
class LLMRouter:
    async def classify_intent(
        self,
        message: str,
        session_context: dict,         # últimas 3 msgs + session_data atual
        known_intents: list[str],      # ids do faq.json
    ) -> "LLMClassification":
        ...

class LLMClassification(BaseModel):
    intent_id: str | None              # None = fora do escopo
    confidence: float                  # 0.0 – 1.0
    reasoning: str | None              # para debug log, não mostrado ao cliente
```

**Opções de modelo — comparativo baseado em pesquisa:**

| Opção | Modelo | Custo estimado (1k queries/dia) | Observação |
|---|---|---|---|
| **Recomendada** | Claude Haiku 4.5 (Anthropic) | ~R$ 83/mês | PT-BR nativo forte, low-latency, boa qualidade de classificação |
| Alternativa A | GPT-4o-mini (OpenAI) | ~R$ 11/mês | Barato, qualidade PT-BR um pouco inferior |
| Alternativa B | Rasa NLU + DIETClassifier | ~R$ 0 (self-hosted) | Zero custo de API mas exige 30+ utterances/intent rotuladas e VPS com +2 GB RAM |

**Por que não fine-tuning na Fase 2:** exige dados rotulados que só começam a existir após meses de Fase 1 em produção. O campo `messages.matched_intent_id` é o dataset futuro.

**Prompt de classificação (template base):**

```python
SYSTEM_PROMPT = """Você é um classificador de intenções do chatbot da Camisart
(loja de uniformes em Belém/PA). Analise a mensagem do cliente e classifique
em EXATAMENTE uma das intenções abaixo, ou retorne "fora_do_escopo".

Intenções disponíveis: {intent_ids}

Responda SOMENTE com JSON: {{"intent_id": "...", "confidence": 0.0}}
Sem explicação, sem texto adicional."""
```

**Thresholds de confiança:**

```python
CONFIDENCE_THRESHOLDS = {
    "high":   0.85,   # aplica intent automaticamente
    "medium": 0.60,   # aplica mas registra para revisão
    "low":    0.40,   # pede confirmação ("Você quis dizer X?")
    "reject": 0.00,   # fallback para humano
}
```

**Esforço estimado:** 1 sprint (2 semanas).

---

### Fase 3 — RAG sobre Catálogo (ADR: Vector Database)

**Decisão proposta:** manter `pgvector` para a Fase 3, com gate de escala para migração futura a `Qdrant` caso o catálogo cresça significativamente.

**Comparativo — justificativa da escolha:**

| Critério | pgvector | ChromaDB | Qdrant |
|---|---|---|---|
| Infraestrutura adicional | Nenhuma (usa Postgres existente) | Python lib, sem servidor | Servidor separado (Rust) |
| Limite de dimensões indexáveis | **2 000** (HNSW) | Sem limite prático | Sem limite prático |
| Latência de busca | ~1,5 ms (HNSW) | ms-level em baixa escala | sub-10 ms em produção |
| Custo mensal | R$ 0 (já pago no VPS) | R$ 0 | R$ 0 self-hosted |
| Hybrid search (BM25 + vector) | Complexo (precisa pg_trgm) | Não nativo | **Nativo** |
| Filtros por metadata (segmento, produto) | SQL WHERE simples | API de filtros | Filterable HNSW |

**Conclusão:** para o catálogo da Camisart (~50–200 produtos atuais), pgvector é suficiente, evita nova infra e aproveita a stack PostgreSQL já decidida. Se o catálogo crescer para 10k+ itens ou a Camisart expandir para um catálogo de um sister-brand como CM Têxtil, migrar para Qdrant atrás da mesma interface `RAGEngine.query()`.

**Modelo de embedding:** `text-embedding-3-small` da OpenAI (1536 dimensões, dentro do limite de 2000 do pgvector HNSW). Custo de indexar 200 produtos: **< R$ 0,01** (uma vez).

**Chunking:** document-based — 1 produto = 1 documento. Produtos têxteis têm 100–400 tokens de conteúdo, não requerem split.

```python
def produto_to_document(produto: dict) -> Document:
    content = f"""
    {produto['nome']} — {produto['tecido']}
    Preços: {json.dumps(produto['precos'])}
    Tamanhos: {', '.join(produto.get('tamanhos', []))}
    Segmentos: {', '.join(produto.get('segmentos', []))}
    Personalizações: {', '.join(produto.get('personalizacoes', []))}
    """
    metadata = {
        "produto_id": produto["id"],
        "segmento": produto.get("segmentos", []),
        "preco_min": min(produto["precos"].values()) if produto["precos"] else None,
    }
    return Document(page_content=content.strip(), metadata=metadata)
```

**Separação obrigatória dados estáticos vs dinâmicos:**

- **Vector store (pgvector):** specs, descrição, tamanhos, segmentos — reindexa via script quando o catálogo muda.
- **Postgres `products` table (novo na Fase 3):** preço atual, estoque, disponibilidade — consultado em tempo real pelo `RAGEngine` antes de responder.

**Fluxo RAG:** `LLMRouter` detecta intenção de "consulta de catálogo" → `RAGEngine.query(message, metadata_filter={"segmento": ...})` busca top-K documentos → LLM sintetiza resposta respeitando tom de voz da Camisart → estoque/preço injetados no último passo via lookup SQL.

### Fase 4 — Integrações Externas + Omnichannel + Observabilidade

- **Integração Kommo** (CRM destino — ver §2.2):
  - `KommoClient` em `app/services/integrations/kommo_client.py`
  - Worker periódico lê `leads WHERE synced_to_kommo_at IS NULL`, chama `POST /api/v4/leads`, grava `external_crm_id` e `synced_to_kommo_at`
  - OAuth2 com refresh token armazenado em tabela `integration_credentials`
  - Mapeamento `segmento` → `pipeline_id` no Kommo configurável via `knowledge/integrations.json`
- **Integração RD Station Marketing**:
  - `RDStationClient` em `app/services/integrations/rd_station_client.py`
  - Conversão de evento: `lead_captured` → `POST /platform/conversions`
  - Tags automáticas por segmento (ex: `agro`, `copa_2026`)
  - OAuth2 com refresh token
- **Canal Instagram DM** (mesma engine, novo `Adapter` em `app/adapters/instagram.py`)
- Fluxo de orçamento com cotação automatizada
- Notificações proativas (lançamentos, COP30, Copa 2026) via Template Messages + RD Station campaigns
- Observabilidade completa: Prometheus + Grafana + alertas
- Painel admin (Camisart atualiza preços sem deploy)

---

## 10. Critérios de Aceite da Fase 1

O MVP da Fase 1 é considerado **pronto para piloto** quando:

- [ ] `GET /health` retorna 200 em produção.
- [ ] Webhook da Meta está verificado e recebendo mensagens.
- [ ] Mensagem "qual o preço da polo?" é respondida corretamente em < 5s.
- [ ] Pelo menos 8 intents do FAQ respondidos corretamente (polo, jaleco, básica, regata, endereço, prazo bordado, pedido mínimo, entrega).
- [ ] Fluxo de consulta de pedido funciona (mensagem → estado `AGUARDA_PEDIDO` → resposta).
- [ ] Fluxo de orçamento captura `Lead` no banco com `status='novo'`.
- [ ] Fluxo de catálogo encaminha arquivo PDF (ou texto substituto se PDF Camisart ainda não existir).
- [ ] Cobertura de testes ≥ 70% nas camadas `engines/`, `services/` e `pipeline/`.
- [ ] **Teste estrutural do padrão Adapter passa** — nenhum módulo fora de `app/adapters/whatsapp_cloud/` importa símbolos concretos da Meta (§7.4).
- [ ] `app/pipeline/message_pipeline.py` é 100% agnóstico de canal — aceita `InboundMessage` e devolve `OutboundMessage`.
- [ ] Auditoria `sgp-sprint-review` do Sprint de foundation aprovada.
- [ ] Deploy na VPS Hostinger automatizado via `git pull` + `systemctl restart`.
- [ ] Dona da Camisart validou o fluxo em pelo menos 1 sessão de teste.
- [ ] **Fallback rate < 40%** nas primeiras 48h de piloto com usuários reais (métrica via §4.2.2).
- [ ] Os 5 intents de maior volume do Instagram (preço polo, preço jaleco, bordado/prazo, endereço, pedido mínimo) respondem corretamente nos testes.
- [ ] Mensagens com erro ortográfico comum ("quanto custa a camiza polo?", "tem bordao?") são reconhecidas pelo FAQ Engine (coverage de patterns robusta).
- [ ] Respostas com botões interativos renderizam corretamente no WhatsApp após aprovação do display name da conta Business (§4.2.1).
- [ ] Fluxo de orçamento captura todos os 5 campos de qualificação (segmento, produto, quantidade, personalização, prazo) antes de gravar o `Lead` (§4.5.2).
- [ ] Session timeout de 2h funciona: sessão em `COLETA_QUANTIDADE` + 3h sem interação → próxima mensagem abre `inicio` com saudação de retorno personalizada.
- [ ] `CampaignEngine` carrega sem erro com `campaigns.json` inicial (mesmo com todas as campanhas `enabled: false`).
- [ ] `POST /admin/campaigns/reload` recarrega o arquivo e retorna 200 com lista de campanhas ativas.
- [ ] Campanha com `enabled: false` não injeta intents nem `greeting_override`, mesmo dentro da janela de datas.
- [ ] Campanha com `active_until` no passado não injeta intents mesmo com `enabled: true`.

**Sprint NPS (v1.1):** ← v1.1

- [ ] `python app/migrations/migrate_sprint_nps.py` executa sem erro; segunda execução também (idempotente).
- [ ] `python scripts/generate_nps_mock.py` insere 20 registros em `nps_responses` e grava `data/nps_results.json`.
- [ ] `python scripts/telegram_nps.py` responde `/start` no Telegram, percorre as 5 perguntas e grava resultado em `nps_responses`.
- [ ] `nps_dashboard.html` abre no browser sem servidor e exibe NPS Score, radar e ações recomendadas.

---

## 11. Glossário e Referências

### 11.1. Glossário

- **BSP**: Business Solution Provider — intermediário entre a empresa e a WhatsApp API (Twilio, Zenvia, etc.). Não usamos.
- **Channel Adapter**: classe em `app/adapters/` que traduz entre o canal externo (WhatsApp/Kommo/Instagram) e o formato canônico interno (`InboundMessage`/`OutboundMessage`). Único ponto de dependência com o canal.
- **Cloud API**: a WhatsApp Business API oficial hospedada pela Meta (sem servidor próprio para o WhatsApp).
- **FAQEngine**: módulo determinístico da Fase 1 que casa regex e retorna resposta.
- **InboundMessage / OutboundMessage**: objetos canônicos canal-agnósticos que atravessam o `MessagePipeline`.
- **Intent**: intenção classificada — na Fase 1, é um item do `faq.json` com patterns regex.
- **Kommo**: CRM brasileiro (antigo amoCRM) usado pela Camisart. WhatsApp nativo integrado. Destino de migração da Fase 4+.
- **MessagePipeline**: orquestrador interno que recebe `InboundMessage`, chama engines/services e devolve `OutboundMessage`. Não conhece canal.
- **RD Station**: plataforma brasileira de automação de marketing. Integração na Fase 4.
- **Salesbot**: chatbot visual nativo do Kommo com DSL própria. Opção M2 da §2.3.
- **wa_id**: identificador do WhatsApp do usuário (número em E.164 sem `+`, ex: `5591991800637`).
- **Webhook**: endpoint HTTPS que a Meta chama quando o bot recebe uma mensagem.
- **Template Message**: mensagem pré-aprovada pela Meta, única forma de iniciar conversa após 24h de silêncio.

### 11.2. Documentos internos

- [relatorio_instagram_camisart.md](relatorio_instagram_camisart.md) — análise de 190 posts e 427 comentários
- [Camisart_AI_Blueprint.pdf](Camisart_AI_Blueprint.pdf) — deck estratégico
- [docs/sprint_13/02_PRD.md](sprint_13/02_PRD.md) — PRD Sprint NPS (v1.1) ← v1.1
- `.claude/skills/` — padrões operacionais herdados dos projetos ConfexAI e SGP
  - `confexai-architecture-decisions/SKILL.md`
  - `confexai-sprint-workflow/SKILL.md`
  - `confexai-testing-standards/SKILL.md`
  - `confexai-api-contracts/SKILL.md`
  - `sgp-sprint-review/SKILL.md`

### 11.3. Documentos externos

- [WhatsApp Cloud API Docs](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Webhook setup guide](https://developers.facebook.com/docs/graph-api/webhooks)
- [FastAPI docs](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 docs](https://docs.sqlalchemy.org/en/20/)
- [pgvector (Fase 3)](https://github.com/pgvector/pgvector)
- [Kommo API v4 (Fase 4)](https://developers.kommo.com/reference)
- [RD Station Marketing API (Fase 4)](https://developers.rdstation.com/reference/introducao-api-rd-station-marketing)

---

*Pedra angular do projeto Camisart AI. Qualquer desvio deste documento exige ADR em `docs/decisions/ADRs.md` com justificativa e aprovação.*
