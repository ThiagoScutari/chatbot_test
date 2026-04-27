"""Admin endpoints — CampaignEngine reload e status.

Protegidos por `X-Admin-Token` header comparado a settings.ADMIN_TOKEN.
Sem token ou token inválido → 403. Na Fase 4, substituir por JWT.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request

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


@router.get(
    "/llm/status",
    dependencies=[Depends(verify_admin_token)],
)
async def llm_status(request: Request) -> StandardResponse:
    """Métricas de uso do LLMRouter (X-Admin-Token obrigatório)."""
    llm_router = getattr(request.app.state, "llm_router", None)
    if llm_router is None:
        return StandardResponse(
            data={
                "enabled": False,
                "reason": (
                    "ANTHROPIC_API_KEY não configurada — "
                    "bot opera apenas com Camada 1 (FAQ regex)."
                ),
            }
        )

    stats = llm_router.stats
    return StandardResponse(
        data={
            "enabled": True,
            "model": llm_router.model,
            "thresholds": llm_router.thresholds,
            "stats": {
                "total_classifications": stats["total"],
                "high_confidence": stats["high"],
                "medium_confidence": stats["medium"],
                "low_confidence": stats["low"],
                "errors": stats["errors"],
                "avg_latency_ms": round(stats["avg_latency_ms"], 1),
            },
        }
    )


@router.get(
    "/context/status",
    dependencies=[Depends(verify_admin_token)],
)
async def context_status(request: Request) -> StandardResponse:
    """
    Status do ContextEngine (Camada 3).

    Mostra tamanho do catálogo em tokens e quando migrar para RAG.
    """
    engine = getattr(request.app.state, "context_engine", None)
    if not engine:
        return StandardResponse(
            data={
                "enabled": False,
                "reason": "ANTHROPIC_API_KEY não configurada.",
            }
        )

    tokens = engine.estimated_tokens()
    pct = round(tokens / 50000 * 100, 1)

    return StandardResponse(
        data={
            "enabled": True,
            "model": engine._config.get("model"),
            "estimated_context_tokens": tokens,
            "max_before_migration": 50000,
            "usage_percent": pct,
            "recommendation": (
                "OK — contexto longo adequado para este tamanho de catálogo"
                if tokens < 30000
                else "ATENÇÃO — considerar migração para RAG (ADR-002)"
            ),
        }
    )


@router.get(
    "/rag/status",
    dependencies=[Depends(verify_admin_token)],
)
async def rag_status_deprecated(request: Request) -> StandardResponse:
    """Deprecated — use /admin/context/status instead."""
    return StandardResponse(
        data={
            "deprecated": True,
            "message": "Use GET /admin/context/status (ADR-003)",
        }
    )
