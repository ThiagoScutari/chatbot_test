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
