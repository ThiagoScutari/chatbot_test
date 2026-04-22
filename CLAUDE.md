# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Context: Two Repositories in One

This is the **Camisart AI** project — a WhatsApp chatbot for Camisart Belém (uniforms store). The repo currently holds two distinct codebases in parallel:

1. **`test/`** — the learning prototype (terminal / Flask web / Telegram bot) with fictional furniture data. **It is runnable and serves as demo for stakeholders.** Do not mistake this for a tests directory — the actual unit tests live at `test/tests/`.
2. **`app/`** — the production codebase for the real Camisart chatbot. **It does not exist yet.** The full specification is in [`docs/project_specz.md`](docs/project_specz.md) — the cornerstone document. Every implementation task starts from there.

The only shared module is `core/` (state machine + handlers + SQLite), which was the engine of the prototype and will be refactored into `app/engines/` and `app/services/` per the spec.

The `README.md` describes the old prototype layout and is out of date. `docs/project_specz.md` is the source of truth.

## The Cornerstone: `docs/project_specz.md`

Before any implementation, architectural discussion, or planning work: **read `docs/project_specz.md`**. It defines:

- Phase 1 scope (Regex + WhatsApp Cloud API + FastAPI + PostgreSQL) — specified in depth, ~2000 lines
- Phase 2–4 as roadmap only (LLM Router → RAG → Kommo/RDStation integration)
- The **Channel Adapter Pattern** (§2.4) — the most important invariant; the chatbot brain must never know which channel delivered the message
- The **migration strategy to Kommo** (§2.2 and §2.3) — the client uses Kommo, and we build in our house to migrate later. Architecture must preserve that path.
- The **Campaign Engine** (§4.7) — seasonal campaigns via `campaigns.json` with hot-reload, no deploy
- Acceptance criteria (§10)

Any divergence from the spec requires an ADR in `docs/decisions/ADRs.md` (not yet created).

## Custom Skills — Must Be Invoked Before Work

Five skills in `.claude/skills/` codify the workflow rules inherited from the architect's other projects (ConfexAI, SGP). Every implementation task must reference these:

| Skill | When to invoke |
|---|---|
| `confexai-sprint-workflow` | Before starting any dev task — defines the 7-step ritual (inspeção → feedback → aprovação → implementação → testes → commits atômicos → PR) |
| `confexai-architecture-decisions` | Before proposing structural changes, libraries, or design patterns — lists immutable decisions (FastAPI monolith, soft delete universal, manual idempotent migrations, etc.) |
| `confexai-api-contracts` | Before creating/modifying FastAPI endpoints or Pydantic schemas — `StandardResponse`, `Literal` types, `deleted_at` filtering |
| `confexai-testing-standards` | Before writing tests — separate test database (`camisart_test_db`, never `camisart_db`), mandatory mocks for external APIs, minimum scenarios per endpoint |
| `sgp-sprint-review` | Before merging a sprint — mandatory adversarial audit on DB, routes, tests, security, docs |

## Commands

### Run the prototype (demonstrations only)

All prototype entry points expect to be run **from within `test/`** (paths inside those scripts resolve relative to `test/`):

```bash
cd test
python etapa1_terminal/main.py           # CLI chatbot
python etapa2_web/app.py                 # Flask web → http://127.0.0.1:5000
set TELEGRAM_BOT_TOKEN=xxx && python etapa3_telegram/bot.py   # Telegram
```

### Run the prototype tests

```bash
cd test
python -m pytest tests/ -v               # 19 tests, configured via test/pytest.ini
```

The tests use pytest `monkeypatch` to swap `core.database.DB_PATH` to a `tmp_path` SQLite — they never touch `test/data/pedidos.db`.

### Production code (once `app/` exists)

The spec prescribes (see §6.1 and §6.3 of the spec for details):

```bash
# Dev
uvicorn app.main:app --reload --port 8000
ngrok http 8000                          # to expose webhook for Meta testing

# Migrations (manual, idempotent, per sprint)
python app/migrations/migrate_sprint_NN.py

# Tests — NEVER call real Meta API; always mock httpx.AsyncClient
pytest -v
```

### Database (production spec)

- Prod: `camisart_db` (PostgreSQL 15+)
- Test: `camisart_test_db` — **never use prod DB in tests**
- Migrations live in `app/migrations/migrate_sprint_NN.py` with matching `rollback_sprint_NN.py`, and must be idempotent

## Directory Layout — What's What

