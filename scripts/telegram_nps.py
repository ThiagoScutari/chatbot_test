"""
telegram_nps.py
---------------
Bot de NPS via Telegram — long-polling.
5 perguntas em linguagem natural + comentário livre.
Persiste em PostgreSQL (nps_responses) e data/nps_results.json.

Uso (terminal separado do bot de vendas):
    python scripts/telegram_nps.py

Pré-requisito: migration aplicada → python app/migrations/migrate_sprint_nps.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from app.config import settings
from app.database import engine
from sqlalchemy import text

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level="INFO",
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

TOKEN     = settings.TELEGRAM_BOT_TOKEN
BASE_URL  = f"https://api.telegram.org/bot{TOKEN}"
DATA_FILE = "data/nps_results.json"
LONG_POLL = 30

# ── Conversation states ───────────────────────────────────────────────────────

AGUARDA_NOME        = 0
LOGISTICA           = 1
PRODUTO_QUALIDADE   = 2
PRODUTO_EXPECTATIVA = 3
ATENDIMENTO         = 4
INDICACAO           = 5
COMENTARIO          = 6

# In-memory state per chat_id
_conversas: dict[int, dict] = {}

PERGUNTAS = {
    LOGISTICA: {
        "categoria": "logistica",
        "texto": (
            "📦 *Logística*\n\n"
            "De *0 a 10*, como você avalia a entrega do seu pedido?\n"
            "Chegou no prazo e em boas condições?"
        ),
    },
    PRODUTO_QUALIDADE: {
        "categoria": "produto_qualidade",
        "texto": (
            "🧵 *Qualidade do Produto*\n\n"
            "De *0 a 10*, como você avalia a qualidade do produto que recebeu?\n"
            "O acabamento e os materiais atenderam o que você esperava?"
        ),
    },
    PRODUTO_EXPECTATIVA: {
        "categoria": "produto_expectativa",
        "texto": (
            "🎯 *Produto × Expectativa*\n\n"
            "De *0 a 10*, o produto correspondeu ao que foi apresentado?\n"
            "Variedade, cores e opções estavam de acordo com a oferta?"
        ),
    },
    ATENDIMENTO: {
        "categoria": "atendimento",
        "texto": (
            "🤝 *Atendimento*\n\n"
            "De *0 a 10*, como você avalia o atendimento que recebeu?\n"
            "A equipe foi ágil, atenciosa e resolveu suas dúvidas?"
        ),
    },
    INDICACAO: {
        "categoria": "indicacao",
        "texto": (
            "💬 *Indicação*\n\n"
            "De *0 a 10*, qual a probabilidade de você recomendar nossa empresa\n"
            "para um amigo ou familiar?"
        ),
    },
}

PROXIMO = {
    LOGISTICA:          PRODUTO_QUALIDADE,
    PRODUTO_QUALIDADE:  PRODUTO_EXPECTATIVA,
    PRODUTO_EXPECTATIVA: ATENDIMENTO,
    ATENDIMENTO:        INDICACAO,
    INDICACAO:          COMENTARIO,
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def classificar_nps(nota: int) -> str:
    if nota >= 9: return "promotor"
    if nota >= 7: return "neutro"
    return "detrator"

def teclado_notas() -> dict:
    return {
        "keyboard": [
            [{"text": str(i)} for i in range(0, 6)],
            [{"text": str(i)} for i in range(6, 11)],
        ],
        "one_time_keyboard": True,
        "resize_keyboard": True,
    }

def teclado_remover() -> dict:
    return {"remove_keyboard": True}

# ── Persistence ───────────────────────────────────────────────────────────────

def salvar_json(registro: dict) -> None:
    """Append result to data/nps_results.json (for dashboard)."""
    os.makedirs("data", exist_ok=True)
    resultados: list = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                resultados = json.load(f)
        except (json.JSONDecodeError, OSError):
            resultados = []
    resultados.append(registro)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

def salvar_postgres(registro: dict) -> None:
    """Insert NPS result into nps_responses table."""
    res = registro["respostas"]
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO nps_responses (
                telegram_user_id, nome,
                nota_logistica, nota_produto_qualidade, nota_produto_expectativa,
                nota_atendimento, nota_indicacao,
                comentario, media_geral, nps_classificacao, raw_data
            ) VALUES (
                :uid, :nome,
                :log, :pq, :pe, :at, :ind,
                :comentario, :media, :class, CAST(:raw AS jsonb)
            )
        """), {
            "uid":        registro["user_id"],
            "nome":       registro["nome"],
            "log":        res["logistica"]["nota"],
            "pq":         res["produto_qualidade"]["nota"],
            "pe":         res["produto_expectativa"]["nota"],
            "at":         res["atendimento"]["nota"],
            "ind":        res["indicacao"]["nota"],
            "comentario": registro["comentario"] or None,
            "media":      registro["media_geral"],
            "class":      registro["nps_classificacao"],
            "raw":        json.dumps(registro, ensure_ascii=False),
        })
        conn.commit()
    logger.info(
        "NPS salvo — user_id=%s nome=%s nps=%s media=%.1f",
        registro["user_id"], registro["nome"],
        registro["nps_classificacao"], registro["media_geral"],
    )

