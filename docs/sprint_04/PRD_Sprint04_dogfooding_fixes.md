# PRD — Sprint 04: Correções do Dogfooding
**Projeto:** Camisart AI  
**Branch:** `sprint/04-dogfooding-fixes`  
**Status:** Aprovação Pendente  
**Origem:** Relatório de Dogfooding `docs/dogfood/2026-04-22_relatorio.md`  
**Skill de referência:** `camisart-sprint-workflow`  
**Review de encerramento:** `camisart-sprint-review`  

---

## Entregáveis do Sprint

| ID | Módulo | Descrição | Prioridade |
|---|---|---|---|
| S04-01 | `engines/` | State machine aceita texto livre nos estados de orçamento | 🔴 |
| S04-02 | `engines/` | Intent `falar_humano` com padrão regex para texto livre | 🔴 |
| S04-03 | `services/` | `session_data` persiste no polling — commit após rate limit check | 🟡 |
| S04-04 | `pipeline/` | Pipeline executa action `send_catalog` no Telegram | 🟡 |
| S04-05 | `knowledge/` | Regex para variações geográficas e ortográficas (C06, C10) | 🟢 |
| S04-06 | `scripts/` | `dogfood_checklist.py` aceita "ok"/"sim"/"s" como PASS | 🟢 |
| S04-07 | `tests/` | Suite atualizada — testes com texto livre nos estados | 🟡 |
| S04-08 | `docs/` | Re-executar dogfooding e registrar novo relatório | 🔴 |

---

## Objetivo do Sprint

Corrigir as 7 falhas do dogfooding de 22/04. Ao final deste sprint, os 20 cenários do checklist passam com ✅ PASS e o `go_live_checklist.md` pode ser preenchido com os critérios de produto.

---

## S04-01 — State machine aceita texto livre nos estados de orçamento

### Causa raiz
Os testes unitários do Sprint 02 mockavam sessões passando IDs exatos de botões (`"corp"`, `"saude"`, `"confirmar"`). No Telegram real, o usuário digita texto livre — `"Corporativo"`, `"saúde"`, `"sim"` — e a state machine não reconhece.

O problema está em cada handler de estado de orçamento: eles fazem `if message == "button_id"` em vez de normalizar e comparar.

### Implementação

```python
# app/engines/state_machine.py
# Adicionar função de normalização de input para estados de orçamento

def _normalize_choice(text: str) -> str:
    """Normaliza input do usuário para comparação com IDs de opções."""
    import unicodedata
    t = text.lower().strip()
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t

# Mapeamentos de texto livre → ID canônico
SEGMENTO_MAP = {
    # corporativo
    "corporativo": "corporativo", "corp": "corporativo",
    "empresa": "corporativo", "uniforme empresa": "corporativo",
    # saude
    "saude": "saude", "saúde": "saude", "medico": "saude",
    "hospital": "saude", "clinica": "saude", "jaleco": "saude",
    # industria
    "industria": "industria", "indústria": "industria",
    "fabrica": "industria", "fábrica": "industria",
    # domestica
    "domestica": "domestica", "doméstica": "domestica",
    "diarista": "domestica", "babá": "domestica",
    # outro
    "outro": "outro", "outros": "outro", "diferente": "outro",
    "nenhum": "outro",
}

PERSONALIZACAO_MAP = {
    "bordado": "bordado", "bordar": "bordado",
    "serigrafia": "serigrafia", "estampa": "serigrafia",
    "sem": "sem_personalizacao", "nenhum": "sem_personalizacao",
    "sem personalizacao": "sem_personalizacao",
    "sem personalização": "sem_personalizacao",
    "nao": "sem_personalizacao", "não": "sem_personalizacao",
}

CONFIRMACAO_MAP = {
    "confirmar": "confirmar", "confirmo": "confirmar",
    "sim": "confirmar", "s": "confirmar", "ok": "confirmar",
    "isso": "confirmar", "correto": "confirmar", "certo": "confirmar",
    "corrigir": "corrigir", "corrigir": "corrigir",
    "nao": "corrigir", "não": "corrigir", "errado": "corrigir",
    "mudar": "corrigir", "alterar": "corrigir",
}
```

Aplicar `_normalize_choice()` + mapeamento em cada estado:

