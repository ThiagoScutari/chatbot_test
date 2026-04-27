"""ContextEngine — Camada 3 simplificada via contexto longo.

Substitui o RAGEngine (pgvector + embeddings) por injeção direta do
catálogo completo no contexto do LLM. Adequado para catálogos pequenos
(< 50.000 tokens). Para catálogos maiores, migrar de volta para RAGEngine.

Contrato arquitetural (§2.1 do spec):
- Sem conhecimento de canais
- Interface: answer(question, session_context) → ContextResult
- Degradação graciosa: sem ANTHROPIC_API_KEY retorna resultado vazio
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ContextResult(BaseModel):
    answer: str | None
    source: str
    tokens_used: int = 0


class ContextEngine:
    """
    Responde perguntas técnicas sobre produtos da Camisart usando o
    catálogo completo como contexto do LLM.
    """

    SYSTEM_PROMPT = """Você é o assistente especialista da Camisart Belém, uma malharia
de uniformes em Belém/PA. Responda a pergunta do cliente usando APENAS as informações
do catálogo abaixo.

REGRAS ABSOLUTAS:
1. Use SOMENTE informações do catálogo fornecido — nunca invente
2. Se a informação não estiver no catálogo, diga que um consultor pode ajudar melhor
3. Seja direto, amigável e em português — máximo 3 parágrafos curtos
4. Não mencione que está consultando um catálogo — responda naturalmente
5. Se relevante, sugira fazer um orçamento ao final"""

    def __init__(
        self,
        knowledge_base_path: Path,
        products_path: Path,
        anthropic_client,
        config: dict | None = None,
    ) -> None:
        self._kb_path = knowledge_base_path
        self._products_path = products_path
        self._client = anthropic_client
        self._config = config or {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 400,
            "timeout_seconds": 10.0,
        }
        self._context_cache: str | None = None

    def _build_context(self) -> str:
        """Monta o contexto completo do catálogo (cached)."""
        if self._context_cache:
            return self._context_cache

        parts = []

        if self._kb_path.exists():
            kb_text = self._kb_path.read_text(encoding="utf-8")
            lines = kb_text.split("\n")
            filtered = []
            skip = False
            for line in lines:
                if "AGUARDANDO VALIDAÇÃO" in line or "⚠️" in line:
                    skip = True
                if line.startswith("## ") and skip:
                    skip = False
                if not skip:
                    filtered.append(line)
            parts.append("## BASE DE CONHECIMENTO CAMISART\n\n" + "\n".join(filtered))

        if self._products_path.exists():
            products = json.loads(self._products_path.read_text(encoding="utf-8"))
            prod_lines = ["## CATÁLOGO DE PRODUTOS\n"]
            for p in products.get("products", []):
                rag_text = p.get("rag_texto", "")
                if rag_text:
                    prod_lines.append(f"- {rag_text}")
            for s in products.get("servicos", []):
                rag_text = s.get("rag_texto", "")
                if rag_text:
                    prod_lines.append(f"- {rag_text}")
            parts.append("\n".join(prod_lines))

        self._context_cache = "\n\n---\n\n".join(parts)
        return self._context_cache

    def estimated_tokens(self) -> int:
        """Estimativa de tokens do contexto (1 token ≈ 4 chars)."""
        return len(self._build_context()) // 4

    async def answer(
        self,
        question: str,
        session_context: dict | None = None,
    ) -> ContextResult:
        """
        Responde uma pergunta técnica usando o catálogo como contexto.
        Retorna ContextResult com answer=None em caso de erro.
        """
        try:
            context = self._build_context()
            nome = (session_context or {}).get("nome_cliente", "cliente")

            user_prompt = (
                f"CATÁLOGO DA CAMISART:\n\n{context}\n\n"
                f"---\n\n"
                f"Pergunta de {nome}: {question}"
            )

            response = await self._client.messages.create(
                model=self._config.get("model", "claude-haiku-4-5-20251001"),
                max_tokens=self._config.get("max_tokens", 400),
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                timeout=self._config.get("timeout_seconds", 10.0),
            )

            answer_text = response.content[0].text.strip()
            tokens = len(context) // 4

            return ContextResult(
                answer=answer_text,
                source="context_engine",
                tokens_used=tokens,
            )

        except Exception as exc:
            logger.error("ContextEngine.answer erro: %s", exc)
            return ContextResult(answer=None, source="error", tokens_used=0)

    def invalidate_cache(self) -> None:
        """Invalida o cache — chamar após atualizar o catálogo."""
        self._context_cache = None
