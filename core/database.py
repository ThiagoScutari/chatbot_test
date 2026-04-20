# core/database.py
import os
import sqlite3

# Caminho padrão do banco — pode ser sobrescrito em testes com monkeypatch
_default_db = os.path.join(os.path.dirname(__file__), "..", "data", "pedidos.db")
DB_PATH = os.environ.get("CHATBOT_DB_PATH", _default_db)

# Dados fictícios inseridos na primeira inicialização
_PEDIDOS_INICIAIS = [
    ("1001", "Ana Silva",     "Cadeira Gamer",      1, "Entregue",     "2026-03-15"),
    ("1002", "João Costa",    "Mesa de Escritório",  1, "Enviado",      "2026-04-01"),
    ("1003", "Maria Souza",   'Monitor 27"',         2, "Em separação", "2026-04-10"),
    ("1004", "Carlos Lima",   "Teclado Mecânico",    1, "Entregue",     "2026-03-28"),
    ("1005", "Beatriz Alves", "Headset Gamer",       1, "Enviado",      "2026-04-05"),
]


def inicializar_banco() -> None:
    """Cria o banco e a tabela de pedidos; insere dados fictícios se vazio."""
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # CREATE TABLE IF NOT EXISTS: não falha se a tabela já existe
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            numero      TEXT UNIQUE,
            cliente     TEXT,
            produto     TEXT,
            quantidade  INTEGER,
            status      TEXT,
            data_pedido TEXT
        )
    """)

    # Só insere se o banco estiver vazio (evita duplicatas)
    cursor.execute("SELECT COUNT(*) FROM pedidos")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            """INSERT INTO pedidos
               (numero, cliente, produto, quantidade, status, data_pedido)
               VALUES (?, ?, ?, ?, ?, ?)""",
            _PEDIDOS_INICIAIS
        )

    conn.commit()
    conn.close()


def buscar_pedido(numero: str) -> dict | None:
    """Retorna os dados do pedido como dict, ou None se não encontrado."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # permite acessar colunas por nome: row["cliente"]
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pedidos WHERE numero = ?", (numero,))
    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None
