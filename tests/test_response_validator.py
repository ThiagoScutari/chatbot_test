"""Tests for ResponseValidator — pure Python, zero API calls."""
from __future__ import annotations

import pytest

from app.engines.response_validator import ResponseValidator


@pytest.fixture
def validator() -> ResponseValidator:
    return ResponseValidator()


def test_valid_response(validator: ResponseValidator) -> None:
    """Clean response passes validation."""
    result = validator.validate(
        resposta="A Polo Piquet custa R$42,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is True
    assert result.issues == []


def test_unknown_price_flagged(validator: ResponseValidator) -> None:
    """Price not in catalog and not a multiple of any known price is flagged."""
    # R$77 is not in catalog and not an integer multiple of any unit price
    result = validator.validate(
        resposta="A polo custa R$77,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is False
    assert any("77" in issue for issue in result.issues)


def test_known_price_passes(validator: ResponseValidator) -> None:
    """Catalog price passes validation."""
    result = validator.validate(
        resposta="O bordado custa R$4,50 por peça.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is True


def test_invalid_action(validator: ResponseValidator) -> None:
    """Invalid action is flagged."""
    result = validator.validate(
        resposta="Oi!",
        acao="explodir",
        dados_extraidos={},
    )
    assert result.valid is False
    assert any("Ação inválida" in issue for issue in result.issues)


def test_long_response_flagged(validator: ResponseValidator) -> None:
    """Response over 1500 chars is flagged."""
    result = validator.validate(
        resposta="a" * 1600,
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is False
    assert any("longa" in issue for issue in result.issues)


def test_empty_response_flagged(validator: ResponseValidator) -> None:
    """Empty response is flagged."""
    result = validator.validate(
        resposta="",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is False
    assert any("vazia" in issue for issue in result.issues)


def test_multiple_prices_validated(validator: ResponseValidator) -> None:
    """Multiple prices in same response are all checked."""
    result = validator.validate(
        resposta="Polo R$42,00, Jaleco R$120,00 e Boné R$35,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is True


def test_mix_valid_invalid_prices(validator: ResponseValidator) -> None:
    """One bad price fails even if others are valid."""
    result = validator.validate(
        resposta="Polo R$42,00 e o especial R$77,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is False


def test_valid_total_price(validator: ResponseValidator) -> None:
    """Computed total (8 × R$42 = R$336) passes validation."""
    result = validator.validate(
        resposta="O total para 8 polos fica R$336,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is True


def test_valid_total_jaleco(validator: ResponseValidator) -> None:
    """6 × R$145 = R$870 passes validation."""
    result = validator.validate(
        resposta="6 jalecos Premium: R$870,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is True


def test_invalid_total_still_caught(validator: ResponseValidator) -> None:
    """Price that is not a multiple of any known price fails."""
    result = validator.validate(
        resposta="O total fica R$777,00.",
        acao="continuar",
        dados_extraidos={},
    )
    assert result.valid is False