```
chatbot/
├── .claude/skills/          ← 5 skills that define the workflow (MUST READ)
├── core/                    ← shared engine from prototype (states, handlers, SQLite)
│                              will be refactored into app/engines/ and app/services/
├── docs/
│   ├── project_specz.md     ← the cornerstone — read this first
│   ├── Camisart_AI_Blueprint.pdf
│   └── relatorio_instagram_camisart.md   ← business analysis (190 posts, 427 comments)
└── test/                    ← prototype (runnable, not tests in traditional sense)
    ├── etapa1_terminal/     ← CLI chatbot
    ├── etapa2_web/          ← Flask web chatbot
    ├── etapa3_telegram/     ← Telegram bot
    ├── tests/               ← actual pytest unit tests for core/
    ├── data/pedidos.db      ← fictional furniture SQLite (NOT Camisart data)
    ├── docs/Catalogo.pdf    ← the Ferla catalog, NOT Camisart
    ├── dados_instagram/     ← scraped Instagram data
    └── pytest.ini           ← pythonpath = ..  (points to project root)
```

`core/database.py` resolves its SQLite path from `CHATBOT_DB_PATH` env var (set by each `test/etapaN/` entry point to `test/data/pedidos.db`). If the env var is unset, it falls back to a path relative to `core/` which points to a non-existent `data/` at project root — this is intentional to force explicit configuration.

## Architecture Invariants (Production `app/`)

These are not negotiable without an ADR. Read `docs/project_specz.md` for rationale.

- **Channel Adapter Pattern** (§2.4): `app/adapters/` is the **only** layer that knows about WhatsApp Cloud API (or Kommo later). `app/engines/`, `app/services/`, `app/pipeline/` must never import from `app/adapters/<concrete>/`. A structural test in the suite enforces this (§7.4).
- **Sessions and messages are channel-agnostic**: keyed by `(channel_id, channel_user_id)`, not by `wa_id` alone.
- **All PKs are UUIDs** — no autoincrement integers.
- **Soft delete universal**: `is_archived` and/or `deleted_at` on every mutable business entity. Exception documented: `messages` is an immutable log.
- **Every mutation writes `audit_logs` before `db.commit()`**.
- **Leads carry CRM-sync fields** (`external_crm_id`, `synced_to_kommo_at`, `synced_to_rdstation_at`, `sync_metadata`) from day one — NULL in Phase 1, populated in Phase 4.
- **Every `messages` row preserves the original `raw_payload`** — future LLM training data.

## Git and Commits

- Commit format (Portuguese): `tipo(módulo): descrição [SNN-NN]`
  - Types: `feat`, `fix`, `test`, `docs`, `refactor`, `perf`, `devops`, `security`, `prompt`
  - `SNN-NN` references the PRD sprint item, e.g. `[S01-03]`
- One commit per bug/feature. Never group unrelated changes.
- Never `--no-verify`, never `--no-gpg-sign`, never force-push to `main`.
- Never run destructive git commands (`reset --hard`, `push --force`, `branch -D`) without explicit approval.

## Communication

- The architect (project owner) writes in Portuguese. Match his language in commits, PR descriptions, and plan/spec documents.
- Skill-internal discussion and CLAUDE.md can stay in English.

## Python and Types

- Python 3.12+ target.
- Pyright is configured via `pyrightconfig.json` — type errors should be addressed, not suppressed.
- Pydantic v2 for all schemas; use `Literal` types for fixed enumerations (per `confexai-api-contracts`).

## Coverage Notes

### app/main.py — lifespan block (~57% coverage, expected)
The lifespan context manager initializes CampaignEngine, FAQEngine
and registers adapters. This block does NOT execute during tests because
TestClient uses dependency_overrides instead of the full lifespan.

This is intentional. The lifespan IS exercised indirectly via:
- test_health.py (DB connectivity)
- test_campaign_engine.py (engine logic)
- test_regex_engine.py (FAQ engine logic)
- test_adapter_registry.py (adapter registration)

Do not add fake tests to inflate this number.

### app/adapters/*/client.py — ~50-61% coverage, expected
HTTP client modules are always mocked in tests (never call real APIs).
The uncovered lines are the actual HTTP call paths — correct behavior.
These lines are exercised only in production against real Meta/Telegram APIs.

### app/adapters/whatsapp_cloud/schemas.py — 0% coverage, expected
Pydantic models used for documentation and type hints.
Parsing happens in adapter.py which is tested.
Direct schema tests would be redundant.

### tests/helpers/conversation_simulator.py — teste manual permanente C03
C03 (session timeout de 2h) não tem cobertura automatizada por natureza —
requer passagem real de tempo. É o único cenário do dogfooding que permanece
como teste manual. Todos os demais C01-C20 estão cobertos por
tests/test_conversation_flows.py.

Para testar C03 manualmente:
  1. python scripts/telegram_polling.py
  2. Alterar last_interaction_at no banco para 3h atrás:
     UPDATE sessions SET last_interaction_at = NOW() - INTERVAL '3 hours'
     WHERE channel_user_id = '<seu_id_telegram>';
  3. Enviar mensagem — bot deve cumprimentar de volta com nome salvo.
