# tests/test_handlers.py
from unittest.mock import patch
from core.states import INICIO, AGUARDA_NOME, MENU, AGUARDA_PEDIDO, FIM
from core.handlers import handle


def nova_sessao():
    """Cria uma sessão nova no estado inicial."""
    return {"nome": None, "estado": INICIO}


# --- Estado INICIO ---

def test_inicio_retorna_boas_vindas():
    sessao = nova_sessao()
    resposta, estado, acao = handle("", sessao)

    assert "Bem-vindo" in resposta or "bem-vindo" in resposta.lower()
    assert estado == AGUARDA_NOME
    assert acao is None


# --- Estado AGUARDA_NOME ---

def test_aguarda_nome_salva_nome_e_exibe_menu():
    sessao = {"nome": None, "estado": AGUARDA_NOME}
    resposta, estado, _ = handle("Ana", sessao)

    assert sessao["nome"] == "Ana"
    assert estado == MENU
    assert "Ana" in resposta
    assert "1" in resposta and "2" in resposta  # menu exibido


def test_aguarda_nome_vazio_permanece_no_estado():
    sessao = {"nome": None, "estado": AGUARDA_NOME}
    _, estado, _ = handle("", sessao)

    assert estado == AGUARDA_NOME
    assert sessao["nome"] is None


def test_aguarda_nome_so_espacos_permanece_no_estado():
    sessao = {"nome": None, "estado": AGUARDA_NOME}
    _, estado, _ = handle("   ", sessao)

    assert estado == AGUARDA_NOME


# --- Estado MENU ---

def test_menu_opcao_1_vai_para_aguarda_pedido():
    sessao = {"nome": "Ana", "estado": MENU}
    _, estado, acao = handle("1", sessao)

    assert estado == AGUARDA_PEDIDO
    assert acao is None


def test_menu_opcao_2_vai_para_fim_e_aciona_catalogo():
    sessao = {"nome": "Ana", "estado": MENU}
    _, estado, acao = handle("2", sessao)

    assert estado == FIM
    assert acao == "enviar_catalogo"


def test_menu_opcao_invalida_permanece_no_menu():
    sessao = {"nome": "Ana", "estado": MENU}
    _, estado, acao = handle("9", sessao)

    assert estado == MENU
    assert acao is None


def test_menu_opcao_invalida_exibe_mensagem_de_erro():
    sessao = {"nome": "Ana", "estado": MENU}
    resposta, _, _ = handle("abc", sessao)

    assert "inválid" in resposta.lower()


# --- Estado AGUARDA_PEDIDO ---

def test_aguarda_pedido_texto_nao_numerico_permanece():
    sessao = {"nome": "Ana", "estado": AGUARDA_PEDIDO}
    _, estado, _ = handle("abc", sessao)

    assert estado == AGUARDA_PEDIDO


def test_aguarda_pedido_invalido_exibe_mensagem_de_erro():
    sessao = {"nome": "Ana", "estado": AGUARDA_PEDIDO}
    resposta, _, _ = handle("abc", sessao)

    assert "inválido" in resposta.lower() or "inválid" in resposta.lower()


def test_aguarda_pedido_valido_retorna_detalhes_e_vai_para_fim():
    sessao = {"nome": "Ana", "estado": AGUARDA_PEDIDO}
    pedido_mock = {
        "numero": "1001", "cliente": "Ana Silva", "produto": "Cadeira Gamer",
        "quantidade": 1, "status": "Entregue", "data_pedido": "2026-03-15"
    }
    with patch("core.handlers.buscar_pedido", return_value=pedido_mock):
        resposta, estado, acao = handle("1001", sessao)

    assert estado == FIM
    assert "1001" in resposta
    assert "Entregue" in resposta
    assert acao is None


def test_aguarda_pedido_inexistente_permanece():
    sessao = {"nome": "Ana", "estado": AGUARDA_PEDIDO}
    with patch("core.handlers.buscar_pedido", return_value=None):
        resposta, estado, _ = handle("9999", sessao)

    assert estado == AGUARDA_PEDIDO
    assert "não encontrado" in resposta.lower()


# --- Despedida usa o nome ---

def test_catalogo_inclui_nome_na_despedida():
    sessao = {"nome": "Carlos", "estado": MENU}
    resposta, _, _ = handle("2", sessao)

    assert "Carlos" in resposta


def test_pedido_encontrado_inclui_nome_na_despedida():
    sessao = {"nome": "Maria", "estado": AGUARDA_PEDIDO}
    pedido_mock = {
        "numero": "1003", "cliente": "Maria Souza", "produto": "Monitor 27\"",
        "quantidade": 2, "status": "Em separação", "data_pedido": "2026-04-10"
    }
    with patch("core.handlers.buscar_pedido", return_value=pedido_mock):
        resposta, _, _ = handle("1003", sessao)

    assert "Maria" in resposta
