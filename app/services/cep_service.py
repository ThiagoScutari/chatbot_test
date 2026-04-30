"""
CEP Service — consulta endereço via API ViaCEP.

API pública, gratuita, sem autenticação.
https://viacep.com.br

Uso:
    endereco = await cep_service.lookup("88310693")
    # {"cep": "88310-693", "logradouro": "Rua Jaime Fernandes Vieira",
    #  "bairro": "Cordeiros", "cidade": "Itajaí", "uf": "SC"}
"""
from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

VIACEP_URL = "https://viacep.com.br/ws/{cep}/json/"
TIMEOUT_SECONDS = 5.0


def normalize_cep(cep: str) -> str | None:
    """Remove tudo que não é dígito. Retorna 8 dígitos ou None."""
    clean = re.sub(r"\D", "", cep)
    return clean if len(clean) == 8 else None


async def lookup(cep: str) -> dict | None:
    """Consulta ViaCEP. Retorna dict com endereço ou None.

    Retorna None se:
    - CEP inválido (não tem 8 dígitos)
    - CEP inexistente (API retorna {"erro": true})
    - Timeout ou erro de rede

    Nunca levanta exceção — fallback graceful.
    """
    clean = normalize_cep(cep)
    if not clean:
        logger.warning("CEP inválido: '%s'", cep)
        return None

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(VIACEP_URL.format(cep=clean))
            resp.raise_for_status()
            data = resp.json()

            if data.get("erro"):
                logger.info("CEP não encontrado: %s", clean)
                return None

            return {
                "cep": data.get("cep", ""),
                "logradouro": data.get("logradouro", ""),
                "bairro": data.get("bairro", ""),
                "cidade": data.get("localidade", ""),
                "uf": data.get("uf", ""),
            }
    except Exception as exc:
        logger.error("ViaCEP erro para CEP '%s': %s", cep, exc)
        return None


def format_address(viacep: dict) -> str:
    """Formata endereço do ViaCEP para exibição."""
    parts = []
    if viacep.get("logradouro"):
        parts.append(viacep["logradouro"])
    if viacep.get("bairro"):
        parts.append(viacep["bairro"])
    cidade_uf = ""
    if viacep.get("cidade"):
        cidade_uf = viacep["cidade"]
    if viacep.get("uf"):
        cidade_uf += f"/{viacep['uf']}"
    if cidade_uf:
        parts.append(cidade_uf)
    return ", ".join(parts)
