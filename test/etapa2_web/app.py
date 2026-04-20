# etapa2_web/app.py
import os
import sys

_test_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # test/
_project_root = os.path.dirname(_test_root)                                 # chatbot/

sys.path.insert(0, _project_root)
os.environ.setdefault("CHATBOT_DB_PATH", os.path.join(_test_root, "data", "pedidos.db"))

from flask import Flask, jsonify, render_template, request, send_file, session
from core.database import inicializar_banco
from core.handlers import handle
from core.states import FIM, INICIO

app = Flask(__name__)
app.secret_key = "chatbot-dev-secret-2026"

CATALOGO_PATH = os.path.join(_test_root, "docs", "Catalogo.pdf")

inicializar_banco()


@app.route("/")
def index():
    """Carrega a página de chat e envia a mensagem inicial do bot."""
    session.clear()
    sessao_chatbot = {"nome": None, "estado": INICIO}
    resposta, novo_estado, _ = handle("", sessao_chatbot)
    sessao_chatbot["estado"] = novo_estado
    session["chatbot"] = sessao_chatbot
    return render_template("index.html", mensagem_inicial=resposta)


@app.route("/mensagem", methods=["POST"])
def mensagem():
    """Recebe a mensagem do usuário e retorna a resposta do bot em JSON."""
    dados = request.get_json()
    texto = (dados.get("texto") or "").strip()

    if not texto:
        return jsonify({"resposta": "Por favor, digite algo.", "fim": False, "acao": None})

    sessao_chatbot = session.get("chatbot", {"nome": None, "estado": INICIO})
    resposta, novo_estado, acao = handle(texto, sessao_chatbot)
    sessao_chatbot["estado"] = novo_estado
    session["chatbot"] = sessao_chatbot

    return jsonify({
        "resposta": resposta,
        "fim": novo_estado == FIM,
        "acao": acao,
    })


@app.route("/catalogo")
def catalogo():
    """Serve o PDF do catálogo para download."""
    return send_file(CATALOGO_PATH, as_attachment=True, download_name="Catalogo.pdf")


if __name__ == "__main__":
    app.run(debug=True)