def salvar_resultado(registro: dict) -> None:
    """Dual-write: PostgreSQL (primary) + JSON (secondary)."""
    try:
        salvar_postgres(registro)
    except Exception:
        logger.exception("Falha ao salvar no PostgreSQL — salvando apenas JSON")
    salvar_json(registro)

# ── Telegram API ──────────────────────────────────────────────────────────────

async def get_updates(offset: int) -> list[dict]:
    url = f"{BASE_URL}/getUpdates"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            params={"offset": offset, "timeout": LONG_POLL},
            timeout=LONG_POLL + 10,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])

async def send_message(chat_id: int, text_: str, reply_markup: dict | None = None) -> None:
    payload: dict = {
        "chat_id":    chat_id,
        "text":       text_,
        "parse_mode": "Markdown",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10.0)
        resp.raise_for_status()

# ── Message handling ──────────────────────────────────────────────────────────

async def processar_update(update: dict) -> None:
    message = update.get("message")
    if not message:
        return

    chat_id = message["chat"]["id"]
    text    = (message.get("text") or "").strip()
    if not text:
        return

    # /cancelar — universal escape
    if text.lower() in ("/cancelar", "/cancel"):
        _conversas.pop(chat_id, None)
        await send_message(
            chat_id,
            "Pesquisa cancelada. Obrigado pelo seu tempo! 😊\n"
            "Se quiser responder depois, envie /start.",
            reply_markup=teclado_remover(),
        )
        return

    # /start or /nps — begin flow
    if text in ("/start", "/nps"):
        nome_tg = message.get("from", {}).get("first_name", "")
        _conversas[chat_id] = {
            "state":     AGUARDA_NOME,
            "user_id":   chat_id,
            "nome":      nome_tg,
            "respostas": {},
            "inicio":    datetime.now().isoformat(),
        }
        saudacao = f", {nome_tg}" if nome_tg else ""
        await send_message(
            chat_id,
            f"Olá{saudacao}! 👋\n\n"
            "Sou o assistente da *Camisart Belém* e gostaria de saber\n"
            "o que você achou da sua experiência conosco.\n\n"
            "São apenas *5 perguntas rápidas* — menos de 2 minutos! 🚀\n\n"
            "Para começar, qual é o seu nome?",
            reply_markup=teclado_remover(),
        )
        return

    # No active conversation
    if chat_id not in _conversas:
        await send_message(
            chat_id,
            "Olá! Para participar da nossa pesquisa de satisfação, envie /start 😊",
        )
        return

    conv  = _conversas[chat_id]
    state = conv["state"]

    # ── AGUARDA_NOME ──────────────────────────────────────────────────────────
    if state == AGUARDA_NOME:
        if len(text) < 2:
            await send_message(chat_id, "Por favor, me diga seu nome para começar. 😊")
            return
        conv["nome"]  = text
        conv["state"] = LOGISTICA
        await send_message(
            chat_id,
            f"Prazer, *{text}*! Vamos começar.\n\n" + PERGUNTAS[LOGISTICA]["texto"],
            reply_markup=teclado_notas(),
        )
        return

    # ── NOTE STATES ───────────────────────────────────────────────────────────
    if state in (LOGISTICA, PRODUTO_QUALIDADE, PRODUTO_EXPECTATIVA, ATENDIMENTO, INDICACAO):
        if not text.isdigit() or not (0 <= int(text) <= 10):
            await send_message(
                chat_id,
                "Por favor, escolha uma nota de *0 a 10* usando o teclado abaixo. 😊",
                reply_markup=teclado_notas(),
            )
            return

        nota      = int(text)
        categoria = PERGUNTAS[state]["categoria"]
        conv["respostas"][categoria] = {
            "nota":          nota,
            "classificacao": classificar_nps(nota),
        }
        proximo       = PROXIMO[state]
        conv["state"] = proximo

        if proximo == COMENTARIO:
            await send_message(
                chat_id,
                "Última pergunta, prometo! 🏁\n\n"
                "Tem algum comentário, elogio ou sugestão que queira compartilhar?\n"
                "_(Digite_ *pular* _se preferir não comentar)_",
                reply_markup=teclado_remover(),
            )
        else:
            await send_message(
                chat_id,
                PERGUNTAS[proximo]["texto"],
                reply_markup=teclado_notas(),
            )
        return

    # ── COMENTARIO — finalize ─────────────────────────────────────────────────
    if state == COMENTARIO:
        comentario = "" if text.lower() in ("pular", "skip", "-", "não", "nao") else text

        respostas      = conv["respostas"]
        notas          = [v["nota"] for v in respostas.values()]
        media_geral    = round(sum(notas) / len(notas), 1) if notas else 0
        nota_indicacao = respostas.get("indicacao", {}).get("nota", 0)
        classificacao  = classificar_nps(nota_indicacao)

        registro = {
            "user_id":           conv["user_id"],
            "nome":              conv["nome"],
            "inicio":            conv["inicio"],
            "fim":               datetime.now().isoformat(),
            "respostas":         respostas,
            "comentario":        comentario,
            "media_geral":       media_geral,
            "nps_classificacao": classificacao,
        }

        salvar_resultado(registro)
        _conversas.pop(chat_id, None)

        emoji = {"promotor": "🤩", "neutro": "😊", "detrator": "😟"}.get(classificacao, "😊")
        await send_message(
            chat_id,
            f"{emoji} *Muito obrigado, {conv['nome']}!*\n\n"
            f"Suas respostas foram registradas com sucesso.\n"
            f"Nota média: *{media_geral}/10*\n\n"
            "Seu feedback é essencial para continuarmos melhorando. 💙\n"
            "_Camisart Belém — sua loja de uniformes!_",
            reply_markup=teclado_remover(),
        )

# ── Main loop (mirrors telegram_polling.py) ───────────────────────────────────

async def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN não configurado. Adicione no .env")
        return

    os.makedirs("data", exist_ok=True)
    logger.info("Bot NPS iniciado. Envie /start para começar. (Ctrl+C para parar)")
    logger.info("JSON  → %s", DATA_FILE)
    logger.info("DB   → tabela nps_responses")

    offset = 0
    while True:
        try:
            updates = await get_updates(offset)
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    await processar_update(update)
                except Exception:
                    logger.exception("Erro ao processar update %s:", update.get("update_id"))
        except httpx.ReadTimeout:
            logger.debug("Long-poll timeout (sem mensagens) — reconectando…")
        except Exception:
            logger.exception("Polling error — aguardando 3s…")
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