```python
# COLETA_ORCAMENTO_SEGMENTO
normalized = _normalize_choice(message)
segmento_id = SEGMENTO_MAP.get(normalized)
if not segmento_id:
    # tenta match parcial — "saúde mental" → "saude"
    for key, val in SEGMENTO_MAP.items():
        if key in normalized:
            segmento_id = val
            break
if not segmento_id:
    return HandleResult(
        response="Não entendi. Por favor escolha uma opção:\n\n"
                 "1. Corporativo\n2. Saúde\n3. Indústria\n4. Doméstica\n5. Outro",
        next_state="coleta_orcamento_segmento"
    )
```

Mesmo padrão para `COLETA_ORCAMENTO_PERSONALIZACAO` e `CONFIRMACAO_ORCAMENTO`.

Para `COLETA_ORCAMENTO_PRODUTO`, o usuário digita o nome do produto em texto livre. Usar match parcial contra os nomes do `PRODUTOS_POR_SEGMENTO`:

```python
# Match parcial por nome de produto
produto_input = _normalize_choice(message)
produtos_disponiveis = PRODUTOS_POR_SEGMENTO.get(
    session.session_data.get("orcamento_segmento", "outro"), []
)
produto_escolhido = None
for p in produtos_disponiveis:
    if _normalize_choice(p) in produto_input or produto_input in _normalize_choice(p):
        produto_escolhido = p
        break
if not produto_escolhido and len(produtos_disponiveis) == 1:
    produto_escolhido = produtos_disponiveis[0]  # único produto → seleciona automaticamente
if not produto_escolhido:
    lista = "\n".join(f"{i+1}. {p}" for i, p in enumerate(produtos_disponiveis))
    return HandleResult(
        response=f"Qual produto você precisa?\n\n{lista}",
        next_state="coleta_orcamento_produto"
    )
```

### Testes
- `"Saúde"` → segmento `"saude"` ✅
- `"sou da área de saúde"` → segmento `"saude"` (match parcial) ✅
- `"Bordado"` → personalização `"bordado"` ✅
- `"Sim"` → confirmação `"confirmar"` ✅
- `"não"` → confirmação `"corrigir"` ✅
- Input desconhecido → re-pergunta com lista de opções ✅
- Segmento com 1 produto → produto selecionado automaticamente ✅

---

## S04-02 — Intent `falar_humano` com padrão regex para texto livre

### Causa raiz
`falar_humano` existe como ID de botão no fallback e no menu, mas não há intent no `faq.json` que case frases como "falar com atendente", "quero falar com uma pessoa", "preciso de ajuda humana".

### Implementação

```json
// app/knowledge/faq.json — adicionar intent com priority 15

{
  "id": "falar_humano",
  "priority": 15,
  "patterns": [
    "\\b(falar|chamar|quero|preciso|atendente|humano|pessoa|vendedor|consultor)\\b.*\\b(humano|atendente|pessoa|vendedor|consultor|real)\\b",
    "\\b(atendente|vendedor|consultor|humano)\\b",
    "\\b(falar com (alguém|alguem|uma pessoa|um atendente|um vendedor))\\b",
    "\\b(me (ajuda|ajude|atende|atenda))\\b",
    "\\btransfer[ei]r?\\b",
    "\\b(nao consigo|não consigo|nao entend|não entend)\\b"
  ],
  "response": {
    "type": "buttons",
    "body": "👤 Vou te conectar com um consultor!\n\nAtendimento: *segunda a sexta, 8h às 18h*.\nEm breve alguém vai te responder. 😊",
    "buttons": [
      {"id": "falar_humano", "title": "✅ Conectar agora"},
      {"id": "menu",         "title": "🏠 Voltar ao menu"}
    ]
  },
  "follow_up_state": "encaminhar_humano"
}
```

**Nota:** `priority 15` garante precedência sobre o fallback (sem priority = 0) mas não interfere com FAQs de produto (priority 5-10).

### Testes
- `"falar com atendente"` → intent `falar_humano` ✅
- `"quero falar com uma pessoa"` → intent `falar_humano` ✅
- `"preciso de um vendedor"` → intent `falar_humano` ✅
- `"atendente"` → intent `falar_humano` ✅
- `"não consigo entender"` → intent `falar_humano` ✅

---

## S04-03 — `session_data` persiste no polling

### Causa raiz
`scripts/telegram_polling.py` cria `SessionLocal()` por mensagem e chama `db.close()` após o processamento. O `check_rate_limit()` atualiza `session.session_data` em memória via ORM, mas sem `db.commit()` explícito após a atualização — a janela deslizante nunca persiste entre mensagens.

