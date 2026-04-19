# etapa3_telegram/bot.py
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from core.database import inicializar_banco
from core.handlers import handle
from core.states import FIM, INICIO

CATALOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs", "Catalogo.pdf"
)

inicializar_banco()


def _sessao_nova() -> dict:
    return {"nome": None, "estado": INICIO}


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start — reinicia a conversa para o usuário."""
    context.user_data["chatbot"] = _sessao_nova()
    resposta, novo_estado, _ = handle("", context.user_data["chatbot"])
    context.user_data["chatbot"]["estado"] = novo_estado
    await update.message.reply_text(resposta)


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa qualquer mensagem de texto recebida."""
    # Se não há sessão ativa, inicia automaticamente (como se o usuário tivesse mandado /start)
    if "chatbot" not in context.user_data:
        context.user_data["chatbot"] = _sessao_nova()
        resposta, novo_estado, _ = handle("", context.user_data["chatbot"])
        context.user_data["chatbot"]["estado"] = novo_estado
        await update.message.reply_text(resposta)
        return

    sessao = context.user_data["chatbot"]

    if sessao["estado"] == FIM:
        await update.message.reply_text(
            "A conversa foi encerrada. Envie /start para começar novamente."
        )
        return

    texto = update.message.text
    resposta, novo_estado, acao = handle(texto, sessao)
    sessao["estado"] = novo_estado

    await update.message.reply_text(resposta)

    if acao == "enviar_catalogo":
        # Envia o PDF como arquivo anexo na conversa
        with open(CATALOGO_PATH, "rb") as f:
            await update.message.reply_document(document=f, filename="Catalogo.pdf")


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("Erro: defina a variável de ambiente TELEGRAM_BOT_TOKEN")
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))

    print("Bot iniciado. Pressione Ctrl+C para parar.")
    app.run_polling()


if __name__ == "__main__":
    main()
