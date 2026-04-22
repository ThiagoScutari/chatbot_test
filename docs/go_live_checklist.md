# Checklist de Go-Live — Camisart AI

Preencher antes de abrir Sprint de Go-Live (Deploy VPS + WhatsApp).
Todos os itens devem estar ✅ APROVADO.

## Critérios Técnicos

- [ ] 0 testes falhando na suite completa
- [ ] Cobertura global ≥ 80%
- [ ] `state_machine.py` ≥ 70%
- [ ] `adapters/registry.py` ≥ 80%
- [ ] `adapters/telegram/routes.py` ≥ 70%
- [ ] `ruff check app/ scripts/` — 0 erros
- [ ] CI verde no `main`
- [ ] Migrations Sprint 01-03 executadas com sucesso em `camisart_test_db`

## Critérios de Produto (validados por pytest — não requerem Telegram)
- [ ] `test_conversation_flows.py` — todos os C01-C20 passando
- [ ] `test_faq_stress.py` — 80+ variações linguísticas cobertas
- [ ] `test_edge_cases.py` — edge cases e inputs adversariais passando
- [ ] `pytest tests/ -q` — 0 falhas, cobertura >= 82%

## Critérios de UX (validados manualmente via Telegram — somente após pytest verde)
- [ ] Conversa flui naturalmente — tom e formatação das mensagens
- [ ] Botões interativos renderizam corretamente (após display name aprovado)
- [ ] Tempo de resposta < 2s percebido pelo usuário

## Critérios Operacionais (manual)

- [ ] Número dedicado adquirido (não o número atual da Camisart)
- [ ] Conta Meta Business verificada
- [ ] Display name aprovado pela Meta
- [ ] `.env` de produção criado na VPS (nunca commitado)
- [ ] `ADMIN_TOKEN` e `WHATSAPP_APP_SECRET` ≥ 32 chars na VPS
- [ ] Certbot configurado e HTTPS válido
- [ ] Webhook registrado na Meta e respondendo ao handshake
- [ ] Migration Sprint 01-03 executadas na VPS (`camisart_db`)
- [ ] Dona da Camisart validou o fluxo completo ao vivo

## Autorização final

**Data:** ___________
**Aprovado por:** Thiago Scutari
**Veredicto:** APROVADO / REPROVADO
