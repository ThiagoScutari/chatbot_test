# PRD — Sprint 02: Conversação
**Projeto:** Camisart AI  
**Branch:** `sprint/02-conversation`  
**Status:** Aprovação Pendente  
**Origem:** Dogfooding Telegram (Sprint 01) + Sprint Review BK-01..BK-11  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S02-01 | `services/` | Startup validation: ADMIN_TOKEN e WHATSAPP_APP_SECRET ≥ 32 chars | 🟡 |
| S02-02 | `migrations/` | Trigger `set_updated_at()` SQL em `sessions` e `leads` | 🟡 |
| S02-03 | `engines/` | `send_catalog` — envia products.json formatado como mensagem real | 🔴 |
| S02-04 | `engines/` | `forward_to_human` — mensagem de handoff + estado terminal com saída | 🔴 |
| S02-05 | `engines/` | `/start` reservado — boas-vindas sem entrar no fluxo de nome | 🟡 |
| S02-06 | `engines/` | StateMachine cobertura ≥ 70% — testes dos paths não cobertos | 🟡 |
| S02-07 | `engines/` | Fluxo de orçamento completo: COLETA_SEGMENTO → COLETA_PRODUTO → COLETA_QTD → COLETA_PERSONALIZACAO → COLETA_PRAZO → CONFIRMACAO → lead capturado | 🔴 |
| S02-08 | `adapters/` | Interactive Messages WhatsApp: botões e listas no `WhatsAppCloudAdapter.send()` | 🟡 |
| S02-09 | `tests/` | Suite completa Sprint 02 — ≥ 70% cobertura em engines/, services/, pipeline/ | 🟡 |
| S02-10 | `docs/` | Atualizar backlog.md — fechar BK-02, BK-03, BK-04, BK-06, BK-07, BK-08, BK-09, BK-10 | 🟢 |

---

## Objetivo do Sprint

Transformar o bot de um **protótipo que responde perguntas** em um **produto que captura negócios**. Ao final deste sprint, o fluxo completo funciona: cliente chega → recebe boas-vindas → tira dúvidas via FAQ → solicita orçamento → bot coleta segmento, produto, quantidade, personalização e prazo → lead gravado no banco com todos os dados → operador recebe notificação interna.

Paralelo: fechar o débito técnico do Sprint 01 (trigger SQL, validação de startup, cobertura de testes).

---

## S02-01 — Startup Validation: tokens mínimos de 32 chars

### Motivação
BK-03. Em produção, um `ADMIN_TOKEN` fraco comprometeria o endpoint de reload de campanhas. Nada impede hoje um token de 6 chars.

### Implementação

```python
# app/config.py — adicionar validator após os campos

from pydantic import model_validator

@model_validator(mode="after")
def validate_secret_lengths(self) -> "Settings":
    if self.APP_ENV == "production":
        if len(self.ADMIN_TOKEN) < 32:
            raise ValueError(
                "ADMIN_TOKEN deve ter pelo menos 32 caracteres em produção. "
                "Gere com: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if len(self.WHATSAPP_APP_SECRET) < 32:
            raise ValueError(
                "WHATSAPP_APP_SECRET deve ter pelo menos 32 caracteres em produção."
            )
    return self
```

### Testes
- `APP_ENV=production` com token curto → `ValidationError` ao instanciar `Settings`
- `APP_ENV=development` com token curto → sem erro (dev flexível)
- `APP_ENV=production` com tokens ≥ 32 chars → sem erro

---

## S02-02 — Trigger set_updated_at() no banco

### Motivação
BK-02. O `onupdate=func.now()` do SQLAlchemy só dispara via ORM. Updates diretos por SQL (migrations futuras, scripts de manutenção, consultas admin) não atualizam `updated_at`. O trigger de banco é a garantia real.

### Implementação

