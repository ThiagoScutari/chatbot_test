"""Persona agent — uses Claude Haiku to simulate a real customer.

Receives the persona document + flow document + conversation history.
Returns the next client message OR "__END__" when finished.
"""
from __future__ import annotations

import anthropic


AGENT_SYSTEM_PROMPT = """Você é um simulador de cliente para testes de chatbot.
Seu papel é agir EXATAMENTE como a persona descrita abaixo, seguindo o fluxo indicado.

REGRAS ABSOLUTAS:
1. Responda APENAS com a mensagem do cliente — sem aspas, sem prefixos como "Cliente:" ou "Mensagem:", sem explicações, sem markdown
2. Mantenha o personagem durante toda a conversa — sotaque, abreviações, tom, erros de digitação
3. Reaja de forma REALISTA às respostas do chatbot — se ele errar, demonstre confusão
4. Se o chatbot pedir informação (nome, cidade, segmento, produto, quantidade), forneça de acordo com a persona e o fluxo
5. Quando o objetivo do fluxo for alcançado OU quando não houver mais o que dizer naturalmente, responda EXATAMENTE com a palavra: __END__
6. NÃO invente produtos que a loja não vende — se precisar de um produto, use: polo, básica, jaleco, regata, boné
7. Se o chatbot fizer algo inesperado (loop, resposta estranha, ignorar sua pergunta), reaja como o cliente reagiria
8. NÃO quebre o personagem em hipótese alguma — sua resposta É a mensagem do cliente
9. Mensagens curtas — clientes de WhatsApp não escrevem parágrafos
10. A PRIMEIRA mensagem que você enviar será após o bot ter respondido ao /start. Você NÃO envia /start.

{persona_doc}

{flow_doc}

TURNO ATUAL: {turn_number} de {max_turns}
Se estiver no turno final ou próximo, encerre naturalmente."""


class PersonaAgent:
    def __init__(self, api_key: str) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    async def generate_message(
        self,
        persona_doc: str,
        flow_doc: str,
        conversation_history: list[dict],
        turn_number: int,
        max_turns: int,
    ) -> str:
        """Generate the next simulated client message.

        ``conversation_history`` format (from Haiku's perspective —
        Haiku IS the assistant in this API call, role-playing the persona):
            [
                {"role": "user", "content": "resposta do bot ao /start"},
                {"role": "assistant", "content": "mensagem anterior do cliente (gerada por Haiku)"},
                {"role": "user", "content": "resposta do bot"},
                ...
            ]

        Returns the client message OR ``"__END__"``.
        """
        system = AGENT_SYSTEM_PROMPT.format(
            persona_doc=persona_doc,
            flow_doc=flow_doc,
            turn_number=turn_number,
            max_turns=max_turns,
        )

        response = await self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system=system,
            messages=conversation_history,
        )

        text = response.content[0].text.strip()

        # Clean possible prefixes Haiku might add
        for prefix in ("Cliente:", "Mensagem:", "User:", ">"):
            if text.startswith(prefix):
                text = text[len(prefix):].strip()

        # Remove wrapping quotes
        if len(text) > 2 and text[0] == '"' and text[-1] == '"':
            text = text[1:-1]

        return text