### Implementação

```python
# app/services/session_service.py — update_rate_limit_data()
# O check_rate_limit já modifica session.session_data mas
# quem chama precisa garantir o commit

# app/pipeline/message_pipeline.py
# Após check_rate_limit(), sempre commitar session antes de retornar:

async def process(self, inbound: InboundMessage, db: Session) -> OutboundMessage | None:
    session, was_reset = session_service.get_or_create_session(...)
    db.add(session)
    db.commit()  # ← persiste session_data atualizado (rate limit window)

    if not session_service.check_rate_limit(session):
        db.commit()  # ← persiste o contador incrementado
        return None  # bloqueado
    db.commit()  # ← persiste rl_count atualizado
    ...
```

**Alternativa mais robusta:** tornar `check_rate_limit()` responsável pelo commit do contador:

```python
# app/services/session_service.py
def check_rate_limit(session: SessionModel, db: Session) -> bool:
    """
    Verifica e persiste o rate limit.
    Retorna True se permitido, False se excedido.
    db é necessário para persistir o contador.
    """
    allowed = _check_and_increment(session)
    db.add(session)
    db.commit()  # garante persistência independente do caller
    return allowed
```

Atualizar todos os callers para passar `db` como argumento.

### Testes
- 10 mensagens em sequência → todas permitidas, contador = 10 no banco
- 11ª mensagem → bloqueada, `rl_count` = 11 no banco
- Nova janela após 1 minuto → contador reseta, mensagem permitida
- `inspect_session.py --last` após 11 mensagens → `session_data` mostra `rl_count: 11`

---

## S04-04 — Pipeline executa action `send_catalog` no Telegram

### Causa raiz
O `MessagePipeline.process()` verifica `handle_result.action == "send_catalog"` e chama `catalog_service.build_catalog_message()`, mas envia a mensagem de catálogo **apenas pelo adapter do canal**. O `telegram_polling.py` chama `pipeline.process()` e depois `adapter.send(outbound)` — mas `outbound` contém apenas a resposta principal, não o catálogo.

A pipeline precisa retornar **duas** `OutboundMessage` quando a action é `send_catalog`, ou o catálogo deve ser enviado dentro do pipeline antes de retornar.

### Implementação

Solução: o pipeline envia o catálogo diretamente via adapter antes de retornar o `OutboundMessage` principal.

```python
# app/pipeline/message_pipeline.py

async def process(
    self, inbound: InboundMessage, db: Session
) -> OutboundMessage | None:
    ...
    handle_result = state_machine.handle(message, session, self._faq_engine)

    # Executar actions antes de retornar
    if handle_result.action == "send_catalog":
        catalog_text = catalog_service.build_catalog_message()
        catalog_outbound = OutboundMessage(
            channel_id=inbound.channel_id,
            channel_user_id=inbound.channel_user_id,
            response={"type": "text", "body": catalog_text}
        )
        # Enviar catálogo imediatamente via registry
        from app.adapters.registry import get as get_adapter
        try:
            adapter = get_adapter(inbound.channel_id)
            await adapter.send(catalog_outbound)
        except Exception as exc:
            logger.error("Erro ao enviar catálogo: %s", exc)

    elif handle_result.action == "capture_lead":
        _capture_lead(session, handle_result, db)

    elif handle_result.action == "forward_to_human":
        pass  # estado já foi atualizado pelo state machine

    # Retorna a mensagem de follow-up (pergunta ou confirmação)
    ...
```

**Nota:** esta implementação usa `registry.get()` — por isso S03-04 era pré-requisito. ✅

### Testes
- `action == "send_catalog"` → `adapter.send()` chamado com catálogo antes do outbound principal
- Catálogo enviado contém nomes dos produtos
- `mock_send` chamado 2x: primeiro catálogo, depois mensagem de follow-up

---

## S04-05 — Regex para variações geográficas e ortográficas

### Causa raiz (C06 e C10)
- C06: `"Camiza Polu"` — o padrão de polo já cobre `polo` mas não variações com `u` final
- C10: `"Entrega em SC"` e `"Entrega em São Paulo"` — o intent `entrega_nacional` tem padrões muito restritivos

### Implementação