```python
# app/migrations/migrate_sprint_02.py

TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    -- sessions
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_sessions_updated_at'
    ) THEN
        CREATE TRIGGER trg_sessions_updated_at
        BEFORE UPDATE ON sessions
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;

    -- leads
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_leads_updated_at'
    ) THEN
        CREATE TRIGGER trg_leads_updated_at
        BEFORE UPDATE ON leads
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    END IF;
END $$;
"""
```

### Testes
- `UPDATE sessions SET nome_cliente = 'x'` via SQL raw → `updated_at` muda
- `UPDATE leads SET status = 'em_atendimento'` via SQL raw → `updated_at` muda
- Rodar migration duas vezes → idempotente, sem erro

---

## S02-03 — Ação `send_catalog`

### Motivação
BK-07. O bot diz "vou enviar o catálogo" e não envia nada — promessa quebrada, pior que não ter o feature.

### Implementação

O `StateMachine` retorna `action="send_catalog"` no `HandleResult`. O `MessagePipeline` detecta essa action e chama `catalog_service.build_message()` antes de enviar a resposta principal.

```python
# app/services/catalog_service.py

import json
from pathlib import Path
from app.config import settings

def build_catalog_message() -> str:
    """
    Lê products.json e formata como texto WhatsApp/Telegram.
    Retorna string pronta para envio.
    """
    data = json.loads(Path("app/knowledge/products.json").read_text())
    lines = ["👕 *Catálogo Camisart*\n"]

    for p in data.get("products", []):
        preco = p.get("precos", {})
        preco_str = _format_preco(preco)
        line = f"• *{p['nome']}* ({p['tecido']})"
        if preco_str:
            line += f" — {preco_str}"
        lines.append(line)

    lines.append("\nQual produto te interessa? Posso fazer um orçamento! 📋")
    return "\n".join(lines)

def _format_preco(precos: dict) -> str:
    if not precos:
        return "consultar"
    if "varejo" in precos:
        return f"a partir de R$ {precos['varejo']:.2f}"
    if "unidade" in precos:
        return f"R$ {precos['unidade']:.2f}/un"
    if "a_partir_de" in precos:
        return f"a partir de R$ {precos['a_partir_de']:.2f}"
    return "consultar"
```

O `MessagePipeline.process()` verifica `handle_result.action == "send_catalog"` e envia **duas mensagens** em sequência: primeiro o catálogo formatado, depois a mensagem de follow-up do estado.

### Testes
- `build_catalog_message()` retorna string com todos os produtos do `products.json`
- Mensagem contém "Catálogo Camisart"
- Produto sem preço aparece como "consultar"
- Pipeline envia catálogo antes da mensagem de estado

---

## S02-04 — Ação `forward_to_human`

### Motivação
BK-06 e BK-08. O estado `ENCAMINHAR_HUMANO` é um dead-end: o bot diz "te conectando com atendente" mas nunca sai desse estado, então toda mensagem seguinte retorna a mesma frase.

### Implementação

```python
# app/engines/state_machine.py — estado ENCAMINHAR_HUMANO

# Ao entrar no estado:
# 1. Enviar mensagem de handoff
# 2. Mover para estado AGUARDA_RETORNO_HUMANO (novo estado terminal)
# 3. Neste estado, qualquer mensagem recebe resposta de "aguardando"
#    + oferta de voltar ao menu

HANDOFF_MESSAGE = (
    "👤 Estou te conectando com um dos nossos consultores!\n\n"
    "Nosso horário de atendimento é segunda a sexta, das 8h às 18h.\n"
    "Em breve alguém vai te responder por aqui. 😊\n\n"
    "Se preferir, pode continuar me fazendo perguntas enquanto aguarda."
)

AGUARDA_RETORNO_MESSAGE = (
    "Já avisamos nossa equipe! Em breve um consultor vai te atender.\n\n"
    "Posso ajudar com mais alguma coisa enquanto isso?"
)
```

