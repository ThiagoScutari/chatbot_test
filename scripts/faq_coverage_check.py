import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.engines.campaign_engine import CampaignEngine
from app.engines.regex_engine import FAQEngine


PERGUNTAS_REAIS = [
    "quanto custa a polo?",
    "tem polo plus size?",
    "faz entrega para o interior?",
    "aceita cartão?",
    "tem camisa manga longa?",
    "qual o tamanho maior que tem?",
    "faz personalização com foto?",
    "tem camisa feminina?",
    "qual o prazo para 100 peças?",
    "faz uniforme para restaurante?",
    "tem jaleco feminino?",
    "faz camiseta para time de futebol?",
    "qual o Whatsapp de vocês?",
    "tem loja física?",
    "aceita pix?",
    "tem desconto para quantidade?",
    "faz camisa polo infantil?",
    "tem tecido dry fit?",
    "qual o instagram de vocês?",
    "tem estoque pronto?",
]


def main():
    engine = CampaignEngine(settings.CAMPAIGNS_JSON_PATH)
    engine.reload()
    faq = FAQEngine(settings.FAQ_JSON_PATH, campaign_engine=engine)

    matched = 0
    gaps = []
    print("\n" + "=" * 60)
    print("FAQ COVERAGE CHECK - Perguntas reais do Instagram")
    print("=" * 60)

    for pergunta in PERGUNTAS_REAIS:
        result = faq.match(pergunta)
        if result:
            matched += 1
            print(f"  [OK] {pergunta!r}\n       -> {result.intent_id}")
        else:
            gaps.append(pergunta)
            print(f"  [--] {pergunta!r}\n       -> FALLBACK")

    coverage = matched * 100 // len(PERGUNTAS_REAIS)
    print("\n" + "=" * 60)
    print(f"Cobertura: {matched}/{len(PERGUNTAS_REAIS)} = {coverage}%")
    status = "OK" if coverage >= 80 else "ABAIXO DA META"
    print(f"Meta: >= 80%  |  Status: {status}")

    if gaps:
        print(f"\nGaps ({len(gaps)}) - adicionar ao faq.json:")
        for g in gaps:
            print(f"  - {g!r}")

    print("=" * 60 + "\n")
    return coverage


if __name__ == "__main__":
    main()
