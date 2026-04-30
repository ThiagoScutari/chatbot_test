"""Testes do CEP Service — chamadas REAIS à API ViaCEP.

A ViaCEP é pública, gratuita e estável. Testes usam API real.
Se a rede estiver indisponível, os testes falham (esperado).
"""
from __future__ import annotations

import pytest

from app.services.cep_service import format_address, lookup, normalize_cep


# ── normalize_cep (offline, sem API) ──

def test_normalize_cep_8_digitos():
    assert normalize_cep("88310693") == "88310693"


def test_normalize_cep_com_hifen():
    assert normalize_cep("88310-693") == "88310693"


def test_normalize_cep_com_espacos():
    assert normalize_cep("  88310 693  ") == "88310693"


def test_normalize_cep_curto_retorna_none():
    assert normalize_cep("8831") is None


def test_normalize_cep_longo_retorna_none():
    assert normalize_cep("883106930") is None


def test_normalize_cep_vazio_retorna_none():
    assert normalize_cep("") is None


def test_normalize_cep_letras_retorna_none():
    assert normalize_cep("abcdefgh") is None


# ── lookup (API real ViaCEP) ──

@pytest.mark.asyncio
async def test_lookup_cep_valido():
    """CEP real de Itajaí/SC retorna endereço correto."""
    result = await lookup("88310693")
    assert result is not None
    assert result["uf"] == "SC"
    assert result["cidade"] == "Itajaí"
    assert "logradouro" in result
    assert "bairro" in result


@pytest.mark.asyncio
async def test_lookup_cep_belem():
    """CEP real de Belém/PA retorna endereço correto."""
    result = await lookup("66015000")
    assert result is not None
    assert result["uf"] == "PA"


@pytest.mark.asyncio
async def test_lookup_cep_com_hifen():
    """CEP com hífen funciona normalmente."""
    result = await lookup("88310-693")
    assert result is not None
    assert result["uf"] == "SC"


@pytest.mark.asyncio
async def test_lookup_cep_inexistente():
    """CEP com 8 dígitos mas inexistente retorna None."""
    result = await lookup("00000000")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_cep_invalido():
    """CEP com menos de 8 dígitos retorna None."""
    result = await lookup("8831")
    assert result is None


@pytest.mark.asyncio
async def test_lookup_cep_vazio():
    """String vazia retorna None."""
    result = await lookup("")
    assert result is None


# ── format_address ──

def test_format_address_completo():
    viacep = {
        "logradouro": "Rua Jaime Fernandes Vieira",
        "bairro": "Cordeiros",
        "cidade": "Itajaí",
        "uf": "SC",
    }
    result = format_address(viacep)
    assert "Jaime Fernandes Vieira" in result
    assert "Cordeiros" in result
    assert "Itajaí/SC" in result


def test_format_address_sem_logradouro():
    viacep = {"logradouro": "", "bairro": "Centro", "cidade": "Belém", "uf": "PA"}
    result = format_address(viacep)
    assert "Centro" in result
    assert "Belém/PA" in result
