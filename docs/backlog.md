# Backlog Estrutural — Camisart AI

Itens identificados na `camisart-sprint-review` do Sprint 01.
Atualizar a cada sprint review.

| ID | Sprint origem | Prioridade | Descrição | Status |
|----|--------------|-----------|-----------|--------|
| BK-01 | Sprint 01 | 🔴 Sprint 02 | S01-09: Deploy VPS Hostinger + certbot + nginx + Meta webhook + validação fim-a-fim com número dedicado | Pendente |
| BK-02 | Sprint 01 | 🟡 Sprint 02 | `set_updated_at()` trigger SQL aplicado via CREATE TRIGGER nas tabelas `sessions` e `leads` (SQLAlchemy `onupdate` não cobre updates por SQL raw) | ✅ Fechado Sprint 02 |
| BK-03 | Sprint 01 | 🟡 Sprint 02 | Validação no startup: `ADMIN_TOKEN` e `WHATSAPP_APP_SECRET` >= 32 chars com erro explícito ao subir a app | ✅ Fechado Sprint 02 |
| BK-04 | Sprint 01 | 🟡 Sprint 02 | `state_machine.py` cobertura de testes >= 70% — paths de AGUARDA_PEDIDO, ENVIA_CATALOGO e COLETA_ORCAMENTO_SEGMENTO não cobertos | ✅ Fechado Sprint 02 |
| BK-05 | Sprint 01 | 🟢 Sprint 03 | Índice explícito em `leads.session_id` para queries de volume | ✅ Fechado Sprint 03 |
| BK-06 | Sprint 02 (dogfooding Telegram) | 🟡 Sprint 02 | `ENVIA_CATALOGO` virou estado "pegadinha" — usuário precisa de 2 turnos para voltar ao menu. `state_machine` deve retornar MENU no mesmo turno que envia o catálogo, sem estado intermediário | ✅ Fechado Sprint 02 |
| BK-07 | Sprint 02 (dogfooding Telegram) | 🔴 Sprint 02 | `HandleResult.action` (`send_catalog` / `forward_to_human` / `capture_lead`) é ignorada pelo Pipeline e adapters. Catálogo não é entregue; operador humano não é notificado. `OutboundMessage` precisa carregar `action` + `action_payload` e cada adapter executa side-effect correspondente | ✅ Fechado Sprint 02 |
| BK-08 | Sprint 02 (dogfooding Telegram) | 🟡 Sprint 02 | `ENCAMINHAR_HUMANO` é dead-end — qualquer input gera a mesma resposta em loop. Permitir: (a) comandos de escape (`/start`, `reiniciar`, `menu`); (b) FAQEngine ainda ativo neste estado; (c) timeout de 30min auto-fecha sessão | ✅ Fechado Sprint 02 |
| BK-09 | Sprint 02 (dogfooding Telegram) | 🟢 Sprint 02 | Reservar `/start` (comando Telegram padrão) para resetar estado da sessão em qualquer momento | ✅ Fechado Sprint 02 |
| BK-10 | Sprint 02 (dogfooding Telegram) | 🟢 Sprint 02 | Validar cobertura do FAQEngine em sessão real Telegram — testar `"qual o preço da polo?"`, `"onde fica a loja?"`, `"tem pedido mínimo?"` | ✅ Fechado Sprint 02 |
| BK-11 | Sprint 02 (dogfooding Telegram) | 🟡 Sprint 02 | Enquanto BK-07 não tratar `send_catalog`, ajustar mensagem de `ENVIA_CATALOGO` para não prometer PDF que não é enviado. Trocar por placeholder honesto até catálogo real Camisart existir | Pendente |
| BK-13 | Sprint 02 review | 🟢 Sprint 03 | `app/adapters/registry.py` era código morto — nenhum adapter chamava `register()` e nenhum código chamava `get()`. Integrar no lifespan ou remover | ✅ Fechado Sprint 03 |
| BK-14 | Sprint 02 review | 🟡 Sprint 03 | `tests/test_telegram_adapter.py` usava `asyncio.get_event_loop().run_until_complete()` (deprecated no Python 3.13). Migrar para `@pytest.mark.asyncio` | ✅ Fechado Sprint 03 |
| BK-15 | Sprint 02 review | 🟢 Sprint 03 | Documentar em CLAUDE.md que `app/main.py` em ~57% de cobertura é esperado (lifespan não roda no TestClient) | ✅ Fechado Sprint 03 |
| BK-16 | Sprint 02 review | 🟡 Sprint 03 | `POST /adapters/telegram/webhook` tinha 0% de cobertura — adicionar teste de integração que cubra wiring do endpoint, FAQ trigger, secret inválido e isolation | ✅ Fechado Sprint 03 |
| BK-17 | Sprint 03 review | 🟡 Fase 4 | Encaminhamento por inatividade com SLA — sessão sem resposta há X horas notifica operador automaticamente | Pendente |
| BK-18 | Sprint 03 review | 🟡 Fase 4 | `close_reason` na sessão — registrar motivo de encerramento (resolvido, transferido, abandono, sem resposta) | Pendente |
| BK-19 | Sprint 03 review | 🟢 Fase 4 | Bloqueio de envios para desengajados em campanhas Template Messages — proteger reputação do número Meta | Pendente |
| BK-20 | Sprint 03 review | 🟢 Sprint 04 | Teste de overlap de prioridade entre intents FAQ — garantir que novos intents não roubam match de intents existentes | Pendente |
| BK-21 | Sprint 03 review | 🟢 Sprint 04 | Corrigir SAWarning `transaction already deassociated` no conftest — ruído no output do pytest há 3 sprints | Pendente |
| BK-22 | Sprint 05 review | 🟢 Documentação | C03 (timeout 2h) documentado como teste manual permanente no CLAUDE.md — não automatizável por natureza | ✅ Fechado Sprint 05 |