Estado `AGUARDA_RETORNO_HUMANO`:
- Qualquer mensagem → FAQEngine tenta match primeiro (cliente pode tirar dúvida enquanto aguarda)
- Se sem match → `AGUARDA_RETORNO_MESSAGE` + botão "Voltar ao menu"
- Saída do estado: apenas por ação do operador (Fase 4) ou por nova sessão (timeout 2h)

### Testes
- Entrar em `ENCAMINHAR_HUMANO` → bot envia `HANDOFF_MESSAGE` + muda para `AGUARDA_RETORNO_HUMANO`
- Mensagem em `AGUARDA_RETORNO_HUMANO` sem match FAQ → `AGUARDA_RETORNO_MESSAGE`
- Mensagem em `AGUARDA_RETORNO_HUMANO` com match FAQ → resposta do FAQ (cliente não fica bloqueado)
- Timeout de 2h → sessão reseta para `INICIO`

---

## S02-05 — `/start` reservado

### Motivação
BK-09. No Telegram, `/start` é enviado automaticamente ao abrir o bot pela primeira vez. O FAQEngine não tem padrão para ele — cai em fallback, que oferece menu de opções antes de o usuário saber o que é o bot.

### Implementação

```python
# app/knowledge/faq.json — adicionar intent com priority 100 (máxima)

{
  "id": "start_command",
  "priority": 100,
  "patterns": [
    "^/start$",
    "^/start@\\w+$"
  ],
  "response": {
    "type": "text",
    "body": "👋 Olá! Sou o assistente virtual da *Camisart Belém* — sua loja de uniformes!\n\nFaço orçamentos, respondo sobre preços, prazos e bordados. Para começar, qual é o seu nome? 😊"
  },
  "follow_up_state": "aguarda_nome"
}
```

**Nota:** priority 100 garante que `/start` nunca seja capturado por outro pattern antes.

### Testes
- `/start` → intent `start_command`, não fallback
- `/start@camisart_dev_bot` → mesmo resultado
- Estado após `/start` → `aguarda_nome`

---

## S02-06 — StateMachine cobertura ≥ 70%

### Motivação
BK-04. `state_machine.py` ficou em 51% no Sprint 01. Os paths não cobertos são justamente os mais críticos para produção: estados intermediários do orçamento e transições inesperadas.

### Testes a adicionar em `tests/test_state_machine.py`

```python
# Cenários mínimos a cobrir:

# 1. INICIO → resposta de boas-vindas (com e sem campanha ativa)
# 2. AGUARDA_NOME → salva nome_cliente e move para MENU
# 3. MENU → input "1" / "consultar_pedido" → AGUARDA_PEDIDO
# 4. MENU → input "2" / "ver_catalogo" → ENVIA_CATALOGO com action=send_catalog
# 5. MENU → input "3" / "falar_humano" → ENCAMINHAR_HUMANO com action=forward_to_human
# 6. MENU → FAQ match de alta prioridade responde sem mudar estado
# 7. MENU → sem match → fallback com botões
# 8. AGUARDA_PEDIDO → número válido → resposta de pedido
# 9. AGUARDA_PEDIDO → texto inválido → pede novamente
# 10. ENCAMINHAR_HUMANO → move para AGUARDA_RETORNO_HUMANO
# 11. AGUARDA_RETORNO_HUMANO → FAQ match → responde e mantém estado
# 12. AGUARDA_RETORNO_HUMANO → sem match → AGUARDA_RETORNO_MESSAGE
# 13. Estado desconhecido → reseta para INICIO (defensive path)
```

---

## S02-07 — Fluxo de orçamento completo

### Motivação
O fluxo de captura de lead está esboçado mas incompleto. O bot coleta segmento (menu) → produto (lista filtrada pelo segmento) → quantidade → personalização → prazo → mostra resumo → captura lead. É o entregável de maior valor de negócio deste sprint.

### Estados novos

