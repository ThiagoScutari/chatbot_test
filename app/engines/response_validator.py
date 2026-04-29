"""ResponseValidator — Guardrails pós-Haiku.

Verifica se a resposta do Haiku é segura antes de enviar ao cliente.
NÃO chama nenhuma API — é código Python puro.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str] = field(default_factory=list)


class ResponseValidator:
    """Guardrails pós-Haiku."""

    # Preços conhecidos do catálogo (fonte de verdade)
    KNOWN_PRICES: set[float] = {
        42.0, 45.0, 55.0,        # polo (piquet, PV, algodão)
        29.0, 25.0,              # básica (varejo, atacado)
        120.0,                   # jaleco tradicional, doméstico
        145.0,                   # jaleco premium
        35.0,                    # boné
        50.0,                    # camiseta do Pará
        4.50,                    # bordado por peça
        60.0, 70.0, 80.0,        # taxa programação bordado (faixa)
        20.0,                    # regata (referência)
    }

    # Ações válidas
    VALID_ACTIONS: set[str] = {
        "continuar",
        "lead_completo",
        "transferir_humano",
    }

    # Máximo de caracteres para WhatsApp
    MAX_RESPONSE_LENGTH: int = 1500

    def __init__(self, products_path: Path | None = None) -> None:
        self._product_names: set[str] = set()
        if products_path and products_path.exists():
            try:
                with open(products_path, encoding="utf-8") as f:
                    products = json.load(f)
                if isinstance(products, dict):
                    for key in products:
                        if isinstance(key, str):
                            self._product_names.add(key.lower())
            except Exception as exc:  # noqa: BLE001
                logger.warning("Erro ao carregar products.json: %s", exc)

    def validate(
        self,
        resposta: str,
        acao: str,
        dados_extraidos: dict,
    ) -> ValidationResult:
        """Valida resposta do Haiku.

        Args:
            resposta: texto da resposta para o cliente
            acao: ação retornada pelo Haiku
            dados_extraidos: dados extraídos da mensagem

        Returns:
            ValidationResult com status e lista de issues.
        """
        issues: list[str] = []

        # 1. Verificar preços mencionados
        issues.extend(self._check_prices(resposta))

        # 2. Verificar ação válida
        if acao not in self.VALID_ACTIONS:
            issues.append(
                f"Ação inválida: '{acao}'. Esperado: {self.VALID_ACTIONS}"
            )

        # 3. Verificar comprimento
        if len(resposta) > self.MAX_RESPONSE_LENGTH:
            issues.append(
                f"Resposta muito longa: {len(resposta)} chars "
                f"(máximo: {self.MAX_RESPONSE_LENGTH})"
            )

        # 4. Verificar se não está vazia
        if not resposta or not resposta.strip():
            issues.append("Resposta vazia")

        if issues:
            logger.warning("Guardrail issues: %s", issues)

        # silence unused-arg warning — kept for future field-level checks
        _ = dados_extraidos

        return ValidationResult(
            valid=len(issues) == 0,
            issues=issues,
        )

    def _check_prices(self, text: str) -> list[str]:
        """Verifica se preços mencionados batem com o catálogo.

        Permite totais calculados (qty × unit_price) — qualquer múltiplo
        inteiro de um preço conhecido até 1000× passa.
        """
        issues: list[str] = []
        price_matches = re.findall(r"R\$\s*([\d]+[.,]?\d{0,2})", text)
        for price_str in price_matches:
            clean = price_str.replace(".", "").replace(",", ".")
            try:
                price = float(clean)
            except ValueError:
                continue
            if price <= 0:
                continue

            # Direct catalog match
            if price in self.KNOWN_PRICES:
                continue

            # Accept if it's a valid multiple of any known price
            is_valid_total = False
            for known in self.KNOWN_PRICES:
                if known <= 0:
                    continue
                ratio = price / known
                if 1 < ratio <= 1000 and abs(ratio - round(ratio)) < 0.01:
                    is_valid_total = True
                    break

            if not is_valid_total:
                issues.append(
                    f"Preço R${price_str} não encontrado no catálogo "
                    f"e não é múltiplo de preço conhecido"
                )
        return issues


__all__ = ["ResponseValidator", "ValidationResult"]
