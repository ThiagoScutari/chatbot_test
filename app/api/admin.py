"""Admin endpoints — CampaignEngine reload e status.

Protegidos por `X-Admin-Token` header comparado a settings.ADMIN_TOKEN.
Sem token ou token inválido → 403. Na Fase 4, substituir por JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.schemas.response import StandardResponse


router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_token(x_admin_token: str = Header(...)) -> None:
    """Requer header X-Admin-Token == settings.ADMIN_TOKEN."""
    if x_admin_token != settings.ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido.")


@router.post(
    "/campaigns/reload",
    dependencies=[Depends(verify_admin_token)],
)
async def reload_campaigns() -> StandardResponse:
    """Relê campaigns.json em memória — sem reiniciar o processo."""
    from app.main import campaign_engine  # noqa: WPS433

    if campaign_engine is None:
        raise HTTPException(status_code=503, detail="CampaignEngine não inicializado.")

    count = campaign_engine.reload()
    active = campaign_engine.active_campaigns()
    return StandardResponse(
        data={
            "reloaded": True,
            "campaigns_loaded": count,
            "active_now": [c.id for c in active],
        }
    )


@router.get(
    "/campaigns/status",
    dependencies=[Depends(verify_admin_token)],
)
async def campaigns_status() -> StandardResponse:
    """Retorna campanhas ativas + próximas."""
    from app.main import campaign_engine  # noqa: WPS433

    if campaign_engine is None:
        raise HTTPException(status_code=503, detail="CampaignEngine não inicializado.")
    return StandardResponse(data=campaign_engine.status())