```json
// app/knowledge/faq.json

// Atualizar intent "entrega_nacional" — adicionar patterns:
"\\b(entrega|envi[ao]|manda|frete)\\b.*\\b(SC|SP|RJ|MG|RS|PR|BA|CE|PA|AM|PE|GO|DF|MS|MT|RO|AC|RR|AP|TO|MA|PI|RN|PB|AL|SE|ES)\\b",
"\\b(entrega|envi[ao])\\b.*\\b(s[aã]o paulo|rio de janeiro|santa catarina|minas gerais|paran[aá]|bahia|cear[aá]|goi[aá]s|mato grosso)\\b",
"\\b(outro estado|outros estados|qualquer estado|todo.*brasil|brasil todo)\\b",
"\\b(fora d[eo] (bel[eé]m|par[aá]))\\b"

// Atualizar intent "preco_polo" — adicionar pattern tolerante:
"\\bpol[ou]\\b.*\\b(pre[çc][oa]|valor|quanto)\\b",
"\\b(pre[çc][oa]|valor|quanto)\\b.*\\bpol[ou]\\b",
"\\bcami[zs][ai].*pol[ou]\\b"
```

### Testes
- `"Entrega em SC"` → intent `entrega_nacional` ✅
- `"Entrega em São Paulo"` → intent `entrega_nacional` ✅
- `"Fora do Pará"` → intent `entrega_nacional` ✅
- `"Camiza Polu"` → intent `preco_polo` ✅

---

## S04-06 — `dogfood_checklist.py` aceita "ok"/"sim"/"s" como PASS

### Causa raiz
O script só reconhece `"PASS"` exato. Durante o teste, respostas naturais como `"ok"`, `"sim"` foram registradas como `⚠️ OBS` em vez de `✅ PASS`, fazendo com que 11 cenários válidos virassem observações em vez de passes — e o veredicto ficou errado.

### Implementação

```python
# scripts/dogfood_checklist.py — atualizar parsing da resposta

PASS_ALIASES = {"pass", "p", "ok", "sim", "s", "yes", "y", "certo", "correto", "✅"}
FAIL_ALIASES = {"fail", "f", "falhou", "errou", "não", "nao", "n", "❌"}
SKIP_ALIASES = {"skip", "pular", "sk"}

resposta_lower = resposta.strip().lower()

if resposta_lower in PASS_ALIASES:
    status = "✅ PASS"
    obs = ""
elif resposta_lower in FAIL_ALIASES or resposta_lower.startswith("fail"):
    status = "❌ FAIL"
    obs = resposta[4:].strip(": ") if resposta_lower.startswith("fail") else ""
elif resposta_lower in SKIP_ALIASES:
    status = "⏭️ SKIP"
    obs = ""
elif resposta_lower.startswith("obs:"):
    status = "⚠️ OBS"
    obs = resposta[4:].strip()
else:
    # Qualquer outro texto → OBS com o texto como observação
    status = "⚠️ OBS"
    obs = resposta
```

Também atualizar o veredicto para considerar OBS como não-bloqueante:

```python
# Veredicto baseado apenas em FAILs — OBS não reprovam
veredicto = "✅ APROVADO" if failed == 0 else \
            "⚠️ APROVADO COM RESSALVAS" if failed <= 2 else \
            "❌ REPROVADO"
```

---

## S04-07 — Testes com texto livre nos estados

### Novos testes em `tests/test_state_machine.py`

