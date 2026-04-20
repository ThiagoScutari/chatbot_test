from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.response import StandardResponse


router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> StandardResponse:
    db.execute(text("SELECT 1"))
    return StandardResponse(data={"status": "ok", "db": "up"})
