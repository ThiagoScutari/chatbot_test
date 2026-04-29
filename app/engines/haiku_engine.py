"""HaikuEngine — Motor LLM-first para o chatbot Camisart.

Toda mensagem do cliente passa por aqui. O Haiku recebe:
- System prompt com catálogo, FAQ, knowledge base, regras
- Estado atual do funil (dados já coletados)
- Histórico da conversa (últimas 20 mensagens)
- Mensagem atual do cliente

Retorna JSON estruturado com resposta + dados extraídos + ação.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)


@dataclass
class HaikuResponse:
    """Resposta parseada do Haiku."""

    resposta: str
    dados_extraidos: dict
    acao: str  # "continuar" | "lead_completo" | "transferir_humano"
    intent: str
    raw_json: dict
    tokens_input: int = 0
    tokens_output: int = 0


class HaikuEngine:
    """Motor LLM-first. Toda mensagem passa por aqui."""

    def __init__(
        self,
        prompt_path: Path,
        client: anthropic.AsyncAnthropic,
    ) -> None:
        self._client = client
        self._system_prompt = prompt_path.read_text(encoding="utf-8")
        logger.info(
            "HaikuEngine inicializado — prompt: %d chars",
            len(self._system_prompt),
        )

    async def process(
        self,
        message: str,
        conversation_history: list[dict],
        session_data: dict,
    ) -> HaikuResponse:
        """Processa uma mensagem do cliente via Haiku.

        Args:
            message: texto da mensagem do cliente
            conversation_history: últimas N mensagens [{"role": ..., "content": ...}]
            session_data: dados já coletados no funil

        Returns:
            HaikuResponse com resposta, dados extraídos e ação.
        """
        # 1. Montar system prompt com estado do funil
        system = self._system_prompt
        if session_data:
            funil_status = self._format_funil_status(session_data)
            if funil_status:
                system += f"\n\n## ESTADO ATUAL DO FUNIL\n{funil_status}"

        # 2. Montar mensagens
        messages = list(conversation_history)
        messages.append({"role": "user", "content": message})

        # 3. Chamar Haiku
        response = await self._client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=system,
            messages=messages,
        )

        # 4. Parsear resposta
        raw_text = response.content[0].text.strip()
        parsed = self._parse_response(raw_text)

        return HaikuResponse(
            resposta=parsed.get("resposta", raw_text),
            dados_extraidos=parsed.get("dados_extraidos") or {},
            acao=parsed.get("acao", "continuar"),
            intent=parsed.get("intent", "desconhecido"),
            raw_json=parsed,
            tokens_input=response.usage.input_tokens,
            tokens_output=response.usage.output_tokens,
        )

    def _format_funil_status(self, session_data: dict) -> str:
        """Formata dados já coletados para incluir no prompt."""
        campos = [
            "nome",
            "segmento",
            "produto",
            "quantidade",
            "personalizacao",
            "prazo",
            "observacoes",
        ]

        coletados = []
        pendentes = []
        for campo in campos:
            valor = session_data.get(campo)
            if valor:
                coletados.append(f"- {campo}: {valor}")
            else:
                pendentes.append(f"- {campo}")

        if not coletados:
            return ""

        parts = ["Dados JÁ coletados (NÃO pergunte novamente):"]
        parts.append("\n".join(coletados))
        if pendentes:
            parts.append("\nDados PENDENTES (coletar quando natural):")
            parts.append("\n".join(pendentes))

        return "\n".join(parts)

    def _parse_response(self, raw_text: str) -> dict:
        """Parseia JSON da resposta do Haiku.

        Tenta múltiplas estratégias de limpeza.
        """
        # Strategy 1: direct parse
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            pass

        # Strategy 2: remove ```json ... ``` fences
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

        # Strategy 3: extract first {...} block
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: return raw text as response
        logger.warning("Haiku retornou JSON inválido, usando texto raw")
        return {
            "resposta": raw_text,
            "dados_extraidos": {},
            "acao": "continuar",
            "intent": "parse_error",
        }


__all__ = ["HaikuEngine", "HaikuResponse"]
