# Backlog Estrutural — Camisart AI

Itens identificados na `camisart-sprint-review` do Sprint 01.
Atualizar a cada sprint review.

| ID | Sprint origem | Prioridade | Descrição | Status |
|----|--------------|-----------|-----------|--------|
| BK-01 | Sprint 01 | 🔴 Sprint 02 | S01-09: Deploy VPS Hostinger + certbot + nginx + Meta webhook + validação fim-a-fim com número dedicado | Pendente |
| BK-02 | Sprint 01 | 🟡 Sprint 02 | `set_updated_at()` trigger SQL aplicado via CREATE TRIGGER nas tabelas `sessions` e `leads` (SQLAlchemy `onupdate` não cobre updates por SQL raw) | Pendente |
| BK-03 | Sprint 01 | 🟡 Sprint 02 | Validação no startup: `ADMIN_TOKEN` e `WHATSAPP_APP_SECRET` >= 32 chars com erro explícito ao subir a app | Pendente |
| BK-04 | Sprint 01 | 🟡 Sprint 02 | `state_machine.py` cobertura de testes >= 70% — paths de AGUARDA_PEDIDO, ENVIA_CATALOGO e COLETA_ORCAMENTO_SEGMENTO não cobertos | Pendente |
| BK-05 | Sprint 01 | 🟢 Sprint 03 | Índice explícito em `leads.session_id` para queries de volume | Pendente |
| BK-06 | Sprint 02 (dogfooding Telegram) | 🟡 Sprint 02 | `ENVIA_CATALOGO` virou estado "pegadinha" — usuário precisa de 2 turnos para voltar ao menu. `state_machine` deve retornar MENU no mesmo turno que envia o catálogo, sem estado intermediário | Pendente |
| BK-07 | Sprint 02 (dogfooding Telegram) | 🔴 Sprint 02 | `HandleResult.action` (`send_catalog` / `forward_to_human` / `capture_lead`) é ignorada pelo Pipeline e adapters. Catálogo não é entregue; operador humano não é notificado. `OutboundMessage` precisa carregar `action` + `action_payload` e cada adapter executa side-effect correspondente | Pendente |
| BK-08 | Sprint 02 (dogfooding Telegram) | 🟡 Sprint 02 | `ENCAMINHAR_HUMANO` é dead-end — qualquer input gera a mesma resposta em loop. Permitir: (a) comandos de escape (`/start`, `reiniciar`, `menu`); (b) FAQEngine ainda ativo neste estado; (c) timeout de 30min auto-fecha sessão | Pendente |
| BK-09 | Sprint 02 (dogfooding Telegram) | 🟢 Sprint 02 | Reservar `/start` (comando Telegram padrão) para resetar estado da sessão em qualquer momento | Pendente |
| BK-10 | Sprint 02 (dogfooding Telegram) | 🟢 Sprint 02 | Validar cobertura do FAQEngine em sessão real Telegram — testar `"qual o preço da polo?"`, `"onde fica a loja?"`, `"tem pedido mínimo?"` | Pendente |
| BK-11 | Sprint 02 (dogfooding Telegram) | 🟡 Sprint 02 | Enquanto BK-07 não tratar `send_catalog`, ajustar mensagem de `ENVIA_CATALOGO` para não prometer PDF que não é enviado. Trocar por placeholder honesto até catálogo real Camisart existir | Pendente |
