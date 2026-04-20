# etapa1_terminal/main.py
import os
import sys

# Garante que stdout/stderr usam UTF-8 para suportar emoji e caracteres especiais
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

_test_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # test/
_project_root = os.path.dirname(_test_root)                                 # chatbot/

sys.path.insert(0, _project_root)
os.environ.setdefault("CHATBOT_DB_PATH", os.path.join(_test_root, "data", "pedidos.db"))

from core.states import INICIO, FIM
from core.handlers import handle
from core.database import inicializar_banco

CATALOGO_PATH = os.path.join(_test_root, "docs", "Catalogo.pdf")


def main():
    # Garante que o banco existe e tem os dados antes de iniciar
    inicializar_banco()

    sessao = {"nome": None, "estado": INICIO}

    # Dispara a mensagem inicial sem input do usuário
    resposta, novo_estado, acao = handle("", sessao)
    sessao["estado"] = novo_estado
    print(f"\nBot: {resposta}\n")

    while sessao["estado"] != FIM:
        try:
            entrada = input("Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C ou fim de stream: encerra graciosamente
            print("\nBot: Encerrando o atendimento. Até logo!")
            break

        if not entrada:
            print("Bot: Por favor, digite algo.\n")
            continue

        resposta, novo_estado, acao = handle(entrada, sessao)
        sessao["estado"] = novo_estado
        print(f"\nBot: {resposta}\n")

        if acao == "enviar_catalogo":
            try:
                os.startfile(CATALOGO_PATH)  # abre o PDF no visualizador padrão (Windows)
                print("Bot: O catálogo foi aberto no seu visualizador de PDF.\n")
            except FileNotFoundError:
                print(f"Bot: Arquivo não encontrado: {CATALOGO_PATH}\n")
            except OSError as e:
                print(f"Bot: Não foi possível abrir o catálogo: {e}\n")


if __name__ == "__main__":
    main()
