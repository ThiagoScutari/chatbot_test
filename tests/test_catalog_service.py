import json
from pathlib import Path

from app.services.catalog_service import build_catalog_message


def test_catalog_contains_header():
    msg = build_catalog_message()
    assert "Catálogo Camisart" in msg


def test_catalog_contains_all_products():
    data = json.loads(Path("app/knowledge/products.json").read_text(encoding="utf-8"))
    msg = build_catalog_message()
    for p in data["products"]:
        assert p["nome"] in msg, f"Produto '{p['nome']}' não encontrado no catálogo"


def test_catalog_contains_services():
    msg = build_catalog_message()
    assert "Bordado" in msg or "Serviços" in msg


def test_catalog_fallback_on_missing_file(tmp_path):
    missing = tmp_path / "nope.json"
    msg = build_catalog_message(products_path=missing)
    assert "catálogo" in msg.lower()


def test_catalog_ends_with_cta():
    msg = build_catalog_message()
    assert "orçamento" in msg.lower()
