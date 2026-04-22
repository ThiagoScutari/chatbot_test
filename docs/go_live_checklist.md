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

## Critérios de Produto (validados via Telegram)

- [ ] 20/20 cenários do dogfooding concluídos (`docs/dogfood/`)
- [ ] FAQ coverage ≥ 80% nas perguntas reais (`scripts/faq_coverage_check.py`)
- [ ] Fallback rate < 20% em 48h de uso contínuo
- [ ] Fluxo de orçamento completo end-to-end sem intervenção humana
- [ ] Lead capturado no banco com todos os campos corretos (`inspect_session.py --leads`)
- [ ] Session timeout testado e funcionando
- [ ] Rate limiting testado (11ª mensagem bloqueada)

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