```python
# Texto livre nos estados de orçamento

def test_segmento_texto_livre_saude(faq):
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("saúde", s, faq)
    assert r.next_state == "coleta_orcamento_produto"
    assert s.session_data["orcamento_segmento"] == "saude"

def test_segmento_texto_livre_corporativo(faq):
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("Corporativo", s, faq)
    assert r.next_state == "coleta_orcamento_produto"

def test_segmento_desconhecido_repergunta(faq):
    s = make_session("coleta_orcamento_segmento", nome="Maria")
    r = handle("xablau", s, faq)
    assert r.next_state == "coleta_orcamento_segmento"

def test_personalizacao_texto_livre(faq):
    s = make_session("coleta_orcamento_personalizacao", nome="Maria",
                     data={"orcamento_segmento": "corporativo",
                           "orcamento_produto": "Camisa Polo",
                           "orcamento_quantidade": 50})
    r = handle("Bordado", s, faq)
    assert r.next_state == "coleta_orcamento_prazo"
    assert s.session_data["orcamento_personalizacao"] == "bordado"

def test_confirmacao_sim(faq):
    s = make_session("confirmacao_orcamento", nome="Maria",
                     data={"orcamento_segmento": "corporativo",
                           "orcamento_produto": "Camisa Polo",
                           "orcamento_quantidade": 50,
                           "orcamento_personalizacao": "bordado",
                           "orcamento_prazo": "15 dias"})
    r = handle("sim", s, faq)
    assert r.action == "capture_lead"

def test_confirmacao_nao(faq):
    s = make_session("confirmacao_orcamento", nome="Maria",
                     data={"orcamento_segmento": "corporativo",
                           "orcamento_produto": "Camisa Polo",
                           "orcamento_quantidade": 50,
                           "orcamento_personalizacao": "bordado",
                           "orcamento_prazo": "15 dias"})
    r = handle("não", s, faq)
    assert r.next_state == "coleta_orcamento_qtd"

def test_falar_humano_texto_livre(faq):
    s = make_session("menu", nome="Maria")
    r = handle("falar com atendente", s, faq)
    assert r.next_state in ("encaminhar_humano", "aguarda_retorno_humano") \
        or r.action == "forward_to_human"

def test_send_catalog_action_presente(faq):
    s = make_session("menu", nome="Maria")
    r = handle("ver_catalogo", s, faq)
    assert r.action == "send_catalog"
```

---

## S04-08 — Re-executar dogfooding

Após implementar S04-01 a S04-07:

1. Iniciar polling:
```bash
python scripts/telegram_polling.py
```

2. Executar checklist:
```bash
python scripts/dogfood_checklist.py
```

3. Passar por todos os 20 cenários. Meta: **≥ 18/20 PASS** (90%).

4. Commitar o relatório:
```bash
git add docs/dogfood/
git commit -m "docs(dogfood): relatório pós-correções Sprint 04 [S04-08]"
```

5. Preencher os critérios de produto no `docs/go_live_checklist.md`.

---

## Ordem de Execução

```
S04-06 → S04-02 → S04-05 → S04-01 → S04-03 → S04-04 → S04-07 → S04-08
```

S04-06 primeiro — corrige o script para que o próximo dogfooding registre corretamente.  
S04-02 segundo — adiciona intent antes de testar o menu.  
S04-05 melhora regex — rápido, sem risco.  
S04-01 é o maior item — texto livre na state machine.  
S04-03 e S04-04 dependem de S04-01 estar estável.  
S04-07 acompanha cada item (testes junto com código).  
S04-08 é o fechamento — só após tudo verde.

---

## Commits Atômicos Esperados

```
fix(scripts): dogfood_checklist aceita ok/sim/s como PASS [S04-06]
feat(faq): intent falar_humano com padrões texto livre [S04-02]
fix(faq): regex entrega_nacional cobre estados BR e variações polo [S04-05]
fix(engine): state_machine aceita texto livre nos estados de orçamento [S04-01]
fix(services): check_rate_limit persiste session_data via db.commit [S04-03]
fix(pipeline): send_catalog envia catálogo antes do outbound principal [S04-04]
test(sprint04): testes texto livre + rate limit + send_catalog [S04-07]
docs(dogfood): relatório pós-correções Sprint 04 [S04-08]
```

---

## Critérios de Aceite

- [ ] `"Saúde"` no estado `coleta_orcamento_segmento` → avança para produto
- [ ] `"Sim"` na confirmação → captura lead
- [ ] `"não"` na confirmação → volta para quantidade
- [ ] `"falar com atendente"` → estado `encaminhar_humano`
- [ ] `"Entrega em SC"` → intent `entrega_nacional`
- [ ] `"Camiza Polu"` → intent `preco_polo`
- [ ] 11 mensagens em 1 minuto → 11ª bloqueada
- [ ] "ver catálogo" → catálogo entregue na conversa Telegram
- [ ] Fluxo completo end-to-end: `/start` → nome → menu → orçamento → lead no banco
- [ ] `inspect_session.py --leads` mostra lead com dados corretos após orçamento
- [ ] `dogfood_checklist.py` conta "ok" e "sim" como PASS
- [ ] ≥ 18/20 cenários PASS no dogfooding re-executado
- [ ] 0 testes falhando
- [ ] CI verde na branch `sprint/04-dogfooding-fixes`
- [ ] `camisart-sprint-review` aprovado antes do merge
