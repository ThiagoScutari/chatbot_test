import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def build_catalog_message(
    products_path: Path = Path("app/knowledge/products.json"),
) -> str:
    """Lê products.json e formata como texto WhatsApp/Telegram-ready.

    Retorna string pronta para envio.
    """
    try:
        data = json.loads(products_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Erro ao ler products.json: %s", exc)
        return (
            "📋 Nosso catálogo completo está disponível na loja!\n"
            "Av. Magalhães Barata, 445 — Belém/PA"
        )

    lines = ["👕 *Catálogo Camisart Belém*\n"]

    for p in data.get("products", []):
        preco_str = _format_preco(p.get("precos", {}))
        line = f"• *{p['nome']}* — {p['tecido']}"
        if preco_str:
            line += f" | {preco_str}"
        obs = p.get("observacao")
        if obs:
            line += f"\n  _{obs}_"
        lines.append(line)

    servicos = data.get("servicos", [])
    if servicos:
        lines.append("\n✂️ *Serviços:*")
        for s in servicos:
            s_line = f"• {s['nome']}"
            if s.get("prazo_dias_uteis"):
                s_line += f" — prazo {s['prazo_dias_uteis']} dias úteis"
            if s.get("pedido_minimo") and s["pedido_minimo"] > 1:
                s_line += f" (mín. {s['pedido_minimo']} peças)"
            lines.append(s_line)

    lines.append("\n💬 Qual produto te interessa? Posso fazer um orçamento completo! 📋")
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
    if "atacado_12" in precos:
        return f"a partir de R$ {precos.get('varejo', precos['atacado_12']):.2f}"
    return "consultar"
