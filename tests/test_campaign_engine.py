import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.engines.campaign_engine import Campaign, CampaignEngine
from app.engines.regex_engine import FAQResponse


@pytest.fixture
def campaigns_json(tmp_path: Path) -> Path:
    data = {
        "version": "1.0",
        "campaigns": [
            {
                "id": "teste_ativo",
                "name": "Campanha Teste Ativa",
                "description": "",
                "enabled": True,
                "active_from": "2020-01-01",
                "active_until": "2099-12-31",
                "lead_segmento_default": "teste",
                "greeting_override": "Olá da campanha!",
                "intents": [
                    {
                        "id": "intent_campanha",
                        "priority": 55,
                        "patterns": ["\\bteste_campanha\\b"],
                        "response": {
                            "type": "text",
                            "body": "Resposta da campanha",
                        },
                    }
                ],
                "response_overrides": {
                    "preco_polo": {
                        "type": "text",
                        "body": "Polo com desconto de campanha!",
                    }
                },
            },
            {
                "id": "teste_inativo",
                "name": "Campanha Inativa",
                "enabled": False,
                "active_from": "2020-01-01",
                "active_until": "2099-12-31",
                "intents": [],
                "response_overrides": {},
            },
            {
                "id": "teste_expirada",
                "name": "Campanha Expirada",
                "enabled": True,
                "active_from": "2020-01-01",
                "active_until": "2020-12-31",
                "intents": [],
                "response_overrides": {},
            },
        ],
    }
    path = tmp_path / "campaigns.json"
    path.write_text(json.dumps(data))
    return path


def test_apenas_campanha_ativa_e_vigente(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    active = engine.active_campaigns()
    assert len(active) == 1
    assert active[0].id == "teste_ativo"


def test_greeting_override_retornado(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    assert engine.active_greeting() == "Olá da campanha!"


def test_default_segmento(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    assert engine.default_segmento() == "teste"


def test_response_override_aplicado(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    base = FAQResponse(type="text", body="Polo original")
    resultado = engine.apply_override("preco_polo", base)
    assert "desconto de campanha" in resultado.body


def test_response_sem_override_retorna_base(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    base = FAQResponse(type="text", body="Jaleco original")
    resultado = engine.apply_override("preco_jaleco", base)
    assert resultado.body == "Jaleco original"


def test_reload_apos_edicao(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    assert len(engine.active_campaigns()) == 1

    data = json.loads(campaigns_json.read_text())
    data["campaigns"][1]["enabled"] = True
    campaigns_json.write_text(json.dumps(data))

    engine.reload()
    assert len(engine.active_campaigns()) == 2


def test_datas_invalidas_levantam_erro() -> None:
    with pytest.raises(ValidationError):
        Campaign(
            id="x",
            name="x",
            enabled=True,
            active_from=date(2026, 12, 31),
            active_until=date(2026, 1, 1),
            intents=[],
            response_overrides={},
        )


def test_sem_campanha_ativa_retorna_vazio(campaigns_json: Path) -> None:
    engine = CampaignEngine(campaigns_json)
    engine.reload()
    active = engine.active_campaigns(at=date(2019, 1, 1))
    assert active == []


def test_engine_vazio_campaigns_json(tmp_path: Path) -> None:
    p = tmp_path / "empty.json"
    p.write_text(json.dumps({"version": "1.0", "campaigns": []}))
    engine = CampaignEngine(p)
    engine.reload()
    assert engine.active_campaigns() == []
    assert engine.active_greeting() is None
    assert engine.default_segmento() is None
    assert engine.status()["total_loaded"] == 0