```
COLETA_ORCAMENTO_SEGMENTO
  ↓ (usuário escolhe: Corporativo / Saúde / Indústria / Doméstica / Outro)
COLETA_ORCAMENTO_PRODUTO
  ↓ (lista filtrada por segmento via products.json)
COLETA_ORCAMENTO_QTD
  ↓ ("Quantas peças você precisa?")
COLETA_ORCAMENTO_PERSONALIZACAO
  ↓ (botões: Bordado / Serigrafia / Sem personalização)
COLETA_ORCAMENTO_PRAZO
  ↓ ("Quando você precisa? Ex: 15 dias, urgente, sem pressa")
CONFIRMACAO_ORCAMENTO
  ↓ (mostra resumo + botões: Confirmar / Corrigir)
LEAD_CAPTURADO
```

### Implementação do resumo antes de capturar

```python
# Mensagem de confirmação antes do lead.capture()
RESUMO_TEMPLATE = (
    "📋 *Resumo do seu orçamento:*\n\n"
    "• Segmento: {segmento}\n"
    "• Produto: {produto}\n"
    "• Quantidade: {quantidade} peças\n"
    "• Personalização: {personalizacao}\n"
    "• Prazo: {prazo}\n\n"
    "Está correto?"
)
```

### Dados de segmento → produto (de products.json)

```python
PRODUTOS_POR_SEGMENTO = {
    "corporativo": ["polo_piquet", "basica_algodao"],
    "saude":       ["jaleco_tradicional", "jaleco_premium"],
    "industria":   ["polo_piquet", "basica_pv"],
    "domestica":   ["uniforme_domestica"],
    "outro":       ["polo_piquet", "basica_algodao", "regata"],
}
```

### Testes
- Fluxo completo ponta-a-ponta: segmento → produto → qtd → personalização → prazo → confirmar → `Lead` criado no banco
- Lead capturado tem `status='novo'` e `audit_log` correspondente
- Usuário digita "corrigir" na confirmação → volta para `COLETA_ORCAMENTO_QTD`
- Quantidade inválida (texto, zero, negativo) → bot pede novamente sem avançar estado
- `CampaignEngine.default_segmento()` usado como segmento quando campanha ativa

---

## S02-08 — Interactive Messages WhatsApp

### Motivação
BK-10. O `WhatsAppCloudAdapter.send()` atualmente envia tudo como texto simples. Os botões do WhatsApp (interactive button reply) devem ser ativados após aprovação do display name da conta Business.

### Implementação

```python
# app/adapters/whatsapp_cloud/adapter.py — método send()

def _build_meta_payload(self, outbound: OutboundMessage) -> dict:
    response = outbound.response
    r_type = response.get("type", "text")

    if r_type == "buttons" and response.get("buttons"):
        return {
            "messaging_product": "whatsapp",
            "to": outbound.channel_user_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": response["body"]},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                        for b in response["buttons"][:3]  # Meta max = 3
                    ]
                }
            }
        }

    if r_type == "list" and response.get("list_items"):
        return {
            "messaging_product": "whatsapp",
            "to": outbound.channel_user_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": response["body"]},
                "action": {
                    "button": response.get("list_button_label", "Ver opções"),
                    "sections": [{
                        "rows": [
                            {"id": item["id"], "title": item["title"],
                             "description": item.get("description", "")}
                            for item in response["list_items"][:10]  # Meta max = 10
                        ]
                    }]
                }
            }
        }

    # Fallback: text
    return {
        "messaging_product": "whatsapp",
        "to": outbound.channel_user_id,
        "type": "text",
        "text": {"body": response.get("body", "")}
    }
```

**Estratégia de rollout** (já documentada no spec §4.2.1):
- Deploy com `type: "text"` até display name aprovado
- Após aprovação: editar `faq.json` (só dado, zero código) e chamar `POST /admin/campaigns/reload`

### Testes
- `type="buttons"` → payload `interactive.type = "button"` com 3 botões
- `type="list"` → payload `interactive.type = "list"`
- `type="text"` → payload `type = "text"` simples
- Mais de 3 botões → truncado para 3 (Meta limit)
- Meta API mockada em todos os testes — nunca chamada de verdade

