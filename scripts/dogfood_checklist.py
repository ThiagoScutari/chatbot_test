"""
Roteiro de validação manual sistemática via Telegram.
Gera relatório em docs/dogfood/YYYY-MM-DD_relatorio.md

Uso:
    python scripts/dogfood_checklist.py
"""
from datetime import date
from pathlib import Path


CENARIOS = [
    ("C01", "BLOCO 1 — Onboarding",
     "Envie /start para o bot",
     "Bot responde com boas-vindas sem pedir menu, pede nome"),
    ("C02", "BLOCO 1 — Onboarding",
     "Envie seu nome (ex: Thiago)",
     "Bot salva o nome e mostra menu com 3 opções"),
    ("C03", "BLOCO 1 — Onboarding",
     "Aguarde 2h (ou altere last_interaction_at no banco para 3h atrás) "
     "e envie uma mensagem",
     "Bot cumprimenta de volta usando o nome salvo"),
    ("C04", "BLOCO 1 — Onboarding",
     "Envie /start novamente com sessão ativa",
     "Bot responde com boas-vindas, NÃO com fallback"),
    ("C05", "BLOCO 2 — FAQ",
     "Envie: qual o preço da polo?",
     "Resposta com preço da polo piquet, varejo e atacado"),
    ("C06", "BLOCO 2 — FAQ",
     "Envie: camiza polo (com erro ortográfico)",
     "Mesmo resultado que C05 — regex tolerante"),
    ("C07", "BLOCO 2 — FAQ",
     "Envie: onde fica a loja?",
     "Endereço completo da Camisart"),
    ("C08", "BLOCO 2 — FAQ",
     "Envie: tem pedido mínimo?",
     "Resposta correta: varejo sem mínimo, serigrafia 40 peças"),
    ("C09", "BLOCO 2 — FAQ",
     "Envie: quanto demora o bordado?",
     "Prazo 5 dias úteis + sem pedido mínimo"),
    ("C10", "BLOCO 2 — FAQ",
     "Envie: entregam para São Paulo?",
     "Confirma entrega nacional"),
    ("C11", "BLOCO 3 — Orçamento",
     "Selecione 'Ver catálogo' ou envie 'ver_catalogo'",
     "Lista completa de produtos com preços"),
    ("C12", "BLOCO 3 — Orçamento",
     "Complete o fluxo: segmento → produto → quantidade (50) "
     "→ personalização (bordado) → prazo (15 dias) → confirmar",
     "Resumo correto + lead gravado no banco"),
    ("C13", "BLOCO 3 — Orçamento",
     "No passo de quantidade, envie 'muitas'",
     "Bot pede novamente sem avançar estado"),
    ("C14", "BLOCO 3 — Orçamento",
     "Na confirmação do orçamento, envie 'corrigir'",
     "Bot volta para o passo de quantidade"),
    ("C15", "BLOCO 3 — Orçamento",
     "Complete e confirme um orçamento. Depois rode:\n"
     "  python scripts/inspect_session.py --leads",
     "Lead aparece com status='novo' e dados corretos"),
    ("C16", "BLOCO 3 — Orçamento",
     "Inicie orçamento e selecione segmento 'saúde'",
     "Lista de produtos mostra apenas jaleco tradicional e premium"),
    ("C17", "BLOCO 4 — Handoff",
     "Envie: falar com atendente",
     "Mensagem de handoff com horário + estado AGUARDA_RETORNO"),
    ("C18", "BLOCO 4 — Handoff",
     "Após C17, envie qualquer mensagem",
     "Bot responde 'aguardando', NÃO trava em loop"),
    ("C19", "BLOCO 5 — Edge cases",
     "Envie 11 mensagens em sequência rápida (< 1 minuto)",
     "11ª mensagem bloqueada por rate limit"),
    ("C20", "BLOCO 5 — Edge cases",
     "Envie: qual o preço do bitcoin?",
     "Fallback com menu, não crash"),
]


def run():
    print("\n" + "=" * 60)
    print("CAMISART AI — ROTEIRO DE DOGFOODING SISTEMÁTICO")
    print("=" * 60)
    testador = input("\nSeu nome (para o relatório): ").strip() or "Anônimo"
    bot = input("Username do bot Telegram (ex: @camisart_dev_bot): ").strip()
    print(
        "\nInstrução: para cada cenário, execute no Telegram e confirme o resultado."
    )
    print("Comandos: PASS | FAIL | SKIP (pular) | OBS: texto livre\n")

    results = []
    bloco_atual = ""

    for cod, bloco, instrucao, esperado in CENARIOS:
        if bloco != bloco_atual:
            bloco_atual = bloco
            print(f"\n{'─' * 40}")
            print(f"  {bloco}")
            print(f"{'─' * 40}")

        print(f"\n[{cod}] {instrucao}")
        print(f"  Esperado: {esperado}")
        resposta = input("  Resultado [PASS/FAIL/SKIP/OBS:...]: ").strip()

        status = "✅ PASS"
        obs = ""
        if resposta.upper().startswith("FAIL"):
            status = "❌ FAIL"
            obs = resposta[4:].strip(": ")
        elif resposta.upper().startswith("SKIP"):
            status = "⏭️ SKIP"
        elif resposta.upper().startswith("OBS:"):
            status = "⚠️ OBS"
            obs = resposta[4:].strip()
        elif resposta.upper() != "PASS":
            status = "⚠️ OBS"
            obs = resposta

        results.append((cod, bloco, instrucao, esperado, status, obs))

    total = len(results)
    passed = sum(1 for r in results if "PASS" in r[4])
    failed = sum(1 for r in results if "FAIL" in r[4])
    skipped = sum(1 for r in results if "SKIP" in r[4])

    veredicto = (
        "✅ APROVADO" if failed == 0
        else "⚠️ APROVADO COM RESSALVAS" if failed <= 2
        else "❌ REPROVADO"
    )

    relatorio = f"""# Relatório de Dogfooding — {date.today()}

**Testador:** {testador}
**Canal:** Telegram ({bot})
**Cenários:** {total} executados

## Resultado Geral

| | |
|---|---|
| ✅ PASS | {passed} |
| ❌ FAIL | {failed} |
| ⏭️ SKIP | {skipped} |
| **Veredicto** | **{veredicto}** |

## Detalhamento

| Cenário | Status | Observação |
|---------|--------|-----------|
"""
    for cod, _, instrucao, _, status, obs in results:
        relatorio += f"| {cod} | {status} | {obs or '—'} |\n"

    if failed > 0:
        relatorio += "\n## Falhas — Itens para o backlog\n\n"
        for cod, _, instrucao, esperado, status, obs in results:
            if "FAIL" in status:
                relatorio += f"### {cod}\n"
                relatorio += f"- **Instrução:** {instrucao}\n"
                relatorio += f"- **Esperado:** {esperado}\n"
                relatorio += f"- **Observação:** {obs}\n\n"

    out_dir = Path("docs/dogfood")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date.today()}_relatorio.md"
    out_file.write_text(relatorio, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"Relatório salvo em: {out_file}")
    print(f"Veredicto: {veredicto}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    run()
