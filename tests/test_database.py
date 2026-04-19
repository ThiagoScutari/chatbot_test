# tests/test_database.py
import pytest
import core.database as db


def test_inicializar_banco_cria_tabela(tmp_path, monkeypatch):
    """Verifica que a tabela 'pedidos' é criada no banco."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.inicializar_banco()

    conn = db.sqlite3.connect(str(tmp_path / "test.db"))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pedidos'"
    )
    assert cursor.fetchone() is not None
    conn.close()


def test_inicializar_banco_insere_dados_ficticios(tmp_path, monkeypatch):
    """Verifica que os 5 pedidos fictícios são inseridos na inicialização."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.inicializar_banco()

    conn = db.sqlite3.connect(str(tmp_path / "test.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pedidos")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 5


def test_inicializar_banco_nao_duplica(tmp_path, monkeypatch):
    """Chamar inicializar_banco duas vezes não duplica os dados."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.inicializar_banco()
    db.inicializar_banco()

    conn = db.sqlite3.connect(str(tmp_path / "test.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pedidos")
    count = cursor.fetchone()[0]
    conn.close()

    assert count == 5


def test_buscar_pedido_existente(tmp_path, monkeypatch):
    """Buscar um número de pedido existente retorna um dicionário com os dados."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.inicializar_banco()

    pedido = db.buscar_pedido("1001")

    assert pedido is not None
    assert pedido["numero"] == "1001"
    assert pedido["cliente"] == "Ana Silva"
    assert pedido["status"] == "Entregue"


def test_buscar_pedido_inexistente(tmp_path, monkeypatch):
    """Buscar um número que não existe retorna None."""
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.inicializar_banco()

    pedido = db.buscar_pedido("9999")

    assert pedido is None
