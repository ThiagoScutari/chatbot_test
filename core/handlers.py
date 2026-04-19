# core/handlers.py
from core.states import INICIO, AGUARDA_NOME, MENU, AGUARDA_PEDIDO, FIM
from core.database import buscar_pedido


def handle(mensagem: str, sessao: dict) -> tuple[str, str, str | None]:
    """
    Processa a mensagem do usuário com base no estado atual da sessão.

    Parâmetros:
        mensagem    — texto enviado pelo usuário (pode ser vazio no estado INICIO)
        sessao      — dicionário com "estado" (str) e "nome" (str | None)

    Retorno:
        (resposta, proximo_estado, acao)
        acao: None | "enviar_catalogo"
    """
    estado = sessao["estado"]
    mensagem = mensagem.strip()

    # ------------------------------------------------------------------ INICIO
    # Estado inicial: enviado automaticamente ao começar a conversa.
    # Não depende de nenhuma entrada do usuário.
    if estado == INICIO:
        sessao["estado"] = AGUARDA_NOME
        return (
            "Olá! Bem-vindo ao nosso atendimento. 😊\nQual é o seu nome?",
            AGUARDA_NOME,
            None,
        )

    # ------------------------------------------------------------ AGUARDA_NOME
    # Aguarda o usuário digitar o nome. Valida que não está vazio.
    if estado == AGUARDA_NOME:
        if not mensagem:
            return ("Por favor, digite o seu nome.", AGUARDA_NOME, None)

        sessao["nome"] = mensagem
        sessao["estado"] = MENU
        return (
            f"Prazer, {mensagem}! Como posso te ajudar?\n\n"
            "1 - Consultar pedido\n"
            "2 - Receber catálogo de produtos",
            MENU,
            None,
        )

    # -------------------------------------------------------------------- MENU
    # Aguarda a escolha: "1" ou "2". Qualquer outro valor é erro.
    if estado == MENU:
        if mensagem == "1":
            sessao["estado"] = AGUARDA_PEDIDO
            return (
                "Por favor, informe o número do pedido (ex: 1001):",
                AGUARDA_PEDIDO,
                None,
            )

        if mensagem == "2":
            nome = sessao.get("nome", "")
            sessao["estado"] = FIM
            return (
                f"Aqui está o nosso catálogo de produtos, {nome}!\n\n"
                f"Foi um prazer te ajudar! Até a próxima. 👋",
                FIM,
                "enviar_catalogo",  # sinaliza à interface para abrir/enviar o PDF
            )

        return (
            "Opção inválida. Digite 1 para consultar pedido ou 2 para o catálogo.",
            MENU,
            None,
        )

    # --------------------------------------------------------- AGUARDA_PEDIDO
    # Aguarda o número do pedido. Valida formato e existência no banco.
    if estado == AGUARDA_PEDIDO:
        if not mensagem.isdigit():
            # isdigit() retorna True apenas se todos os caracteres são dígitos
            return (
                "Número de pedido inválido. Digite apenas os números (ex: 1001).",
                AGUARDA_PEDIDO,
                None,
            )

        pedido = buscar_pedido(mensagem)

        if pedido is None:
            return (
                f"Pedido {mensagem} não encontrado. Verifique o número e tente novamente.",
                AGUARDA_PEDIDO,
                None,
            )

        nome = sessao.get("nome", "")
        sessao["estado"] = FIM
        resposta = (
            f"📦 Pedido #{pedido['numero']}\n"
            f"Cliente:    {pedido['cliente']}\n"
            f"Produto:    {pedido['produto']}\n"
            f"Quantidade: {pedido['quantidade']}\n"
            f"Status:     {pedido['status']}\n"
            f"Data:       {pedido['data_pedido']}\n\n"
            f"Foi um prazer te ajudar, {nome}! Até a próxima. 👋"
        )
        return (resposta, FIM, None)

    # -------------------------------------------------------------------- FIM
    # Estado terminal. Conversa encerrada.
    return ("Conversa encerrada. Reinicie para começar novamente.", FIM, None)
