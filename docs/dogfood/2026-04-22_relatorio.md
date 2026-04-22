# Relatório de Dogfooding — 2026-04-22

**Testador:** Thiago Scutari
**Canal:** Telegram (@camisart_dev_bot)
**Cenários:** 20 executados

## Resultado Geral

| | |
|---|---|
| ✅ PASS | 8 |
| ❌ FAIL | 6 |
| ⏭️ SKIP | 1 |
| **Veredicto** | **❌ REPROVADO** |

## Detalhamento

| Cenário | Status | Observação |
|---------|--------|-----------|
| C01 | ✅ PASS | — |
| C02 | ✅ PASS | — |
| C03 | ⏭️ SKIP | — |
| C04 | ✅ PASS | — |
| C05 | ✅ PASS | — |
| C06 | ✅ PASS | — |
| C07 | ✅ PASS | — |
| C08 | ✅ PASS | — |
| C09 | ✅ PASS | — |
| C10 | ❌ FAIL | — |
| C11 | ❌ FAIL | — |
| C12 | ⚠️ OBS | encerrar |
| C13 | ⚠️ OBS | encerrar |
| C14 | ⚠️ OBS | encerrar |
| C15 | ⚠️ OBS | encerrar |
| C16 | ⚠️ OBS | encerrar |
| C17 | ❌ FAIL | — |
| C18 | ❌ FAIL | — |
| C19 | ❌ FAIL | — |
| C20 | ❌ FAIL | — |

## Falhas — Itens para o backlog

### C10
- **Instrução:** Envie: entregam para São Paulo?
- **Esperado:** Confirma entrega nacional
- **Observação:** 

### C11
- **Instrução:** Selecione 'Ver catálogo' ou envie 'ver_catalogo'
- **Esperado:** Lista completa de produtos com preços
- **Observação:** 

### C17
- **Instrução:** Envie: falar com atendente
- **Esperado:** Mensagem de handoff com horário + estado AGUARDA_RETORNO
- **Observação:** 

### C18
- **Instrução:** Após C17, envie qualquer mensagem
- **Esperado:** Bot responde 'aguardando', NÃO trava em loop
- **Observação:** 

### C19
- **Instrução:** Envie 11 mensagens em sequência rápida (< 1 minuto)
- **Esperado:** 11ª mensagem bloqueada por rate limit
- **Observação:** 

### C20
- **Instrução:** Envie: qual o preço do bitcoin?
- **Esperado:** Fallback com menu, não crash
- **Observação:** 