---

## S02-09 — Suite de testes completa Sprint 02

### Meta de cobertura
- `app/engines/state_machine.py` ≥ 70% (era 51% no Sprint 01)
- `app/services/catalog_service.py` ≥ 80%
- `app/adapters/whatsapp_cloud/adapter.py` ≥ 80%
- Cobertura global ≥ 75%

### Arquivos de teste

```
tests/
  test_startup_validation.py     ← S02-01 (3 testes)
  test_migration_02.py           ← S02-02 (3 testes — trigger SQL)
  test_catalog_service.py        ← S02-03 (4 testes)
  test_state_machine.py          ← S02-06 + S02-04 + S02-05 + S02-07 (≥ 20 testes)
  test_whatsapp_interactive.py   ← S02-08 (5 testes)
```

**Total alvo: ≥ 35 testes novos. Total acumulado: ≥ 102 testes. 0 falhas.**

---

## Ordem de Execução

```
S02-01 → S02-02 → S02-05 → S02-03 → S02-04 → S02-07 → S02-06 → S02-08 → S02-09 → S02-10
```

S02-01 e S02-02 são independentes e rápidos — fechar débito técnico primeiro.  
S02-05 (`/start`) é pré-requisito de S02-07 (fluxo de orçamento usa o mesmo FSM).  
S02-03 e S02-04 desbloqueiam as ações do S02-07.  
S02-06 acompanha S02-04 e S02-07 (testes dos novos estados).  
S02-08 é independente — pode ser feito em paralelo após S02-03.  
S02-09 é contínuo — testes escritos junto com cada item.  
S02-10 fecha o sprint.

---

## Commits Atômicos Esperados

```
feat(config): validação de comprimento mínimo de tokens no startup [S02-01]
feat(migrations): trigger set_updated_at() em sessions e leads [S02-02]
feat(services): CatalogService — formata products.json para envio [S02-03]
feat(engine): ação forward_to_human + estado AGUARDA_RETORNO_HUMANO [S02-04]
feat(engine): intent start_command com priority 100 [S02-05]
test(engine): state_machine cobertura >= 70% [S02-06]
feat(engine): fluxo de orçamento completo 6 estados + lead capturado [S02-07]
feat(adapter): WhatsApp Interactive Messages — buttons e list [S02-08]
test(sprint02): suite completa >= 35 testes novos, 0 falhas [S02-09]
docs(backlog): fecha BK-02..BK-10 do Sprint 02 [S02-10]
```

---

## Critérios de Aceite

- [ ] `APP_ENV=production` com token < 32 chars levanta `ValidationError` com mensagem clara
- [ ] UPDATE direto em `sessions` via SQL raw → `updated_at` atualiza
- [ ] `/start` → boas-vindas, não fallback
- [ ] "ver_catalogo" → lista real de produtos da Camisart entregue na conversa
- [ ] "falar_humano" → mensagem de handoff + estado `AGUARDA_RETORNO_HUMANO`
- [ ] Mensagem em `AGUARDA_RETORNO_HUMANO` com FAQ match → resposta correta, estado mantido
- [ ] Fluxo completo de orçamento: segmento → produto → qtd → personalização → prazo → confirmação → `Lead` no banco com `status='novo'`
- [ ] `Lead` capturado tem `audit_log` com `action_type='lead.captured'`
- [ ] Quantidade inválida (texto) no orçamento → bot pede novamente
- [ ] `WhatsAppCloudAdapter.send()` com `type="buttons"` → payload `interactive.type="button"`
- [ ] Coverage ≥ 70% em `state_machine.py`
- [ ] Coverage global ≥ 75%
- [ ] 0 testes falhando
- [ ] CI verde na branch `sprint/02-conversation`
- [ ] `camisart-sprint-review` executado e aprovado antes do merge
