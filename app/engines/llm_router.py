"""LLMRouter — Camada 2 da arquitetura de 3 camadas.

Classifica intenção de mensagens que o FAQEngine (Camada 1) não resolveu.
NÃO gera respostas livres. NÃO conhece templates. É um classificador puro.

Contrato arquitetural (§2.1 do spec):
- Sem conhecimento de canais
- Interface: classify_intent(msg, context, intents) → LLMClassification
- Degradação graciosa: se API falhar, retorna confidence=0.0 sem exceção
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMClassification(BaseModel):
    intent_id: str | None = None        # None = fora do escopo ou erro
    confidence: float = 0.0              # 0.0 a 1.0
    reasoning: str | None = None         # para debug — nunca enviado ao cliente


class LLMRouter:
    """
    Classifica intenções via Claude Haiku quando FAQEngine retorna None.

    Uso:
        router = LLMRouter(Path("app/knowledge/llm_config.json"))
        result = await router.classify_intent(
            message="quanto fica aquela camisa branca?",
            session_context={"last_messages": ["quero comprar polo"]},
            known_intents=["preco_polo", "endereco", "bordado_prazo"],
        )
        # result.intent_id = "preco_polo", result.confidence = 0.92
    """

    def __init__(
        self,
        config_path: Path,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._config = self._load_config(config_path)
        self._client = client or anthropic.AsyncAnthropic()
        self.model = self._config["model"]
        self.stats: dict[str, Any] = {
            "total": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "errors": 0,
            "total_latency_ms": 0.0,
            "avg_latency_ms": 0.0,
        }

    @property
    def thresholds(self) -> dict[str, float]:
        return self._config["thresholds"]

    async def classify_intent(
        self,
        message: str,
        session_context: dict,
        known_intents: list[str],
    ) -> LLMClassification:
        """
        Classifica a intenção da mensagem.

        Retorna LLMClassification com intent_id=None e confidence=0.0
        em caso de erro — nunca levanta exceção.
        """
        start = time.perf_counter()
        self.stats["total"] += 1

        try:
            classification = await self._call_api(
                message, session_context, known_intents
            )

            # Valida que o intent_id retornado existe na lista
            if (
                classification.intent_id is not None
                and classification.intent_id not in known_intents
            ):
                logger.warning(
                    "LLMRouter retornou intent_id desconhecido '%s' — descartando.",
                    classification.intent_id,
                )
                classification = LLMClassification(
                    intent_id=None,
                    confidence=0.0,
                    reasoning="intent_id inválido descartado",
                )

            # Atualiza stats por threshold
            t = self.thresholds
            if classification.confidence >= t["high"]:
                self.stats["high"] += 1
            elif classification.confidence >= t["medium"]:
                self.stats["medium"] += 1
            elif classification.confidence >= t["low"]:
                self.stats["low"] += 1

            if (
                self._config.get("log_low_confidence")
                and classification.confidence < t["medium"]
            ):
                logger.info(
                    "LLM low confidence %.2f for '%s' → %s",
                    classification.confidence,
                    message[:60],
                    classification.intent_id,
                )

            return classification

        except Exception as exc:  # noqa: BLE001
            self.stats["errors"] += 1
            logger.error(
                "LLMRouter erro ao classificar '%s': %s", message[:60], exc
            )
            return LLMClassification(intent_id=None, confidence=0.0)

        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.stats["total_latency_ms"] += elapsed_ms
            if self.stats["total"] > 0:
                self.stats["avg_latency_ms"] = (
                    self.stats["total_latency_ms"] / self.stats["total"]
                )

    async def _call_api(
        self,
        message: str,
        session_context: dict,
        known_intents: list[str],
    ) -> LLMClassification:
        """Chamada real à API Anthropic. Separado para facilitar mock em testes."""
        last_msgs = session_context.get("last_messages", [])
        if last_msgs:
            window = self._config["context_window"]
            context_str = "\n".join(f"- {m}" for m in last_msgs[-window:])
        else:
            context_str = "(sem histórico)"

        user_prompt = (
            f"Intents disponíveis: {', '.join(known_intents)}\n\n"
            f"Histórico recente:\n{context_str}\n\n"
            f"Mensagem atual: \"{message}\"\n\n"
            f"Classifique a intenção."
        )

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self._config["max_tokens"],
            temperature=self._config.get("temperature", 0.0),
            system=self._config["system_prompt"],
            messages=[{"role": "user", "content": user_prompt}],
            timeout=self._config.get("timeout_seconds", 8.0),
        )

        raw_text = response.content[0].text.strip()

        # Remove markdown code fences se presentes
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        # Attempt 1: direct parse
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            # Attempt 2: extract JSON object with regex
            import re
            match = re.search(r'\{[^{}]*\}', raw_text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    # Attempt 3: extract only intent_id and confidence
                    intent_match = re.search(
                        r'"intent_id"\s*:\s*"?([^",\n}]+)"?', raw_text
                    )
                    conf_match = re.search(
                        r'"confidence"\s*:\s*([0-9.]+)', raw_text
                    )
                    if intent_match and conf_match:
                        intent_val = intent_match.group(1).strip().strip('"')
                        if intent_val.lower() in ("null", "none", ""):
                            intent_val = None
                        return LLMClassification(
                            intent_id=intent_val,
                            confidence=float(conf_match.group(1)),
                            reasoning="parsed via regex fallback",
                        )
                    raise
            else:
                raise
        return LLMClassification(
            intent_id=parsed.get("intent_id"),
            confidence=float(parsed.get("confidence", 0.0)),
            reasoning=parsed.get("reasoning"),
        )

    @staticmethod
    def _load_config(path: Path) -> dict:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if not k.startswith("_")}
